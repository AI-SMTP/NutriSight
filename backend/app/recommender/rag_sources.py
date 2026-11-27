"""팀 공식 RAG 원문 4종(PDF·XML) 정의, 텍스트 추출, 문단 청킹 유틸리티.

출처 정본: `docs/research/rag-sources/README.md`
원문 PDF/XML 파일은 재배포 라이선스 미확인으로 Git에 커밋하지 않고 로컬에서 읽는다.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCES_DIR = REPO_ROOT / "docs" / "research" / "rag-sources"
DEFAULT_CHROMA_DIR = Path(__file__).resolve().parents[2] / "var" / "chroma_guidelines"


@dataclass(frozen=True)
class OfficialSourceSpec:
    """`docs/research/rag-sources/README.md`의 공식 가이드라인 원문 메타데이터."""

    doc_id: str
    subfolder: str
    filename: str
    document_title: str
    publisher: str
    source_url: str
    language: str
    xml_fallback_filename: str | None = None


@dataclass(frozen=True)
class GuidelineChunk:
    """청킹된 가이드라인 구절 단위."""

    chunk_id: str
    doc_id: str
    section: str
    text: str
    source_url: str
    document_title: str
    language: str
    file_hash: str


OFFICIAL_SOURCE_SPECS: tuple[OfficialSourceSpec, ...] = (
    OfficialSourceSpec(
        doc_id="espen_geriatrics",
        subfolder="espen-geriatrics",
        filename="espen-practical-guideline-geriatrics.pdf",
        document_title="ESPEN practical guideline: Clinical nutrition and hydration in geriatrics",
        publisher="ESPEN",
        source_url=(
            "https://www.espen.org/files/ESPEN-Guidelines/"
            "ESPEN%5Fpractical%5Fguideline%5FClinical%5Fnutrition%5Fand%5Fhydration%5Fin%5Fgeriatrics.pdf"
        ),
        language="en",
    ),
    OfficialSourceSpec(
        doc_id="kjg_elderly_nutrition_2019",
        subfolder="kjg-elderly-nutrition-2019",
        filename="kjg-2019-73-4-196-elderly-nutrition.pdf",
        document_title="대한소화기학회지 「고령자의 영양 관리」(2019)",
        publisher="대한소화기학회",
        source_url="https://doi.org/10.4166/kjg.2019.73.4.196",
        language="ko",
    ),
    OfficialSourceSpec(
        doc_id="glim_2025",
        subfolder="glim-2025",
        filename="glim-5-year-update-2025-clnu.pdf",
        document_title="GLIM 5년 업데이트(2025)",
        publisher="Clinical Nutrition / JPEN",
        source_url="https://www.clinicalnutritionjournal.com/article/S0261-5614(25)00086-X/pdf",
        language="en",
        xml_fallback_filename="glim-5-year-update-2025-jpen.xml",
    ),
    OfficialSourceSpec(
        doc_id="khna_pressure_injury",
        subfolder="khna-pressure-injury",
        filename="khna-pressure-injury-guideline.pdf",
        document_title="대한간호협회 욕창 예방·관리 가이드라인",
        publisher="대한간호협회",
        source_url="https://khna.or.kr/home/data/khna_guide_ebp10.pdf",
        language="ko",
    ),
)


def clean_extracted_text(text: str) -> str:
    """추출된 PDF/XML 텍스트에서 불필요한 공백과 제어 문자를 정리한다."""
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, *, chunk_size: int = 900, chunk_overlap: int = 180) -> list[str]:
    """문단·문장 경계를 우선 보존하며 텍스트를 청크 목록으로 분할한다."""
    cleaned = clean_extracted_text(text)
    if not cleaned:
        return []
    if len(cleaned) <= chunk_size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    total_len = len(cleaned)
    while start < total_len:
        end = min(start + chunk_size, total_len)
        if end < total_len:
            min_split = start + chunk_size // 2
            split_at = cleaned.rfind("\n\n", min_split, end)
            if split_at == -1:
                split_at = cleaned.rfind(". ", min_split, end)
                if split_at != -1:
                    split_at += 1
            if split_at == -1:
                split_at = cleaned.rfind("\n", min_split, end)
            if split_at != -1 and split_at > start:
                end = split_at

        piece = cleaned[start:end].strip()
        if len(piece) >= 40:
            chunks.append(piece)
        if end >= total_len:
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks


def _resolve_source_file(base: Path, spec: OfficialSourceSpec) -> tuple[Path, str] | None:
    pdf_path = base / spec.subfolder / spec.filename
    if (
        pdf_path.exists()
        and pdf_path.stat().st_size > 1024
        and pdf_path.read_bytes()[:5] == b"%PDF-"
    ):
        return pdf_path, "pdf"

    if spec.xml_fallback_filename is not None:
        xml_path = base / spec.subfolder / spec.xml_fallback_filename
        if xml_path.exists() and xml_path.stat().st_size > 64:
            return xml_path, "xml"
    return None


def compute_source_hashes(sources_dir: str | Path = DEFAULT_SOURCES_DIR) -> dict[str, str]:
    """PDF 텍스트 파싱 없이 존재하는 원문 파일의 SHA-256 앞 16자리만 계산한다."""
    base = Path(sources_dir)
    hashes: dict[str, str] = {}
    for spec in OFFICIAL_SOURCE_SPECS:
        resolved = _resolve_source_file(base, spec)
        if resolved is None:
            continue
        file_path, _ = resolved
        hashes[spec.doc_id] = hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]
    return hashes


def _extract_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        extracted = clean_extracted_text(page.extract_text() or "")
        if extracted:
            pages.append((idx, extracted))
    return pages


def _extract_xml_sections(xml_path: Path) -> list[tuple[str, str]]:
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    sections: list[tuple[str, str]] = []
    for idx, elem in enumerate(root.iter(), start=1):
        tag = elem.tag.split("}")[-1].lower()
        if tag != "sec":
            continue
        title_el = next((c for c in elem if c.tag.split("}")[-1].lower() == "title"), None)
        title = "".join(title_el.itertext()).strip() if title_el is not None else f"Section {idx}"
        paragraphs = [
            "".join(p.itertext()).strip() for p in elem if p.tag.split("}")[-1].lower() == "p"
        ]
        body = clean_extracted_text("\n\n".join(p for p in paragraphs if p))
        if body:
            sections.append((title or f"Section {idx}", body))
    if not sections:
        full_text = clean_extracted_text(" ".join(root.itertext()))
        if full_text:
            sections.append(("Full Document", full_text))
    return sections


def load_guideline_chunks(
    sources_dir: str | Path = DEFAULT_SOURCES_DIR,
    *,
    chunk_size: int = 900,
    chunk_overlap: int = 180,
) -> tuple[list[GuidelineChunk], dict[str, dict[str, Any]]]:
    """로컬 공식 원문 4종(PDF/XML)을 읽어 `GuidelineChunk` 목록과 문서별 적재 상태를 반환한다."""
    base = Path(sources_dir)
    chunks: list[GuidelineChunk] = []
    status_by_doc: dict[str, dict[str, Any]] = {}

    for spec in OFFICIAL_SOURCE_SPECS:
        resolved = _resolve_source_file(base, spec)
        if resolved is None:
            status_by_doc[spec.doc_id] = {
                "loaded": False,
                "expected_path": str(base / spec.subfolder / spec.filename),
                "chunks": 0,
            }
            continue

        file_path, kind = resolved
        file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]
        doc_chunk_count = 0

        if kind == "pdf":
            for page_num, page_text in _extract_pdf_pages(file_path):
                pieces = chunk_text(page_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                for c_idx, piece in enumerate(pieces, start=1):
                    chunks.append(
                        GuidelineChunk(
                            chunk_id=f"{spec.doc_id}#p{page_num}_c{c_idx}",
                            doc_id=spec.doc_id,
                            section=f"p.{page_num}",
                            text=piece,
                            source_url=spec.source_url,
                            document_title=spec.document_title,
                            language=spec.language,
                            file_hash=file_hash,
                        )
                    )
                    doc_chunk_count += 1
        else:
            for s_idx, (sec_title, sec_body) in enumerate(
                _extract_xml_sections(file_path), start=1
            ):
                pieces = chunk_text(sec_body, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                for c_idx, piece in enumerate(pieces, start=1):
                    chunks.append(
                        GuidelineChunk(
                            chunk_id=f"{spec.doc_id}#s{s_idx}_c{c_idx}",
                            doc_id=spec.doc_id,
                            section=sec_title[:80],
                            text=piece,
                            source_url=spec.source_url,
                            document_title=spec.document_title,
                            language=spec.language,
                            file_hash=file_hash,
                        )
                    )
                    doc_chunk_count += 1

        status_by_doc[spec.doc_id] = {
            "loaded": True,
            "path": str(file_path),
            "kind": kind,
            "file_hash": file_hash,
            "chunks": doc_chunk_count,
        }

    return chunks, status_by_doc
