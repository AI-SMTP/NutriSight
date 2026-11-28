/**
 * 제출 요청 순번 훅(`docs/specs/frontend-shell-upload.md` '제출과 잠금 규칙'의 요청 대상 고정).
 *
 * - `submit(target, run, handlers)`는 대상(날짜·끼니, ②는 환자와 `meal_order_id`)과 고른 사진을 얼린
 *   요청 객체로 고정해 `run`에 넘기고 요청 순번을 올린다. 요청 중에는 `busy`이며 새 제출을 받지 않는다.
 * - 응답은 현재 요청 순번과 같고 컴포넌트가 마운트된 상태일 때만 반영한다. 화면을 떠난 뒤 도착한
 *   성공·실패 응답은 상태도 바꾸지 않고 `handlers`도 부르지 않는다.
 * - 실패는 `ApiError.kind`로 남긴다(안내 문구는 화면이 고른다). `ApiError`가 아닌 실패는 `server`다.
 * - 성공 뒤 로컬 제출 완료 잠금·재조회는 `onSuccess`에서 `useMealQuery`의 `markSubmitted`·`refetch`로 한다.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, type ApiErrorKind } from "../../api/provisional";

export interface SubmitHandlers<T, R> {
  /** 현재 요청이 성공했을 때(마운트된 동안만) */
  onSuccess?: (result: R, request: Readonly<T>) => void;
  /** 현재 요청이 실패했을 때(마운트된 동안만) */
  onError?: (error: unknown, request: Readonly<T>) => void;
}

export interface Submission {
  /** 요청이 진행 중인지 */
  busy: boolean;
  /** 마지막 요청의 실패 분류. 성공했거나 새 요청을 시작하면 `null` */
  error: ApiErrorKind | null;
  /** 요청을 보낸다. 이미 요청 중이면 보내지 않고 `false`를 돌려준다 */
  submit: <T extends object, R>(
    target: T,
    run: (request: Readonly<T>) => Promise<R>,
    handlers?: SubmitHandlers<T, R>,
  ) => boolean;
  /** 오류 표시를 지운다(요청이 없을 때 선택을 바꾸면 화면이 부른다) */
  clearError: () => void;
}

interface SubmissionState {
  busy: boolean;
  error: ApiErrorKind | null;
}

const IDLE: SubmissionState = { busy: false, error: null };

function errorKind(error: unknown): ApiErrorKind {
  return error instanceof ApiError ? error.kind : "server";
}

/**
 * 요청 번호표. `begin()`은 요청 중이면 `null`, 아니면 새 번호를 준다. `finish(seq)`는 그 번호가 아직
 * 현재 번호면 요청 중 표시를 풀고 `true`를 돌려준다. 언마운트하면 번호를 올려 모든 응답을 낡게 만든다.
 */
function useRequestTicket() {
  const seqRef = useRef(0);
  const pendingRef = useRef(false);

  useEffect(
    () => () => {
      seqRef.current += 1;
      pendingRef.current = false;
    },
    [],
  );

  const begin = useCallback((): number | null => {
    if (pendingRef.current) return null;
    pendingRef.current = true;
    seqRef.current += 1;
    return seqRef.current;
  }, []);

  const finish = useCallback((seq: number): boolean => {
    if (seq !== seqRef.current) return false;
    pendingRef.current = false;
    return true;
  }, []);

  return { begin, finish };
}

export function useSubmission(): Submission {
  const [state, setState] = useState<SubmissionState>(IDLE);
  const { begin, finish } = useRequestTicket();

  const submit = useCallback(
    <T extends object, R>(
      target: T,
      run: (request: Readonly<T>) => Promise<R>,
      handlers: SubmitHandlers<T, R> = {},
    ): boolean => {
      const seq = begin();
      if (seq === null) return false;
      const request: Readonly<T> = Object.freeze({ ...target });
      setState({ busy: true, error: null });
      run(request).then(
        (result) => {
          if (!finish(seq)) return;
          setState(IDLE);
          handlers.onSuccess?.(result, request);
        },
        (error: unknown) => {
          if (!finish(seq)) return;
          setState({ busy: false, error: errorKind(error) });
          handlers.onError?.(error, request);
        },
      );
      return true;
    },
    [begin, finish],
  );

  const clearError = useCallback(() => {
    setState((current) => (current.error === null ? current : { ...current, error: null }));
  }, []);

  return { ...state, submit, clearError };
}
