/**
 * 모의 처리 단계의 상태 전이(순수 함수). 받은 상태를 고치지 않고 새 상태를 돌려준다.
 *
 * - 정본: 스펙 3.4절(처리 단계 순서, 기준 사진 최초 등록·교체 규칙, 사진 상태 ↔ `record_status` 대응),
 *   시스템 구조 4절 상태 표, 8-1절 `photo.status_changed` 데이터.
 * - 단계: `uploaded → queued → analyzing(intake) → analyzing(nutrition) → analyzing(alert) → done`.
 *   `recommendation` 단계는 경고 수준이 오를 때만 있으므로 모의에서는 거치지 않는다.
 * - 모의 결과가 `not_determinable`·`failed`면 섭취 추정(`intake`) 단계에서 끝난다(시스템 구조 4절:
 *   사진 전체 판단 불가는 섭취 추정 단계에서 끝남. 실패는 모의 단순화로 같은 단계에 둔다).
 */
import type {
  PhotoStage,
  PhotoStatus,
  PhotoStatusChangedEvent,
  RecordStatus,
} from "../api/provisional";
import { findPhoto } from "./operations";
import type { MockPhoto, MockState } from "./types";

/** 식후 사진 처리의 최종 결과(테스트가 주입) */
export type MockResult = "done" | "not_determinable" | "failed";

export interface Step {
  readonly status: PhotoStatus;
  readonly stage: PhotoStage | null;
}

export const QUEUED: Step = { status: "queued", stage: null };

const TERMINAL: ReadonlySet<PhotoStatus> = new Set<PhotoStatus>([
  "done",
  "not_determinable",
  "failed",
]);

export function isTerminal(status: PhotoStatus): boolean {
  return TERMINAL.has(status);
}

/** 분석 중 사진의 다음 단계 */
function nextAnalyzing(stage: PhotoStage | null, result: MockResult): Step {
  if (stage === "intake") {
    return result === "done"
      ? { status: "analyzing", stage: "nutrition" }
      : { status: result, stage: "intake" };
  }
  if (stage === "nutrition") return { status: "analyzing", stage: "alert" };
  return { status: "done", stage: "alert" };
}

/** 다음 단계. 진행할 단계가 없는 상태(`waiting_baseline`·종료 상태)면 `null` */
export function nextStep(photo: MockPhoto, result: MockResult): Step | null {
  switch (photo.status) {
    case "uploaded":
      return QUEUED;
    case "queued":
      return { status: "analyzing", stage: "intake" };
    case "analyzing":
      return nextAnalyzing(photo.stage, result);
    default:
      return null;
  }
}

/** 수동 모드 정지 지점(첫 `analyzing(intake)`)인지 */
export function isManualStop(photo: MockPhoto): boolean {
  return photo.status === "analyzing" && photo.stage === "intake";
}

/** 사진 상태 → 발주 `record_status` (시스템 구조 4절 표) */
export function recordStatusFor(status: PhotoStatus): RecordStatus {
  switch (status) {
    case "done":
      return "recorded";
    case "not_determinable":
      return "not_determinable";
    case "failed":
      return "failed";
    default:
      return "pending";
  }
}

/**
 * 사진을 `step`으로 바꾸고, 그 사진이 지금 연결된 발주(`post_photo_id`)의 `record_status`도 함께 바꾼다.
 * 연결이 끊긴 사진(재촬영·전량 기록)이면 발주는 그대로 둔다.
 */
export function applyStep(state: MockState, photoId: string, step: Step): MockState {
  const recordStatus = recordStatusFor(step.status);
  return {
    ...state,
    photos: state.photos.map((p) =>
      p.photo_id === photoId ? { ...p, status: step.status, stage: step.stage } : p,
    ),
    orders: state.orders.map((o) =>
      o.post_photo_id === photoId ? { ...o, record_status: recordStatus } : o,
    ),
  };
}

/** 식후 사진의 `photo.status_changed` 데이터. `outcome`은 `done`에만 붙인다 */
export function postPhotoEvent(
  state: MockState,
  photo: MockPhoto,
  at: string,
): PhotoStatusChangedEvent {
  const order = state.orders.find((o) => o.meal_order_id === photo.meal_order_id);
  const event: PhotoStatusChangedEvent = {
    photo_id: photo.photo_id,
    kind: "post",
    patient_id: order?.patient_id ?? null,
    meal_plan_id: photo.meal_plan_id,
    meal_order_id: photo.meal_order_id,
    status: photo.status,
    stage: photo.stage,
    at,
  };
  return photo.status === "done" ? { ...event, outcome: "no_change" } : event;
}

/** 기준 사진 저장 직후의 이벤트(스펙 3.4절, 시스템 구조 3-1절 4단계) */
export function baselineEvent(photo: MockPhoto, at: string): PhotoStatusChangedEvent {
  return {
    photo_id: photo.photo_id,
    kind: "baseline",
    meal_plan_id: photo.meal_plan_id,
    patient_id: null,
    meal_order_id: null,
    status: "uploaded",
    stage: null,
    at,
  };
}

/** 기준 사진 등록으로 다시 처리할 사진. `restart`는 지금 `queued`부터, `reserve`는 지금 처리 뒤 한 번 더 */
export interface ReprocessTargets {
  readonly restart: readonly string[];
  readonly reserve: readonly string[];
}

const RESTART_ON_FIRST: ReadonlySet<PhotoStatus> = new Set<PhotoStatus>(["waiting_baseline"]);
const RESTART_ON_REPLACE: ReadonlySet<PhotoStatus> = new Set<PhotoStatus>([
  "done",
  "not_determinable",
  "failed",
  "waiting_baseline",
]);
const RESERVE_ON_REPLACE: ReadonlySet<PhotoStatus> = new Set<PhotoStatus>(["queued", "analyzing"]);

/**
 * 기준 사진 등록 때 다시 처리할 식후 사진을 고른다. 대상은 그 끼니에서 전량 기록(`staff_zero_reason`)이
 * 없고 현재 연결된 식후 사진이 있는 발주의 사진이다.
 * - 최초 등록: `waiting_baseline` 사진만 `restart`.
 * - 교체: `done`·`not_determinable`·`failed`·`waiting_baseline`은 `restart`, `queued`·`analyzing`은 `reserve`.
 */
export function reprocessTargets(
  state: MockState,
  mealPlanId: string,
  replaced: boolean,
): ReprocessTargets {
  const linked = state.orders
    .filter((o) => o.meal_plan_id === mealPlanId && o.staff_zero_reason === null)
    .flatMap((o) => findPhoto(state, o.post_photo_id) ?? []);
  const pick = (statuses: ReadonlySet<PhotoStatus>) =>
    linked.filter((p) => statuses.has(p.status)).map((p) => p.photo_id);
  if (!replaced) {
    return { restart: pick(RESTART_ON_FIRST), reserve: [] };
  }
  return { restart: pick(RESTART_ON_REPLACE), reserve: pick(RESERVE_ON_REPLACE) };
}
