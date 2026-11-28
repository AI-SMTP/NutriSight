"""팀 공식 RAG 원문 4종(5개 아티팩트) 매니페스트 검증, 텍스트 추출, 고유 근거 식별자 청킹.

출처 정본: `docs/research/rag-sources/README.md`
매니페스트: `backend/app/recommender/source_manifest.json`

핵심 정책:
- 원문 PDF/XML 파일은 Git에 커밋하지 않고 로컬에서 읽는다.
- 파일이 존재한다는 사실만으로 `approved`로 자동 승격하지 않는다.
- 아티팩트별 전체 64자리 SHA-256과 `review_status`를 검증하고, PDF와 XML 출처를 엄격히 구분한다.
- 모든 청크는 `(doc_id, section)` 고유성이 보장되어 `EvidenceRef` 역추적이 가능하다.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCES_DIR = REPO_ROOT / "docs" / "research" / "rag-sources"
DEFAULT_README_PATH = DEFAULT_SOURCES_DIR / "README.md"
DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parent / "source_manifest.json"
DEFAULT_CHROMA_DIR = Path(__file__).resolve().parents[2] / "var" / "chroma_guidelines"

EXTRACTOR_VERSION = "v2.1"
SECTION_ID_VERSION = "v2.0"

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

_VERIFIED_REC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:^|\n)\s*Recommendation\s+(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*(R\d{1,3})\s*[:.\-]\s+\S"),
)


@dataclass(frozen=True)
class SourceArtifactSpec:
    """매니페스트에 등록된 단일 원문 파일(PDF 또는 XML) 메타데이터."""

    artifact_id: str
    doc_id: str
    document_title: str
    publisher: str
    published_year_or_edition: str
    relative_path: str
    format: str  # "pdf" | "xml"
    source_url: str
    language: str
    expected_sha256: str | None
    review_status: str  # "pending" | "approved"
    reviewed_at: str | None = None


@dataclass(frozen=True)
class ArtifactAuditEntry:
    """로컬 파일·README·매니페스트 대조 감사 결과 항목."""

    artifact_id: str
    doc_id: str
    document_title: str
    publisher: str
    published_year_or_edition: str
    actual_source_file: str
    format: str
    source_url: str
    review_status: str
    expected_sha256: str | None
    actual_sha256: str | None
    file_exists: bool
    in_readme: bool
    # "approved_ready" | "pending_review" | "missing_file" | "hash_mismatch" | "invalid_format"
    status: str
    detail: str


@dataclass(frozen=True)
class GuidelineChunk:
    """고유 근거 식별자(`doc_id`, `section`)를 갖춘 청킹된 가이드라인 구절."""

    chunk_id: str
    doc_id: str
    artifact_id: str
    section: str
    locator: str
    verified_recommendation_no: str | None
    text: str
    source_url: str
    document_title: str
    publisher: str
    published_year_or_edition: str
    actual_source_file: str
    source_format: str
    language: str
    file_sha256: str
    review_status: str


def compute_file_sha256(path: Path) -> str:
    """파일의 전체 64자리 SHA-256 해시를 계산한다."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def load_source_manifest(
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
) -> tuple[list[SourceArtifactSpec], str]:
    """매니페스트 JSON을 읽어 아티팩트 목록과 매니페스트 파일 자체의 SHA-256을 반환한다."""
    path = Path(manifest_path)
    raw_bytes = path.read_bytes()
    manifest_sha = hashlib.sha256(raw_bytes).hexdigest()
    data = json.loads(raw_bytes.decode("utf-8"))
    artifacts: list[SourceArtifactSpec] = []
    seen_artifact_ids: set[str] = set()
    seen_paths: set[str] = set()
    for entry in data.get("artifacts", []):
        aid = str(entry["artifact_id"]).strip()
        rel_path = str(entry["relative_path"]).strip()
        if not aid or aid in seen_artifact_ids:
            raise ValueError(f"매니페스트에 중복되거나 비어 있는 artifact_id가 있다: {aid!r}")
        if not rel_path or rel_path in seen_paths:
            raise ValueError(
                f"매니페스트에 중복되거나 비어 있는 relative_path가 있다: {rel_path!r}"
            )
        seen_artifact_ids.add(aid)
        seen_paths.add(rel_path)

        status = str(entry.get("review_status", "pending")).strip().lower()
        if status not in {"pending", "approved"}:
            status = "pending"
        raw_sha = entry.get("expected_sha256")
        norm_sha = str(raw_sha).strip().lower() if raw_sha is not None else None
        artifacts.append(
            SourceArtifactSpec(
                artifact_id=aid,
                doc_id=str(entry["doc_id"]).strip(),
                document_title=str(entry["document_title"]),
                publisher=str(entry["publisher"]),
                published_year_or_edition=str(entry["published_year_or_edition"]),
                relative_path=rel_path,
                format=str(entry["format"]).strip().lower(),
                source_url=str(entry["source_url"]),
                language=str(entry.get("language", "en")),
                expected_sha256=norm_sha,
                review_status=status,
                reviewed_at=entry.get("reviewed_at"),
            )
        )
    return artifacts, manifest_sha


def parse_readme_artifact_paths(readme_path: str | Path = DEFAULT_README_PATH) -> set[str]:
    """`docs/research/rag-sources/README.md` 표에서 공식 원문 상대 경로 집합을 추출한다."""
    path = Path(readme_path)
    if not path.exists():
        return set()
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        folder = cells[0].strip("` ").rstrip("/")
        filename = cells[1].strip("` ")
        if folder and filename and not folder.startswith("-") and folder != "폴더":
            found.add(f"{folder}/{filename}")
    return found


def _validate_bytes_magic(raw_bytes: bytes, expected_format: str) -> bool:
    size = len(raw_bytes)
    if expected_format == "pdf":
        return size > 1024 and raw_bytes[:5] == b"%PDF-"
    if expected_format == "xml":
        if size <= 64:
            return False
        return raw_bytes[:256].lstrip().startswith(b"<")
    return False


def _validate_file_magic(file_path: Path, expected_format: str) -> bool:
    return _validate_bytes_magic(file_path.read_bytes(), expected_format)


def audit_source_manifest(
    sources_dir: str | Path = DEFAULT_SOURCES_DIR,
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    readme_path: str | Path | None = None,
) -> dict[str, Any]:
    """매니페스트·README·실제 로컬 파일을 3자 대조하여 감사 리포트를 생성한다."""
    base = Path(sources_dir)
    artifacts, manifest_sha = load_source_manifest(manifest_path)
    effective_readme = Path(readme_path) if readme_path is not None else (base / "README.md")
    if not effective_readme.exists() and readme_path is None:
        effective_readme = DEFAULT_README_PATH
    readme_paths = parse_readme_artifact_paths(effective_readme)

    entries: list[ArtifactAuditEntry] = []
    manifest_paths: set[str] = set()

    for spec in artifacts:
        manifest_paths.add(spec.relative_path)
        file_path = base / spec.relative_path
        in_readme = (spec.relative_path in readme_paths) if readme_paths else True
        exists = file_path.exists()
        actual_sha: str | None = None

        if not exists:
            status = "missing_file"
            detail = f"원문 파일 누락: {spec.relative_path} (review_status={spec.review_status})"
        elif not _validate_file_magic(file_path, spec.format):
            status = "invalid_format"
            detail = f"형식 불일치: 기대={spec.format}, 파일={spec.relative_path}"
        else:
            actual_sha = compute_file_sha256(file_path)
            if spec.review_status != "approved":
                status = "pending_review"
                detail = (
                    f"파일은 존재하나 검토 미승인(review_status={spec.review_status}) — "
                    "자동 승인 금지 정책으로 색인 제외"
                )
            elif not spec.expected_sha256 or not _SHA256_HEX_RE.match(spec.expected_sha256):
                status = "hash_mismatch"
                detail = (
                    "승인 아티팩트에 유효한 64자리 expected_sha256이 없어 "
                    "무결성 검증을 통과할 수 없음(fail-closed)"
                )
            elif actual_sha != spec.expected_sha256:
                status = "hash_mismatch"
                detail = (
                    f"SHA-256 판본 불일치: expected={spec.expected_sha256[:12]}..., "
                    f"actual={actual_sha[:12]}..."
                )
            else:
                status = "approved_ready"
                detail = "승인·해시 검증 완료"

        entries.append(
            ArtifactAuditEntry(
                artifact_id=spec.artifact_id,
                doc_id=spec.doc_id,
                document_title=spec.document_title,
                publisher=spec.publisher,
                published_year_or_edition=spec.published_year_or_edition,
                actual_source_file=spec.relative_path,
                format=spec.format,
                source_url=spec.source_url,
                review_status=spec.review_status,
                expected_sha256=spec.expected_sha256,
                actual_sha256=actual_sha,
                file_exists=exists,
                in_readme=in_readme,
                status=status,
                detail=detail,
            )
        )

    readme_missing_from_manifest = sorted(readme_paths - manifest_paths) if readme_paths else []
    approved_doc_ids = sorted({e.doc_id for e in entries if e.status == "approved_ready"})
    all_manifest_doc_ids = sorted({e.doc_id for e in entries})
    missing_or_unapproved_doc_ids = sorted(set(all_manifest_doc_ids) - set(approved_doc_ids))

    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "readme_checked": effective_readme.exists(),
        "readme_missing_from_manifest": readme_missing_from_manifest,
        "total_manifest_docs": len(all_manifest_doc_ids),
        "approved_ready_doc_ids": approved_doc_ids,
        "missing_or_unapproved_doc_ids": missing_or_unapproved_doc_ids,
        "artifacts": [asdict(e) for e in entries],
    }


def clean_extracted_text(text: str) -> str:
    """Unicode NFKC 정규화 후 제어 문자·중복 공백을 정리한다."""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\x00", " ")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


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


def extract_verified_recommendation_no(text: str) -> str | None:
    """원문 텍스트에 명시적으로 검증 가능한 권고 번호(예: Recommendation 20 → R20)만 추출한다.

    원문에 없는 권고 번호는 절대 생성하지 않는다.
    """
    for pat in _VERIFIED_REC_PATTERNS:
        matches = pat.findall(text)
        unique_nums: list[str] = []
        for raw in matches:
            norm = raw.upper() if raw.upper().startswith("R") else f"R{raw}"
            if norm not in unique_nums:
                unique_nums.append(norm)
        # 한 청크 안에 단일 권고 번호가 명확히 존재할 때만 반환
        if len(unique_nums) == 1:
            return unique_nums[0]
    return None


def compute_source_hashes(
    sources_dir: str | Path = DEFAULT_SOURCES_DIR,
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    require_approved: bool = True,
) -> dict[str, str]:
    """승인·검증 대상 아티팩트의 전체 64자리 SHA-256 매핑(`artifact_id -> sha256`)을 계산한다."""
    audit = audit_source_manifest(sources_dir, manifest_path=manifest_path)
    allowed_statuses = (
        {"approved_ready"} if require_approved else {"approved_ready", "pending_review"}
    )
    return {
        art["artifact_id"]: art["actual_sha256"]
        for art in audit["artifacts"]
        if art["status"] in allowed_statuses and art["actual_sha256"]
    }


def _extract_pdf_pages_from_bytes(pdf_bytes: bytes) -> list[tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages: list[tuple[int, str]] = []
    for idx, page in enumerate(reader.pages, start=1):
        extracted = clean_extracted_text(page.extract_text() or "")
        if extracted:
            pages.append((idx, extracted))
    return pages


def _extract_xml_sections_from_bytes(xml_bytes: bytes) -> list[tuple[int, str, str]]:
    root = ET.fromstring(xml_bytes)
    sections: list[tuple[int, str, str]] = []
    sec_ordinal = 0
    for elem in root.iter():
        tag = elem.tag.split("}")[-1].lower()
        if tag != "sec":
            continue
        sec_ordinal += 1
        title_el = next((c for c in elem if c.tag.split("}")[-1].lower() == "title"), None)
        title = (
            "".join(title_el.itertext()).strip()
            if title_el is not None
            else f"Section {sec_ordinal}"
        )
        paragraphs = [
            "".join(p.itertext()).strip() for p in elem if p.tag.split("}")[-1].lower() == "p"
        ]
        body = clean_extracted_text("\n\n".join(p for p in paragraphs if p))
        if body:
            sections.append((sec_ordinal, title or f"Section {sec_ordinal}", body))
    if not sections:
        full_text = clean_extracted_text(" ".join(root.itertext()))
        if full_text:
            sections.append((1, "Full Document", full_text))
    return sections


def _assign_unique_sections(raw_chunks: list[GuidelineChunk]) -> list[GuidelineChunk]:
    """문서 내 `(doc_id, section)` 고유성을 강제한다.

    - 검증된 권고 번호(`R20` 등)가 문서 전체에서 단 하나의 청크에만 유일하게 매핑되면 `R20` 사용.
    - 복수 청크에 걸치거나 권고 번호가 없으면 결정론적 `locator`(`p.12#c1` 또는 `xml:s1#c1`) 사용.
    """
    rec_counts: Counter[tuple[str, str]] = Counter()
    for c in raw_chunks:
        if c.verified_recommendation_no:
            rec_counts[(c.doc_id, c.verified_recommendation_no)] += 1

    finalized: list[GuidelineChunk] = []
    seen_keys: set[tuple[str, str]] = set()

    for c in raw_chunks:
        if (
            c.verified_recommendation_no
            and rec_counts[(c.doc_id, c.verified_recommendation_no)] == 1
        ):
            section = c.verified_recommendation_no
        else:
            section = c.locator

        key = (c.doc_id, section)
        if key in seen_keys:
            section = f"{c.artifact_id}:{c.locator}"
            key = (c.doc_id, section)
        if key in seen_keys:
            raise ValueError(f"중복된 근거 식별자 감지: doc_id={c.doc_id}, section={section}")
        seen_keys.add(key)

        finalized.append(
            GuidelineChunk(
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                artifact_id=c.artifact_id,
                section=section,
                locator=c.locator,
                verified_recommendation_no=c.verified_recommendation_no,
                text=c.text,
                source_url=c.source_url,
                document_title=c.document_title,
                publisher=c.publisher,
                published_year_or_edition=c.published_year_or_edition,
                actual_source_file=c.actual_source_file,
                source_format=c.source_format,
                language=c.language,
                file_sha256=c.file_sha256,
                review_status=c.review_status,
            )
        )
    return finalized


def load_guideline_chunks(
    sources_dir: str | Path = DEFAULT_SOURCES_DIR,
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    chunk_size: int = 900,
    chunk_overlap: int = 180,
    require_approved: bool = True,
    fail_on_approved_issue: bool = True,
) -> tuple[list[GuidelineChunk], dict[str, Any]]:
    """매니페스트 검증을 통과한 공식 원문만 청킹하고 감사 리포트와 함께 반환한다.

    - `require_approved=True` (기본): `review_status=="approved"` 및 해시 일치 아티팩트만 적재.
    - `fail_on_approved_issue=True` (기본): 승인 아티팩트 누락·해시 불일치·형식 오류·0청크 시 예외.
    """
    base = Path(sources_dir)
    specs, _ = load_source_manifest(manifest_path)
    spec_by_id = {s.artifact_id: s for s in specs}
    audit = audit_source_manifest(sources_dir, manifest_path=manifest_path)

    allowed_statuses = (
        {"approved_ready"} if require_approved else {"approved_ready", "pending_review"}
    )
    raw_chunks: list[GuidelineChunk] = []
    status_by_artifact: dict[str, dict[str, Any]] = {}
    approved_failures: list[str] = []

    for art in audit["artifacts"]:
        aid = art["artifact_id"]
        spec = spec_by_id[aid]
        art_status = art["status"]

        if spec.review_status == "approved" and art_status in {
            "missing_file",
            "hash_mismatch",
            "invalid_format",
        }:
            approved_failures.append(f"{aid}: {art['detail']}")

        if art_status not in allowed_statuses:
            status_by_artifact[aid] = {
                **art,
                "loaded": False,
                "chunks": 0,
            }
            continue

        file_path = base / spec.relative_path
        # TOCTOU 방지: 바이트를 단 1회만 읽고 해시 검증 후 동일 바이트 버퍼에서 파싱한다.
        raw_bytes = file_path.read_bytes()
        actual_sha = hashlib.sha256(raw_bytes).hexdigest()
        if not _validate_bytes_magic(raw_bytes, spec.format):
            approved_failures.append(f"{aid}: 파싱 직전 형식 검증 실패 ({spec.relative_path})")
            status_by_artifact[aid] = {
                **art,
                "status": "invalid_format",
                "loaded": False,
                "chunks": 0,
            }
            continue
        if spec.review_status == "approved" and actual_sha != spec.expected_sha256:
            approved_failures.append(f"{aid}: 파싱 직전 SHA-256 변경 감지 ({spec.relative_path})")
            status_by_artifact[aid] = {
                **art,
                "status": "hash_mismatch",
                "loaded": False,
                "chunks": 0,
            }
            continue

        doc_chunk_count = 0

        if spec.format == "pdf":
            for page_num, page_text in _extract_pdf_pages_from_bytes(raw_bytes):
                pieces = chunk_text(page_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                for c_idx, piece in enumerate(pieces, start=1):
                    locator = f"p.{page_num}#c{c_idx}"
                    rec_no = extract_verified_recommendation_no(piece)
                    raw_chunks.append(
                        GuidelineChunk(
                            chunk_id=f"{spec.artifact_id}::{locator}",
                            doc_id=spec.doc_id,
                            artifact_id=spec.artifact_id,
                            section=locator,
                            locator=locator,
                            verified_recommendation_no=rec_no,
                            text=piece,
                            source_url=spec.source_url,
                            document_title=spec.document_title,
                            publisher=spec.publisher,
                            published_year_or_edition=spec.published_year_or_edition,
                            actual_source_file=spec.relative_path,
                            source_format=spec.format,
                            language=spec.language,
                            file_sha256=actual_sha,
                            review_status=spec.review_status,
                        )
                    )
                    doc_chunk_count += 1
        else:
            for sec_ord, _sec_title, sec_body in _extract_xml_sections_from_bytes(raw_bytes):
                pieces = chunk_text(sec_body, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                for c_idx, piece in enumerate(pieces, start=1):
                    locator = f"xml:s{sec_ord}#c{c_idx}"
                    rec_no = extract_verified_recommendation_no(piece)
                    raw_chunks.append(
                        GuidelineChunk(
                            chunk_id=f"{spec.artifact_id}::{locator}",
                            doc_id=spec.doc_id,
                            artifact_id=spec.artifact_id,
                            section=locator,
                            locator=locator,
                            verified_recommendation_no=rec_no,
                            text=piece,
                            source_url=spec.source_url,
                            document_title=spec.document_title,
                            publisher=spec.publisher,
                            published_year_or_edition=spec.published_year_or_edition,
                            actual_source_file=spec.relative_path,
                            source_format=spec.format,
                            language=spec.language,
                            file_sha256=actual_sha,
                            review_status=spec.review_status,
                        )
                    )
                    doc_chunk_count += 1

        if doc_chunk_count == 0:
            approved_failures.append(f"{aid}: 추출된 청크가 0개입니다 ({spec.relative_path})")
            status_by_artifact[aid] = {
                **art,
                "status": "zero_chunks",
                "loaded": False,
                "chunks": 0,
            }
            continue

        status_by_artifact[aid] = {
            **art,
            "loaded": True,
            "chunks": doc_chunk_count,
        }

    if fail_on_approved_issue and approved_failures:
        raise ValueError(f"승인 문헌 무결성 검증 실패: {'; '.join(approved_failures)}")

    chunks = _assign_unique_sections(raw_chunks)
    report = {
        **audit,
        "status_by_artifact": status_by_artifact,
        "loaded_chunk_count": len(chunks),
        "loaded_doc_ids": sorted({c.doc_id for c in chunks}),
        "extractor_version": EXTRACTOR_VERSION,
        "section_id_version": SECTION_ID_VERSION,
    }
    return chunks, report
