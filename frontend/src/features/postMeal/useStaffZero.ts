/**
 * 화면 ② "사진 없이 기록"(전량 거부·전량 미섭취) 흐름(스펙 3.5절 화면 ② 5번, 3.3절 staff-zero 계약).
 *
 * - `open(reason)`은 지금 고른 발주로 요청 객체를 만들어 확인 시트에 띄운다(요청은 아직 보내지 않는다).
 *   대상(날짜·끼니·환자·`meal_order_id`)은 이때 고정한다.
 * - `confirm()`은 시트를 닫고, 그 사이 조회 결과가 바뀌어 기록할 수 없게 됐으면(처리 중으로 바뀜, 다른 발주 등)
 *   요청하지 않는다. 기록할 수 있으면 공용 `useUploadFlow.start`로 `recordStaffZero`를 보낸다. 업로드와 같은
 *   `submission`을 쓰므로 두 요청은 함께 막힌다.
 * - 200이면 그 발주(`meal_order_id`)를 로컬 제출 완료로 잠그고 성공 안내를 남긴 뒤 다시 읽는다. 404·409면
 *   그 끼니를 다시 읽는다(스펙 3.3절). 전량 기록은 사진 이벤트를 만들지 않으므로 SSE를 기다리지 않는다.
 * - 시트는 확인 즉시 닫는다(화면 ①의 재업로드 시트와 같다). 요청 중에는 업로드 영역 제목이 포커스를 받는다.
 */
import { useState } from "react";

import {
  recordStaffZero,
  type ApiErrorKind,
  type Meal,
  type MealOrderSummary,
  type StaffZeroReason,
} from "../../api/provisional";
import type { SubmitTarget, UploadFlow, UploadOptions } from "../shared/useUploadFlow";
import { staffZeroNotice } from "./messages";

/** 전량 기록 요청 객체(확인 시트를 열 때 고정한다) */
export interface StaffZeroRequest extends SubmitTarget {
  mealOrderId: string;
  displayName: string;
  reason: StaffZeroReason;
}

/** 성공하면 그 발주를 잠그고, 404·409면 다시 읽는다 */
const STAFF_ZERO_SUBMIT: UploadOptions<StaffZeroRequest> = {
  lockKey: (request) => request.mealOrderId,
  notice: (request) => staffZeroNotice(request),
  refetchOn: new Set<ApiErrorKind>(["not_found", "conflict"]),
};

function sendStaffZero(request: Readonly<StaffZeroRequest>) {
  return recordStaffZero(request.mealOrderId, request.reason);
}

export interface StaffZeroArgs {
  flow: UploadFlow;
  date: string | null;
  meal: Meal;
  /** 고른 환자의 발주(고를 수 있는 것만) */
  order: MealOrderSummary | null;
  /** 지금 전량 기록을 막는지 */
  disabled: boolean;
  /** 요청을 보내기 직전에 부른다(화면이 실패 안내를 어느 요청의 것으로 볼지 정한다) */
  onStart: () => void;
}

export interface StaffZeroControls {
  /** 확인 시트에 띄운 요청. 시트가 닫혀 있으면 `null` */
  pending: StaffZeroRequest | null;
  /** 전량 기록 버튼: 확인 시트를 연다 */
  open: (reason: StaffZeroReason) => void;
  /** 확인 시트의 기록 버튼 */
  confirm: () => void;
  /** 확인 시트의 취소 버튼·Escape */
  cancel: () => void;
}

export function useStaffZero(args: StaffZeroArgs): StaffZeroControls {
  const { flow, date, meal, order, disabled } = args;
  const [pending, setPending] = useState<StaffZeroRequest | null>(null);

  const open = (reason: StaffZeroReason) => {
    if (disabled || date === null || order === null) return;
    const { meal_order_id: mealOrderId, display_name: displayName } = order;
    setPending({ date, meal, mealOrderId, displayName, reason });
  };

  const confirm = () => {
    setPending(null);
    const stillTarget = pending !== null && order?.meal_order_id === pending.mealOrderId;
    if (!stillTarget || disabled) return;
    args.onStart();
    flow.start(pending, sendStaffZero, STAFF_ZERO_SUBMIT);
  };

  return { pending, open, confirm, cancel: () => setPending(null) };
}
