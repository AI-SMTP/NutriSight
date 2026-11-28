/**
 * 끼니 조회 훅(`docs/specs/frontend-shell-upload.md` '끼니 조회 순서 규칙'의 번호·404·(가)·(나), '제출과 잠금 규칙'의
 * 제출 성공 뒤 재조회 실패, 'SSE 구독'의 SSE 재조회).
 *
 * - 시연일이 준비되지 않았으면(`date === null` 또는 `enabled === false`) 조회를 보내지 않는다.
 *   SSE `open`은 시연일·끼니가 준비되기 전에도 올 수 있으므로 그때의 재조회는 아무것도 하지 않는다.
 * - 모든 조회(최초·SSE 이벤트·`open`·제출 뒤·다시 시도)는 `refetch()` 하나로 보내고 보낼 때마다 순번을
 *   올린다. 성공이든 실패든 가장 마지막으로 보낸 조회의 응답만 반영한다.
 * - 날짜·끼니를 바꾸면 이전 끼니 데이터를 바로 지우고, 새 조회가 성공할 때까지 `view`는 `ready`가 아니다.
 * - 같은 끼니(`meal_plan_id`)의 `photo.status_changed`와 모든 `open`마다 다시 읽는다. `kind`는 보지 않는다.
 * - "다시 시도"는 `refetch()`만 부른다(제출 요청을 다시 보내지 않는다).
 * - 상태 전이 규칙은 `mealQueryState.ts`에 있다.
 */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

import { useSystemEvents } from "../../api/events";
import { getMeal, mealPlanId, type Meal, type MealDetail } from "../../api/provisional";
import {
  INITIAL_STATE,
  applyOutcome,
  markSubmitted as markSubmittedState,
  selectMeal,
  type FetchOutcome,
  type MealQueryState,
  type MealView,
} from "./mealQueryState";

export type { MealView } from "./mealQueryState";

export interface MealQueryOptions {
  /** 시연일(화면 ②는 항상 시연일). 아직 모르면 `null` */
  date: string | null;
  meal: Meal;
  /** `false`면 조회하지 않는다. 기본 `true` */
  enabled?: boolean;
}

export interface MealQuery {
  data: MealDetail | null;
  view: MealView;
  /** 보여 주던 데이터가 있는데 재조회가 실패했는지(참조 문서 '끼니 조회 순서 규칙'의 (나)) */
  refreshError: boolean;
  /** 현재 선택을 다시 읽는다. 선택이 준비되지 않았으면 아무것도 하지 않는다 */
  refetch: () => void;
  /**
   * 대상(①은 `meal_plan_id`, ②는 `meal_order_id`)을 로컬 제출 완료로 표시하고 성공 안내를 남긴다.
   * 제출이 성공한 직후, 재조회(`refetch`)보다 먼저 부른다.
   */
  markSubmitted: (targetKey: string, notice: string) => void;
  /** 대상이 로컬 제출 완료로 잠겨 있는지 */
  isLocked: (targetKey: string) => boolean;
  /** 제출 성공 안내. 조회 실패·선택 전환에도 유지된다 */
  submitNotice: string | null;
  clearSubmitNotice: () => void;
}

type SetQueryState = Dispatch<SetStateAction<MealQueryState>>;

/**
 * 선택(`key`)에 맞춘 상태. 선택이 바뀌었으면 이번 렌더에서 이전 끼니 데이터를 지운다
 * (이전 렌더 값으로 상태를 맞추는 패턴. 이펙트에서 지우면 한 번은 이전 데이터가 그려진다).
 */
function useSelectionState(key: string | null): [MealQueryState, SetQueryState] {
  const [stored, setState] = useState<MealQueryState>(INITIAL_STATE);
  const state = stored.selectionKey === key ? stored : selectMeal(stored, key);
  if (state !== stored) setState(state);
  return [state, setState];
}

/**
 * 늘 마지막 렌더의 `fn`을 부르는 고정 함수. 제출 성공 콜백처럼 제출 시점에 잡힌 함수가 나중에
 * 불려도 그때의 선택(날짜·끼니)으로 동작하게 한다. 커밋 직후(layout effect)에 바꿔 끼운다.
 */
function useLatestCallback<A extends unknown[]>(fn: (...args: A) => void): (...args: A) => void {
  const latest = useRef(fn);
  useLayoutEffect(() => {
    latest.current = fn;
  });
  return useCallback((...args: A) => latest.current(...args), []);
}

interface Selection {
  key: string | null;
  date: string | null;
  meal: Meal;
}

/**
 * 순번 기반 조회. `refetch()`는 보낼 때마다 순번을 올리고 마지막 순번의 응답만 반영한다.
 * 화면을 떠나면 진행 중인 조회를 취소하고 응답을 버린다. `lastSeq()`는 마지막으로 보낸 순번이다.
 */
function useLatestMealFetch({ key, date, meal }: Selection, setState: SetQueryState) {
  const seqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    return () => controller.abort();
  }, []);

  const refetch = useCallback(() => {
    if (key === null || date === null) return;
    seqRef.current += 1;
    const seq = seqRef.current;
    const signal = abortRef.current?.signal;
    const settle = (outcome: FetchOutcome) => {
      if (seq !== seqRef.current || signal?.aborted) return;
      setState((current) => applyOutcome(current, key, seq, outcome));
    };
    getMeal(date, meal, { signal }).then(
      (data) => settle({ ok: true, data }),
      (error: unknown) => settle({ ok: false, error }),
    );
  }, [key, date, meal, setState]);

  const lastSeq = useCallback(() => seqRef.current, []);
  return { refetch, lastSeq };
}

export function useMealQuery({ date, meal, enabled = true }: MealQueryOptions): MealQuery {
  const key = enabled && date !== null ? mealPlanId(date, meal) : null;
  const [state, setState] = useSelectionState(key);
  // 순서 의존: useLatestMealFetch 안의 취소 컨트롤러 이펙트가 아래 최초 조회 이펙트보다 먼저 선언돼야
  // 최초 조회에도 취소 신호가 붙는다(이펙트는 선언 순서대로 실행된다).
  const { refetch: refetchSelection, lastSeq } = useLatestMealFetch({ key, date, meal }, setState);

  useEffect(() => {
    refetchSelection();
  }, [refetchSelection]);

  // eslint-plugin-react-hooks는 커스텀 훅(useSelectionState)이 돌려준 setState를 안정 값으로 보지 않는다.
  // 그래서 useCallback 의존성에 setState를 함께 적는다(실제로는 바뀌지 않는다).
  const markSelection = useCallback(
    (targetKey: string, notice: string) => {
      const lock = { selectionKey: key, seq: lastSeq() };
      setState((current) => markSubmittedState(current, targetKey, lock, notice));
    },
    [key, lastSeq, setState],
  );
  // 밖으로 내보내는 함수는 늘 현재 선택으로 동작한다(제출 중 선택이 바뀐 뒤 불려도 안전하다)
  const refetch = useLatestCallback(refetchSelection);
  const markSubmitted = useLatestCallback(markSelection);

  useSystemEvents({
    onOpen: refetch,
    onPhotoStatusChanged: (event) => {
      if (key !== null && event.meal_plan_id === key) refetch();
    },
  });

  const clearSubmitNotice = useCallback(() => {
    setState((current) => ({ ...current, submitNotice: null }));
  }, [setState]);

  return {
    data: state.data,
    view: state.view,
    refreshError: state.refreshError,
    refetch,
    markSubmitted,
    isLocked: (targetKey) => state.locks.has(targetKey),
    submitNotice: state.submitNotice,
    clearSubmitNotice,
  };
}
