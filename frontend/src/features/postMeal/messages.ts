/**
 * 화면 ② 문구.
 * - 스펙에 있는 문구: 기준 사진 안내 두 가지(2절 완료 기준), "이미 기록 중이거나 기록된 끼니입니다"(3.5절 임시 규칙),
 *   409 공통 안내(3.3절). 404·413·422·네트워크는 화면 ①과 같은 `COMMON_UPLOAD_ERRORS`를 쓴다.
 * - 이 화면에서 새로 제안한 문구(제안): 성공 안내 "<환자> 식후 사진을 올렸습니다", 500 등 계약 밖 실패
 *   "식후 사진을 올리지 못했습니다. 다시 시도해 주세요", 현황 제목 "업로드 현황", 환자를 고르기 전 업로드
 *   버튼 "식후 사진 업로드"와 안내 "환자를 고르세요".
 */
import { uploadErrorMessages } from "../shared/messages";

/** 기준 사진 안내(스펙 2절 완료 기준) */
export const BASELINE_GUIDE = {
  ready: "기준 사진 등록됨",
  missing: "기준 사진이 아직 없어요. 지금 올려도 기준 사진이 등록되면 자동으로 분석해요.",
} as const;

/** 처리 중·완료 환자를 골랐을 때(스펙 3.5절 업로드·전량 기록 임시 규칙) */
export const NOT_RECORDABLE = "이미 기록 중이거나 기록된 끼니입니다";

/** 환자를 고르기 전 안내(제안) */
export const PICK_PATIENT = "환자를 고르세요";

/** 업로드 현황 제목(제안). 환자 목록의 이름이기도 하다 */
export const ORDERS_TITLE = "업로드 현황";

/** 409 공통 안내(스펙 3.3절). 전량 기록(Story 17)도 같은 문구를 쓴다 */
export const CONFLICT_MESSAGE =
  "이 끼니는 지금 기록할 수 없습니다(식사가 나가지 않거나 이미 기록 중·기록됨). 목록을 확인하세요";

/** 업로드 버튼 문구. 환자를 고르기 전에는 이름 없이 쓴다(제안) */
export function uploadLabel(displayName: string | null): string {
  return displayName === null ? "식후 사진 업로드" : `${displayName} 식후 사진 업로드`;
}

/** 업로드 성공 안내(제안) */
export function uploadedNotice(displayName: string): string {
  return `${displayName} 식후 사진을 올렸습니다`;
}

/** 식후 사진 업로드 계약에 없는 실패(500 등)의 안내(제안) */
const UPLOAD_FAILED = "식후 사진을 올리지 못했습니다. 다시 시도해 주세요";

/** 업로드 실패 분류별 안내 */
export const uploadErrorMessage = uploadErrorMessages({
  conflict: CONFLICT_MESSAGE,
  server: UPLOAD_FAILED,
});
