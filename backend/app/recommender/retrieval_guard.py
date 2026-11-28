"""RAG v0.3 안전 검색 계약(P0) 및 인용 무결성 검증(P2) 모듈.

원칙:
- 공용 계약(`GuidelineSearch`, `GuidelineHit`, `EvidenceRef`)을 변경하지 않는다.
- 검색기 자체는 임상적 판단을 확정하거나 자동 처방을 생성하지 않는다.
- 근거 부족·미지원 처방 수치 범위·검색 오류 시 T5 에이전트가 안전하게 보류(`abstain`)할 수 있도록
  구조화된 상태(`RetrievalStatus`)와 사유를 반환한다.
- 추천 항목에 첨부된 `EvidenceRef`가 활성 승인 색인에서 1:1 역추적되는지 검증해
  `FakeGuidelineSearch` 모의 ID(`R20`, `R23` 등)나 미검증 ID가 공식 근거로 표시되지 않게 막는다.
"""

from __future__ import annotations

import inspect
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.recommender.guideline_types import GuidelineHit, GuidelineSearch
from app.services.ports import EvidenceRef


class RetrievalStatus(StrEnum):
    """안전 검색 래퍼의 결과 상태."""

    FOUND = "found"
    NO_EVIDENCE = "no_evidence"
    UNSUPPORTED_SCOPE = "unsupported_scope"
    SEARCH_ERROR = "search_error"


@dataclass(frozen=True)
class SafeRetrievalResult:
    """T5 에이전트용 구조화 검색 결과.

    - `status != FOUND`일 때 `hits`는 항상 빈 튜플 `()`이며 `requires_clinical_review=True`다.
    - `FOUND`라도 최종 임상 판단과 처방 확정은 검색기가 아니라 의료진/에이전트 정책의 책임이다.
    """

    status: RetrievalStatus
    hits: tuple[GuidelineHit, ...]
    requires_clinical_review: bool
    abstain_reason: str | None = None
    scope_warning: str | None = None
    error_detail: str | None = None


# 승인 코퍼스 4종(ESPEN 노인, KJG, GLIM 2025, KHNA 욕창)이 다루지 않는
# 구체적 병기별 처방 수치·약물 투약 프로토콜 요청만 보수적으로 차단한다.
# 주의: "고령자 만성콩팥병 영양 평가 개별 목표 주의사항"(NS09-A) 같은 일반 주의사항 질의는
# 구체적 처방 수치 요청이 아니므로 차단하지 않는다.
_CKD_STAGE_OR_RENAL_RE = re.compile(
    r"(?:만성\s*콩팥병|만성\s*신장\s*질환|신부전|\bckd\b|g[345][ab]?|투석)",
    re.IGNORECASE,
)
_SPECIFIC_DOSAGE_REQUEST_RE = re.compile(
    r"(?:처방\s*수치|처방량|증량\s*한도|투여\s*용량|투여량|단백질\s*처방|"
    r"목표가\s*미등록|단백질\s*목표\s*미등록|병기별\s*단백질|"
    r"단백질.{0,30}(?:몇\s*(?:g|그램)|얼마|적절|권장량|목표량|"
    r"g\s*/\s*kg|하루\s*섭취\s*수치))",
    re.IGNORECASE,
)
_DRUG_PROTOCOL_RE = re.compile(
    r"(?:(?:항생제|항혈소판제|스테로이드|인슐린|와파린).{0,25}"
    r"(?:용량|증량|투여\s*기간|중단일|재개|처방)|"
    r"(?:패혈증|심근경색|스텐트|교환수혈|광선치료).{0,25}(?:항생제|항혈소판제|빌리루빈|적응증))",
    re.IGNORECASE,
)


def detect_unsupported_scope(query: str) -> str | None:
    """승인 문헌 4종의 범위를 벗어난 처방 수치·약물 투약 요청을 보수적으로 감지한다.

    반환값이 문자열이면 미지원 범위 사유이며, `None`이면 정상 검색 대상으로 통과한다.
    """
    normalized = unicodedata.normalize("NFKC", query).strip()
    if not normalized:
        return None

    if _CKD_STAGE_OR_RENAL_RE.search(normalized) and _SPECIFIC_DOSAGE_REQUEST_RE.search(normalized):
        return (
            "승인 가이드라인 4종(ESPEN·KJG·GLIM·KHNA)에는 만성콩팥병 병기별 단백질 처방 수치나 "
            "목표 미등록 환자의 자동 처방 기준이 없어 의료진 개별 판단이 필요합니다."
        )

    if _DRUG_PROTOCOL_RE.search(normalized):
        return (
            "승인 가이드라인 4종은 영양 관리 문헌으로 약물 용량·투약 중단/재개·급성기 약물 "
            "프로토콜 근거를 포함하지 않으므로 의료진 확인이 필요합니다."
        )

    return None


async def safe_search_guidelines(
    search: GuidelineSearch,
    query: str,
    *,
    limit: int = 3,
) -> SafeRetrievalResult:
    """`GuidelineSearch` 계약을 유지하면서 근거 부족·미지원 범위·오류를 안전하게 구조화한다."""
    if limit < 1:
        raise ValueError("limit은 1 이상이어야 한다")

    cleaned = unicodedata.normalize("NFKC", query).strip()
    if not cleaned:
        return SafeRetrievalResult(
            status=RetrievalStatus.NO_EVIDENCE,
            hits=(),
            requires_clinical_review=True,
            abstain_reason="검색 질의가 비어 있어 가이드라인 근거를 조회할 수 없습니다.",
        )

    scope_reason = detect_unsupported_scope(cleaned)
    if scope_reason is not None:
        return SafeRetrievalResult(
            status=RetrievalStatus.UNSUPPORTED_SCOPE,
            hits=(),
            requires_clinical_review=True,
            abstain_reason=scope_reason,
            scope_warning="out_of_guideline_prescription_scope",
        )

    try:
        hits = await search.search(cleaned, limit=limit)
    except Exception as exc:
        return SafeRetrievalResult(
            status=RetrievalStatus.SEARCH_ERROR,
            hits=(),
            requires_clinical_review=True,
            abstain_reason=(
                "가이드라인 검색 중 오류가 발생했습니다. "
                "가짜 근거를 생성하지 말고 의료진 확인으로 보류하세요."
            ),
            error_detail=f"{type(exc).__name__}: {exc}",
        )

    if not hits:
        return SafeRetrievalResult(
            status=RetrievalStatus.NO_EVIDENCE,
            hits=(),
            requires_clinical_review=True,
            abstain_reason=(
                "승인 가이드라인에서 관련 근거를 찾지 못했습니다. "
                "근거 없는 처방 항목 생성을 중단하고 의료진 확인을 요청하세요."
            ),
        )

    return SafeRetrievalResult(
        status=RetrievalStatus.FOUND,
        hits=hits,
        requires_clinical_review=False,
    )


class CitationStatus(StrEnum):
    """추천 항목 `EvidenceRef`의 원문 색인 검증 상태."""

    VERIFIED_OFFICIAL = "verified_official"
    UNVERIFIED_OR_MOCK = "unverified_or_mock"
    INDEX_UNAVAILABLE = "index_unavailable"


@dataclass(frozen=True)
class CitationCheck:
    """단일 `EvidenceRef`에 대한 역추적 검증 결과."""

    doc_id: str
    section: str
    status: CitationStatus
    is_official_verified: bool
    resolved_source_url: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class CitationAuditReport:
    """추천 항목 전체 인용 목록의 무결성 감사 결과."""

    checks: tuple[CitationCheck, ...]
    verified_count: int
    unverified_count: int
    all_verified: bool
    can_display_as_official: bool


async def verify_evidence_refs(
    refs: Sequence[EvidenceRef],
    search: GuidelineSearch,
    *,
    version_id: str | None = None,
) -> CitationAuditReport:
    """`EvidenceRef` 목록을 활성 승인 색인에서 역조회해 공식 근거 표시 가능 여부를 판정한다.

    - `FakeGuidelineSearch`처럼 `resolve_evidence`가 없는 구현이면 `INDEX_UNAVAILABLE`로 분류해
      모의 인용(`R20`, `R23` 등)이 공식 근거로 표시되지 않도록 차단한다.
    - 실제 검색기에서 역조회 결과가 `None`이면 `UNVERIFIED_OR_MOCK`으로 분류한다.
    """
    resolver = getattr(search, "resolve_evidence", None)
    if not callable(resolver):
        checks = tuple(
            CitationCheck(
                doc_id=ref.doc_id,
                section=ref.section,
                status=CitationStatus.INDEX_UNAVAILABLE,
                is_official_verified=False,
                reason=(
                    "원문 역조회(resolve_evidence)를 지원하지 않는 검색기(예: Fake) — "
                    "공식 근거 표시 불가"
                ),
            )
            for ref in refs
        )
        return CitationAuditReport(
            checks=checks,
            verified_count=0,
            unverified_count=len(checks),
            all_verified=False,
            can_display_as_official=False,
        )

    sig = inspect.signature(resolver)
    supports_version = "version_id" in sig.parameters

    results: list[CitationCheck] = []
    verified_count = 0
    for ref in refs:
        try:
            if supports_version and version_id is not None:
                resolved = await resolver(ref.doc_id, ref.section, version_id=version_id)
            else:
                resolved = await resolver(ref.doc_id, ref.section)
        except Exception as exc:
            results.append(
                CitationCheck(
                    doc_id=ref.doc_id,
                    section=ref.section,
                    status=CitationStatus.INDEX_UNAVAILABLE,
                    is_official_verified=False,
                    reason=f"색인 역조회 오류 ({type(exc).__name__}): {exc}",
                )
            )
            continue

        if resolved is None:
            results.append(
                CitationCheck(
                    doc_id=ref.doc_id,
                    section=ref.section,
                    status=CitationStatus.UNVERIFIED_OR_MOCK,
                    is_official_verified=False,
                    reason=(
                        "활성 승인 색인에 존재하지 않는 인용 ID "
                        "(모의 카드 또는 미검증 ID) — 공식 근거 표시 금지"
                    ),
                )
            )
        else:
            verified_count += 1
            results.append(
                CitationCheck(
                    doc_id=ref.doc_id,
                    section=ref.section,
                    status=CitationStatus.VERIFIED_OFFICIAL,
                    is_official_verified=True,
                    resolved_source_url=resolved.source_url,
                )
            )

    total = len(results)
    unverified_count = total - verified_count
    all_verified = total > 0 and unverified_count == 0
    return CitationAuditReport(
        checks=tuple(results),
        verified_count=verified_count,
        unverified_count=unverified_count,
        all_verified=all_verified,
        can_display_as_official=all_verified,
    )
