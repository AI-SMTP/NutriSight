// 화면 ② 배지·현황 규칙 (순수 함수).
// 정본: 스펙 3.5절 화면 ② 배지 표, data-model.md 5절 "② 요양보호사 화면" 열.
// 필드 이름·값은 data-model.md의 meal_orders·photos를 따른다.

/** 배지 계산에 필요한 발주 필드만 담은 구조 타입. API 응답 타입이 구조적으로 만족한다. */
export interface OrderStatusInput {
  /** `ordered` / `npo` / `cancelled` */
  order_status: string;
  /** `not_recorded` / `pending` / `recorded` / `not_determinable` / `failed` */
  record_status: string;
  /** `refused` / `not_eaten` / null */
  staff_zero_reason: string | null;
  /** 발주에 현재 연결된 식후 사진. 상태는 photos.status 값 */
  post_photo: { status: string } | null;
}

export type BadgeKind =
  "npo" | "cancelled" | "done" | "retake" | "waiting_baseline" | "processing" | "not_recorded";

export interface OrderBadge {
  kind: BadgeKind;
  label: string;
  /** 환자 목록에서 고를 수 있는지. 금식·취소만 고를 수 없다 */
  selectable: boolean;
}

/** 전량 기록 사유별 문구. 프로토타입 속성(`constructor` 등)이 잡히지 않도록 Map을 쓴다 */
const STAFF_ZERO_LABELS: ReadonlyMap<string, string> = new Map([
  ["refused", "완료 · 전량 거부"],
  ["not_eaten", "완료 · 전량 미섭취"],
]);

/** 5행(처리 중)에 해당하는 사진 상태 */
const PROCESSING_PHOTO_STATUSES: ReadonlySet<string> = new Set([
  "uploaded",
  "queued",
  "analyzing",
  "failed",
]);

/** 5행(처리 중)에 해당하는 기록 상태 */
const PROCESSING_RECORD_STATUSES: ReadonlySet<string> = new Set(["pending", "failed"]);

/** 업로드·전량 기록을 허용하는 배지 (스펙 3.5절 임시 규칙) */
const RECORDABLE_KINDS: ReadonlySet<BadgeKind> = new Set(["not_recorded", "retake"]);

function makeBadge(kind: BadgeKind, label: string, selectable = true): OrderBadge {
  return { kind, label, selectable };
}

/** 발주 하나의 배지. 배지 표를 위에서부터 보고 처음 맞는 행을 쓴다 */
export function orderBadge(order: OrderStatusInput): OrderBadge {
  const photoStatus = order.post_photo?.status ?? null;

  // 1행: 발주 상태
  if (order.order_status === "npo") return makeBadge("npo", "금식", false);
  if (order.order_status === "cancelled") return makeBadge("cancelled", "취소", false);

  // 2행: 기록 완료(전량 기록이면 사유를 붙인다)
  if (order.record_status === "recorded") {
    const reason = order.staff_zero_reason;
    const label = (reason !== null && STAFF_ZERO_LABELS.get(reason)) || "완료";
    return makeBadge("done", label);
  }

  // 3행: 판단 불가
  if (order.record_status === "not_determinable" || photoStatus === "not_determinable") {
    return makeBadge("retake", "재촬영 필요");
  }

  // 4행: 기준 사진 대기
  if (photoStatus === "waiting_baseline") {
    return makeBadge("waiting_baseline", "처리 중 · 기준 사진 대기");
  }

  // 5행: 처리 중(실패 재시도는 화면 ④에서 한다)
  if (
    (photoStatus !== null && PROCESSING_PHOTO_STATUSES.has(photoStatus)) ||
    PROCESSING_RECORD_STATUSES.has(order.record_status)
  ) {
    return makeBadge("processing", "처리 중");
  }

  // 6행: 그 밖
  return makeBadge("not_recorded", "미기록");
}

/** 식후 사진 업로드와 전량 거부·미섭취 기록을 허용하는지 */
export function canRecord(badge: OrderBadge): boolean {
  return RECORDABLE_KINDS.has(badge.kind);
}

/**
 * 현황 머리글 "완료 x / y · 금식 n".
 * y = ordered 발주 수, x = 그중 recorded 수, n = npo 수.
 * cancelled는 분모에서 빼고 머리글에 표시하지 않는다(팀 제안안).
 * data-model.md 357행은 금식·취소를 "따로 센다"고 적지만, 머리글에서 취소를 표시하지 않는 것은 팀 제안안이다.
 */
export function summarizeOrders(orders: readonly OrderStatusInput[]): string {
  const ordered = orders.filter((o) => o.order_status === "ordered");
  const done = ordered.filter((o) => o.record_status === "recorded").length;
  const npo = orders.filter((o) => o.order_status === "npo").length;
  return `완료 ${done} / ${ordered.length} · 금식 ${npo}`;
}
