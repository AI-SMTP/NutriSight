/**
 * 화면 ① 문구. `docs/specs/frontend-shell-upload.md` '기준 사진 화면'에 있는 문구(재업로드 확인 시트 본문)는 그대로 쓴다.
 * 조회 상태 안내와 업로드 공통 오류는 `features/shared/messages.ts`에 있다.
 * 업로드 오류 문구의 출처:
 * - 404·413·422·네트워크: 화면 ①② 공통 업로드 오류로 제안한 문구다(참조 문서 '오류 안내 문구').
 * - 409·500(기준 사진 업로드 계약 밖의 실패): 이 화면에서 새로 제안한 문구다.
 */
import { uploadErrorMessages } from "../shared/messages";

/** 업로드 성공 직후의 일시 안내(등록 상태 표시와 별개) */
export const BASELINE_REGISTERED = "기준 사진 등록됨";

/** 이미 등록된 끼니에 다시 올릴 때의 확인 시트(참조 문서 '기준 사진 화면' 6번) */
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

/** 기준 사진 업로드 계약에 없는 실패(409·500 등)의 안내(이 화면의 제안) */
const UPLOAD_FAILED = "기준 사진을 올리지 못했습니다. 다시 시도해 주세요";

/** 업로드 실패 분류별 안내 */
export const uploadErrorMessage = uploadErrorMessages({
  conflict: UPLOAD_FAILED,
  server: UPLOAD_FAILED,
});
