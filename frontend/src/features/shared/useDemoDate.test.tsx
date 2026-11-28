// 시연일 초기화 훅 테스트(`docs/specs/frontend-shell-upload.md` '시연일 초기화'). 기본 MSW 핸들러의 시연일은 2026-11-27이다.
import { act, renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";

import { errorHandlers } from "../../mocks/errorHandlers";
import { DEMO_DATE } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { useDemoDate } from "./useDemoDate";

describe("useDemoDate", () => {
  it("처음에는 loading이고 조회에 성공하면 ready(시연일)이다", async () => {
    const { result } = renderHook(() => useDemoDate());

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", date: DEMO_DATE }));
  });

  it.each([
    ["네트워크 오류", "network"],
    ["서버 오류(500)", "server"],
  ] as const)("%s면 error이고, retry() 성공 → ready", async (_label, kind) => {
    server.use(errorHandlers.meta(kind));
    const { result } = renderHook(() => useDemoDate());

    await waitFor(() => expect(result.current.status).toBe("error"));

    server.resetHandlers();
    act(() => result.current.retry());
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current).toMatchObject({ status: "ready", date: DEMO_DATE }));
  });

  it("retry()는 시연일 조회를 한 번 다시 보낸다", async () => {
    server.use(errorHandlers.meta("network"));
    const { result } = renderHook(() => useDemoDate());
    await waitFor(() => expect(result.current.status).toBe("error"));

    let calls = 0;
    server.resetHandlers();
    server.use(
      http.get("/api/meta", () => {
        calls += 1;
        return undefined;
      }),
    );
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(calls).toBe(1);
  });

  it("언마운트 뒤 도착한 응답은 반영하지 않는다(경고 없음)", async () => {
    const consoleError = vi.spyOn(console, "error");
    const { result, unmount } = renderHook(() => useDemoDate());
    unmount();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(result.current.status).toBe("loading");
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
