/**
 * 시연일 초기화 훅(`docs/specs/frontend-shell-upload.md` '시연일 초기화').
 *
 * - 화면 ①②는 들어오면 먼저 `GET /api/meta`로 시연일을 읽고, `ready`가 된 뒤에 끼니 조회를 시작한다.
 * - 네트워크 오류·서버 오류 모두 `error`다. `retry()`는 시연일 조회부터 다시 한다.
 * - 화면을 떠난 뒤 도착한 응답은 반영하지 않는다.
 */
import { useCallback, useEffect, useState } from "react";

import { getMeta } from "../../api/provisional";

export type DemoDateState =
  { status: "loading" } | { status: "ready"; date: string } | { status: "error" };

export type DemoDate = DemoDateState & {
  /** 시연일 조회를 처음부터 다시 한다 */
  retry: () => void;
};

const LOADING: DemoDateState = { status: "loading" };

export function useDemoDate(): DemoDate {
  const [state, setState] = useState<DemoDateState>(LOADING);
  // 조회 시도 번호. 바뀔 때마다 이펙트가 조회를 새로 보낸다.
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    getMeta().then(
      ({ demo_date: date }) => {
        if (active) setState({ status: "ready", date });
      },
      () => {
        if (active) setState({ status: "error" });
      },
    );
    return () => {
      active = false;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setState(LOADING);
    setAttempt((n) => n + 1);
  }, []);

  return { ...state, retry };
}
