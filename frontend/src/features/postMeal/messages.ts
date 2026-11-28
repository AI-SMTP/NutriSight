/**
 * 화면 ② 문구.
 * - 설계 단계에서 정한 문구(`docs/specs/frontend-shell-upload.md`): 기준 사진 안내 두 가지('식후 사진 화면' 2번),
 *   "이미 기록 중이거나 기록된 끼니입니다"('제출과 잠금 규칙'의 임시 규칙), 409 공통 안내('오류 안내 문구'). 404·413·422·네트워크는 화면 ①과 같은 `COMMON_UPLOAD_ERRORS`를 쓴다.
 * - 이 화면에서 새로 제안한 문구(제안): 성공 안내 "<환자> 식후 사진을 올렸습니다", 500 등 계약 밖 실패
 *   "식후 사진을 올리지 못했습니다. 다시 시도해 주세요", 현황 제목 "업로드 현황", 환자를 고르기 전 업로드
 *   버튼 "식후 사진 업로드"와 안내 "환자를 고르세요".
 * - 전량 기록: 묶음 이름 "사진 없이 기록"·버튼 "전량 거부"·"전량 미섭취"·시트 본문 "<환자> <끼니>을 전량 거부로
 *   기록합니다"는 참조 문서 '식후 사진 화면' 6번 문구다. 시트 제목 "사진 없이 기록할까요?"·확인 버튼 "기록하기",
 *   성공 안내 "<환자> <끼니>을 전량 거부로 기록했습니다", 계약 밖 실패 "전량 기록을 하지 못했습니다. 다시 시도해
 *   주세요"는 제안이다. 404·409·네트워크는 업로드와 같은 문구를 쓴다.
 */
import type { ApiErrorKind, Meal, StaffZeroReason } from "../../api/provisional";
import { uploadErrorMessages } from "../shared/messages";
import { MEAL_LABELS } from "../shared/meals";

/** 기준 사진 안내(참조 문서 '식후 사진 화면' 2번) */
export const BASELINE_GUIDE = {
  ready: "기준 사진 등록됨",
  missing: "기준 사진이 아직 없어요. 지금 올려도 기준 사진이 등록되면 자동으로 분석해요.",
} as const;

/** 처리 중·완료 환자를 골랐을 때(참조 문서 '제출과 잠금 규칙'의 업로드·전량 기록 임시 규칙) */
export const NOT_RECORDABLE = "이미 기록 중이거나 기록된 끼니입니다";

/** 환자를 고르기 전 안내(제안) */
export const PICK_PATIENT = "환자를 고르세요";

/** 업로드 현황 제목(제안). 환자 목록의 이름이기도 하다 */
export const ORDERS_TITLE = "업로드 현황";

/** 409 공통 안내(참조 문서 '오류 안내 문구'). 전량 기록도 같은 문구를 쓴다 */
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

/** "사진 없이 기록" 묶음 이름(참조 문서 '식후 사진 화면' 6번) */
export const STAFF_ZERO_TITLE = "사진 없이 기록";

/** 전량 기록 사유별 버튼 이름(참조 문서 '식후 사진 화면' 6번) */
export const STAFF_ZERO_LABELS: Readonly<Record<StaffZeroReason, string>> = {
  refused: "전량 거부",
  not_eaten: "전량 미섭취",
};

/** 전량 기록 확인 시트. 본문은 설계 단계 문구, 제목·확인 버튼은 제안 */
export const STAFF_ZERO_SHEET = {
  title: "사진 없이 기록할까요?",
  confirmLabel: "기록하기",
} as const;

/** 전량 기록 대상의 문구 재료 */
export interface StaffZeroSubject {
  displayName: string;
  meal: Meal;
  reason: StaffZeroReason;
}

// 조사는 낱말 끝소리를 전제로 고정해 붙인다. 시트 본문과 성공 안내가 함께 쓴다.
// - "을": 끼니 이름(아침·점심·저녁)이 모두 받침으로 끝난다.
// - "로": 사유 이름(전량 거부·전량 미섭취)이 모두 받침 없이 끝난다(받침이 있으면 "으로"). 사유나 끼니 이름을
//   바꾸면 이 전제를 다시 확인한다.
function subjectText({ displayName, meal, reason }: StaffZeroSubject): string {
  return `${displayName} ${MEAL_LABELS[meal]}을 ${STAFF_ZERO_LABELS[reason]}로`;
}

/** 확인 시트 본문("NS03 점심을 전량 거부로 기록합니다", 참조 문서 '식후 사진 화면' 6번) */
export function staffZeroConfirmMessage(subject: StaffZeroSubject): string {
  return `${subjectText(subject)} 기록합니다`;
}

/** 전량 기록 성공 안내(제안) */
export function staffZeroNotice(subject: StaffZeroSubject): string {
  return `${subjectText(subject)} 기록했습니다`;
}

/** 전량 기록 계약에 없는 실패(500·422 등)의 안내(제안) */
const STAFF_ZERO_FAILED = "전량 기록을 하지 못했습니다. 다시 시도해 주세요";

/**
 * 전량 기록 실패 분류별 안내. 업로드와 같은 `submission`을 쓰므로 문구 표를 따로 둔다.
 * 404·409·네트워크는 업로드와 같은 문구이고, 사진 관련 분류(413·422)는 이 요청에 맞지 않아 실패 안내로 묶는다.
 */
const STAFF_ZERO_ERRORS: Readonly<Record<ApiErrorKind, string>> = {
  not_found: uploadErrorMessage("not_found"),
  conflict: CONFLICT_MESSAGE,
  network: uploadErrorMessage("network"),
  too_large: STAFF_ZERO_FAILED,
  invalid: STAFF_ZERO_FAILED,
  server: STAFF_ZERO_FAILED,
};

export function staffZeroErrorMessage(kind: ApiErrorKind): string {
  return STAFF_ZERO_ERRORS[kind];
}
