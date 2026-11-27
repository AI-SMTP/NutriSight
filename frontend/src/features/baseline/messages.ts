/**
 * 화면 ① 문구. 스펙 3.5절에 있는 문구(조회 상태 안내, 재업로드 확인 시트 본문)는 그대로 쓴다.
 * 업로드 오류 문구의 출처:
 * - 404·413·422·네트워크: 계획 Story 15 완료 기준이 제안한 문구다(404·413은 스펙 3.3절과도 같다).
 * - 409·500(기준 사진 업로드 계약 밖의 실패): 계획에도 없어 이 화면에서 새로 제안한 문구다.
 */
import type { ApiErrorKind } from "../../api/provisional";

/** 업로드 성공 직후의 일시 안내(등록 상태 표시와 별개) */
export const BASELINE_REGISTERED = "기준 사진 등록됨";

/** 이미 등록된 끼니에 다시 올릴 때의 확인 시트(스펙 3.5절 화면 ① 3번) */
export const RESUBMIT_SHEET = {
  title: "기준 사진을 다시 올릴까요?",
  message:
    "다시 올리면 이 끼니의 식후 사진을 모두 새 기준으로 다시 분석합니다(분석 중인 사진은 끝난 뒤 다시 분석). 사진 없이 기록한 끼니는 그대로입니다",
  confirmLabel: "다시 올리기",
} as const;

/** 촬영 안내 두 줄(수직 촬영, 수저·손이 칸을 가리지 않게) */
export const SHOOTING_GUIDE: readonly string[] = [
  "식판 바로 위에서 수직으로 찍어 주세요",
  "수저나 손이 칸을 가리지 않게 해 주세요",
];

/** 조회 상태 안내(스펙 3.5절 공통) */
export const VIEW_MESSAGES = {
  demoDateFailed: "시연일을 불러오지 못했습니다",
  noPlan: "이 날짜·끼니의 배식 계획이 없습니다",
  unreachable: "서버에 연결할 수 없습니다",
  refreshFailed: "목록을 새로 고치지 못했습니다",
  loading: "불러오는 중…",
  retry: "다시 시도",
} as const;

/** 기준 사진 업로드 계약에 없는 실패(409·500 등)의 안내(이 화면의 제안) */
const UPLOAD_FAILED = "기준 사진을 올리지 못했습니다. 다시 시도해 주세요";

const UPLOAD_ERRORS: Readonly<Record<ApiErrorKind, string>> = {
  not_found: "대상을 찾을 수 없습니다. 목록을 새로 고칩니다",
  too_large: "사진이 너무 큽니다",
  invalid: "사진을 확인할 수 없습니다. 다른 사진을 골라 주세요",
  network: "서버에 연결할 수 없습니다. 다시 시도해 주세요",
  conflict: UPLOAD_FAILED,
  server: UPLOAD_FAILED,
};

/** 업로드 실패 분류별 안내. 상태 코드 분류만 보고 서버 본문(`detail`)은 보지 않는다 */
export function uploadErrorMessage(kind: ApiErrorKind): string {
  return UPLOAD_ERRORS[kind];
}
