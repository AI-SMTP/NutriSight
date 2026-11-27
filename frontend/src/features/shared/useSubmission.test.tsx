// 제출 요청 순번 훅 테스트(스펙 3.5절 "요청 대상 고정과 선택 전환 규칙").
// 응답 시점을 테스트가 정하도록 실제 요청 대신 직접 끝내는 약속(test/deferred)을 쓴다.
import { act, renderHook } from "@testing-library/react";

import { ApiError } from "../../api/provisional";
import { jpegBlob } from "../../test/apiError";
import { deferred, type Deferred } from "../../test/deferred";
import { useSubmission } from "./useSubmission";

interface Target {
  date: string;
  meal: string;
  photo: Blob;
}

function target(): Target {
  return { date: "2026-11-27", meal: "dinner", photo: jpegBlob() };
}

describe("useSubmission", () => {
  it("요청 중에는 busy이고, 성공하면 busy를 풀고 onSuccess에 결과와 고정된 요청을 넘긴다", async () => {
    const pending = deferred<string>();
    const run = vi.fn<(request: Target) => Promise<string>>(() => pending.promise);
    const onSuccess = vi.fn();
    const { result } = renderHook(() => useSubmission());
    const original = target();

    let started = false;
    act(() => {
      started = result.current.submit(original, run, { onSuccess });
    });
    expect(started).toBe(true);
    expect(result.current.busy).toBe(true);

    // 요청을 보낸 뒤 원래 대상 객체를 바꿔도 요청 객체는 그대로다(대상·사진 고정)
    const request = run.mock.calls[0]?.[0];
    original.meal = "lunch";
    expect(request).toMatchObject({ meal: "dinner", photo: expect.any(Blob) });
    expect(Object.isFrozen(request)).toBe(true);

    await act(async () => pending.resolve("ok"));
    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBeNull();
    expect(onSuccess).toHaveBeenCalledWith("ok", request);
  });

  it("실패하면 busy를 풀고 오류 kind를 남기며 onError를 부른다", async () => {
    const pending = deferred<string>();
    const onError = vi.fn();
    const { result } = renderHook(() => useSubmission());

    act(() => {
      result.current.submit(target(), () => pending.promise, { onError });
    });
    const error = new ApiError("conflict", 409);
    await act(async () => pending.reject(error));

    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBe("conflict");
    expect(onError).toHaveBeenCalledWith(error, expect.objectContaining({ meal: "dinner" }));
  });

  it("ApiError가 아닌 실패는 server로 분류한다", async () => {
    const { result } = renderHook(() => useSubmission());

    act(() => {
      result.current.submit(target(), () => Promise.reject(new Error("boom")));
    });
    await act(async () => {});

    expect(result.current.error).toBe("server");
  });

  it("요청 중에 다시 submit하면 보내지 않는다", () => {
    const run = vi.fn(() => new Promise<string>(() => {}));
    const { result } = renderHook(() => useSubmission());

    act(() => {
      result.current.submit(target(), run);
    });
    let second = true;
    act(() => {
      second = result.current.submit(target(), run);
    });

    expect(second).toBe(false);
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("새 제출을 시작하면 이전 오류를 지우고, clearError()로도 지울 수 있다", async () => {
    const { result } = renderHook(() => useSubmission());
    act(() => {
      result.current.submit(target(), () => Promise.reject(new ApiError("too_large", 413)));
    });
    await act(async () => {});
    expect(result.current.error).toBe("too_large");

    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();

    act(() => {
      result.current.submit(target(), () => Promise.reject(new ApiError("invalid", 422)));
    });
    await act(async () => {});
    expect(result.current.error).toBe("invalid");
    const pending = deferred<string>();
    act(() => {
      result.current.submit(target(), () => pending.promise);
    });
    expect(result.current.error).toBeNull();
  });

  it.each([
    ["성공", (d: Deferred<string>) => d.resolve("ok")],
    ["실패", (d: Deferred<string>) => d.reject(new ApiError("network"))],
  ])("제출 중 언마운트하면 늦은 %s 응답을 버리고 React 경고가 없다", async (_label, settle) => {
    const consoleError = vi.spyOn(console, "error");
    const pending = deferred<string>();
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const { result, unmount } = renderHook(() => useSubmission());

    act(() => {
      result.current.submit(target(), () => pending.promise, { onSuccess, onError });
    });
    unmount();
    await act(async () => settle(pending));

    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
    expect(result.current.busy).toBe(true);
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
