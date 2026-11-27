// 모의 API의 상태 전이(순수 함수). 받은 상태를 고치지 않고 새 상태를 돌려준다.
// 허용 규칙은 스펙 3.3절(404·409 구분)과 3.5절 업로드·전량 기록 임시 규칙을 따른다.
import type {
  BaselinePhoto,
  MealDetail,
  MealOrderSummary,
  PhotoStatus,
  PostPhotoAccepted,
  StaffZeroReason,
  StaffZeroResult,
} from "../api/provisional";
import { canRecord, orderBadge } from "../lib/mealStatus";
import type { MockOrder, MockPhoto, MockPlan, MockState } from "./types";

/** 상태 전이 결과. 실패는 응답 상태 코드로 표현한다 */
export type Outcome<T> =
  { ok: true; state: MockState; value: T } | { ok: false; status: 404 | 409 };

const NOT_FOUND = { ok: false, status: 404 } as const;
const CONFLICT = { ok: false, status: 409 } as const;

export function findPlan(state: MockState, date: string, meal: string): MockPlan | undefined {
  return state.plans.find((p) => p.date === date && p.meal === meal);
}

function findPhoto(state: MockState, photoId: string | null): MockPhoto | undefined {
  return photoId === null ? undefined : state.photos.find((p) => p.photo_id === photoId);
}

/** 발주 하나를 화면 ②용 요약으로 바꾼다 */
function summarize(state: MockState, order: MockOrder): MealOrderSummary {
  const patient = state.patients.find((p) => p.patient_id === order.patient_id);
  const photo = findPhoto(state, order.post_photo_id);
  return {
    meal_order_id: order.meal_order_id,
    patient_id: order.patient_id,
    display_name: patient?.display_name ?? order.patient_id,
    room: patient?.room ?? "",
    order_status: order.order_status,
    record_status: order.record_status,
    staff_zero_reason: order.staff_zero_reason,
    post_photo: photo
      ? { photo_id: photo.photo_id, status: photo.status, stage: photo.stage }
      : null,
  };
}

/** `GET /api/meals/{date}/{meal}` 응답 본문 */
export function toMealDetail(state: MockState, plan: MockPlan): MealDetail {
  const baseline = findPhoto(state, plan.baseline_photo_id);
  return {
    meal_plan_id: plan.meal_plan_id,
    date: plan.date,
    meal: plan.meal,
    slots: [...plan.slots],
    baseline_photo: baseline
      ? { photo_id: baseline.photo_id, uploaded_at: baseline.uploaded_at }
      : null,
    orders: state.orders
      .filter((o) => o.meal_plan_id === plan.meal_plan_id)
      .map((o) => summarize(state, o)),
  };
}

/** 새 사진 ID를 받고 번호를 올린 상태를 돌려준다 */
function issuePhotoId(state: MockState): [string, MockState] {
  return [`mock_photo_${state.nextPhotoSeq}`, { ...state, nextPhotoSeq: state.nextPhotoSeq + 1 }];
}

function replaceOrder(state: MockState, next: MockOrder): MockState {
  return {
    ...state,
    orders: state.orders.map((o) => (o.meal_order_id === next.meal_order_id ? next : o)),
  };
}

/** 금식·취소가 아니고, 배지가 "미기록"·"재촬영 필요"인 발주만 기록할 수 있다 */
function isRecordable(state: MockState, order: MockOrder): boolean {
  return order.order_status === "ordered" && canRecord(orderBadge(summarize(state, order)));
}

/** 기준 식전 사진 등록(최초·교체). 대기 사진 재처리와 이벤트 발행은 처리 단계 런타임이 맡는다 */
export function registerBaseline(
  state: MockState,
  args: { date: string; meal: string; now: string },
): Outcome<BaselinePhoto> {
  const plan = findPlan(state, args.date, args.meal);
  if (!plan) return NOT_FOUND;
  const [photoId, issued] = issuePhotoId(state);
  const photo: MockPhoto = {
    photo_id: photoId,
    kind: "baseline",
    meal_plan_id: plan.meal_plan_id,
    meal_order_id: null,
    status: "uploaded",
    stage: null,
    uploaded_at: args.now,
  };
  const next: MockState = {
    ...issued,
    plans: issued.plans.map((p) =>
      p.meal_plan_id === plan.meal_plan_id ? { ...p, baseline_photo_id: photoId } : p,
    ),
    photos: [...issued.photos, photo],
  };
  return { ok: true, state: next, value: { photo_id: photoId, uploaded_at: args.now } };
}

/**
 * 식후 사진 접수. 계획·환자 없음 404, 발주 없음·금식·취소·이미 기록 중·기록됨 409.
 * 재촬영 필요 발주에 올리면 새 사진이 발주 연결을 대신하고 이전 사진 행은 남는다.
 * 기준 사진이 없는 끼니면 `waiting_baseline`, 있으면 `uploaded`에 머문다(단계 진행은 런타임 몫).
 */
export function acceptPostPhoto(
  state: MockState,
  args: { patientId: string; date: string; meal: string; now: string },
): Outcome<PostPhotoAccepted> {
  const plan = findPlan(state, args.date, args.meal);
  const patientExists = state.patients.some((p) => p.patient_id === args.patientId);
  if (!plan || !patientExists) return NOT_FOUND;
  const order = state.orders.find(
    (o) => o.meal_plan_id === plan.meal_plan_id && o.patient_id === args.patientId,
  );
  if (!order || !isRecordable(state, order)) return CONFLICT;

  const [photoId, issued] = issuePhotoId(state);
  const status: PhotoStatus = plan.baseline_photo_id === null ? "waiting_baseline" : "uploaded";
  const photo: MockPhoto = {
    photo_id: photoId,
    kind: "post",
    meal_plan_id: plan.meal_plan_id,
    meal_order_id: order.meal_order_id,
    status,
    stage: null,
    uploaded_at: args.now,
  };
  const linked: MockOrder = { ...order, record_status: "pending", post_photo_id: photoId };
  const next = replaceOrder({ ...issued, photos: [...issued.photos, photo] }, linked);
  return {
    ok: true,
    state: next,
    value: { photo_id: photoId, meal_order_id: order.meal_order_id, status },
  };
}

/**
 * 사진 없이 전량 거부·미섭취 기록. 발주 ID 없음 404, 금식·취소·이미 기록 중·기록됨 409.
 * 재촬영 필요 발주면 사진 행은 남기고 발주의 현재 사진 연결(`post_photo_id`)을 끊는다.
 */
export function recordStaffZero(
  state: MockState,
  args: { mealOrderId: string; reason: StaffZeroReason },
): Outcome<StaffZeroResult> {
  const order = state.orders.find((o) => o.meal_order_id === args.mealOrderId);
  if (!order) return NOT_FOUND;
  if (!isRecordable(state, order)) return CONFLICT;

  const recorded: MockOrder = {
    ...order,
    record_status: "recorded",
    staff_zero_reason: args.reason,
    post_photo_id: null,
  };
  return {
    ok: true,
    state: replaceOrder(state, recorded),
    value: {
      meal_order_id: order.meal_order_id,
      record_status: "recorded",
      staff_zero_reason: args.reason,
    },
  };
}
