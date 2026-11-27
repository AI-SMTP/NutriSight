/**
 * 끼니 조회 훅(`useMealQuery`)의 상태와 상태 전이 순수 함수.
 *
 * - 조회 결과 반영: 성공은 `ready`, 404는 `no_plan`, 그 밖의 실패는 보여 줄 데이터가 있으면
 *   `refreshError`(스펙 3.5절 나), 없으면 `unreachable`(가)이다.
 * - 로컬 제출 완료 잠금: 대상 키마다 (그 순간의 선택, 그 순간의 마지막 조회 순번)을 남긴다.
 *   같은 선택에서 그 순번보다 뒤에 보낸 조회가 성공해 반영될 때만 지운다.
 * - 제출 성공 안내(`submitNotice`)와 잠금은 선택 전환·조회 실패와 관계없이 유지된다.
 */
import { ApiError, type MealDetail } from "../../api/provisional";

export type MealView = "loading" | "ready" | "no_plan" | "unreachable";

/** 로컬 제출 완료 표시. `seq`는 표시한 순간의 마지막 조회 순번이다 */
export interface SubmitLock {
  selectionKey: string | null;
  seq: number;
}

export interface MealQueryState {
  /** 이 상태가 가리키는 선택(`meal_plan_id`). 선택이 준비되지 않았으면 `null` */
  selectionKey: string | null;
  data: MealDetail | null;
  view: MealView;
  refreshError: boolean;
  locks: ReadonlyMap<string, SubmitLock>;
  submitNotice: string | null;
}

export type FetchOutcome = { ok: true; data: MealDetail } | { ok: false; error: unknown };

export const INITIAL_STATE: MealQueryState = {
  selectionKey: null,
  data: null,
  view: "loading",
  refreshError: false,
  locks: new Map(),
  submitNotice: null,
};

/** 선택을 바꾼다. 이전 끼니 데이터는 지우고 잠금·성공 안내는 남긴다 */
export function selectMeal(state: MealQueryState, selectionKey: string | null): MealQueryState {
  return { ...state, selectionKey, data: null, view: "loading", refreshError: false };
}

/** 그 선택에서 `seq`보다 앞서 표시된 잠금을 지운다 */
function releaseLocks(
  locks: ReadonlyMap<string, SubmitLock>,
  selectionKey: string,
  seq: number,
): ReadonlyMap<string, SubmitLock> {
  const kept = [...locks].filter(
    ([, lock]) => !(lock.selectionKey === selectionKey && lock.seq < seq),
  );
  return kept.length === locks.size ? locks : new Map(kept);
}

/**
 * 최신 조회(`seq`)의 결과를 반영한다. 결과가 다른 선택의 것이면 그대로 둔다.
 * 순번이 최신인지는 호출자가 먼저 확인한다.
 */
export function applyOutcome(
  state: MealQueryState,
  selectionKey: string,
  seq: number,
  outcome: FetchOutcome,
): MealQueryState {
  if (state.selectionKey !== selectionKey) return state;
  if (outcome.ok) {
    return {
      ...state,
      data: outcome.data,
      view: "ready",
      refreshError: false,
      locks: releaseLocks(state.locks, selectionKey, seq),
    };
  }
  if (outcome.error instanceof ApiError && outcome.error.kind === "not_found") {
    return { ...state, data: null, view: "no_plan", refreshError: false };
  }
  if (state.data !== null) return { ...state, refreshError: true };
  return { ...state, view: "unreachable", refreshError: false };
}

/** 대상을 로컬 제출 완료로 표시하고 성공 안내를 남긴다 */
export function markSubmitted(
  state: MealQueryState,
  targetKey: string,
  lock: SubmitLock,
  notice: string,
): MealQueryState {
  return { ...state, locks: new Map([...state.locks, [targetKey, lock]]), submitNotice: notice };
}
