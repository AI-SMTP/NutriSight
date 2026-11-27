// 브라우저 모의 API 시작(browser.ts) 테스트. jsdom에서는 서비스 워커를 띄울 수 없으므로
// `msw/browser`의 setupWorker를 대역으로 바꾸고, 시작 성공·실패와 전역 연결을 확인한다.
import type { SetupWorker } from "msw/browser";

import {
  restoreServiceWorkerSupport,
  stubServiceWorkerSupport,
} from "../test/serviceWorkerSupport";
import { MockApiUnavailableError, startMockApi } from "./browser";
import { mockState } from "./state";
import * as runtime from "./runtime";

const worker = vi.hoisted(() => ({
  start: vi.fn<() => Promise<unknown>>(),
  setupCalls: 0,
  handlers: [] as unknown[],
}));

vi.mock("msw/browser", () => ({
  setupWorker: (...handlers: unknown[]) => {
    worker.setupCalls += 1;
    worker.handlers = handlers;
    return { start: worker.start } as unknown as SetupWorker;
  },
}));

beforeEach(() => {
  vi.stubGlobal("EventSource", vi.fn());
  worker.start.mockReset();
  worker.setupCalls = 0;
  worker.handlers = [];
  // 기본은 서비스 워커를 쓸 수 있는 보안 컨텍스트다. 실패 사례는 테스트 안에서 바꾼다.
  stubServiceWorkerSupport({ secure: true, serviceWorker: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  restoreServiceWorkerSupport();
  delete window.__nutrisightMock;
});

describe("startMockApi", () => {
  it("REST 핸들러와 /api/events SSE 핸들러로 워커를 시작한다", async () => {
    worker.start.mockResolvedValue(undefined);
    const { handlers } = await import("./handlers");

    await startMockApi({ target: window });

    expect(worker.start).toHaveBeenCalledWith({ onUnhandledFrame: "bypass" });
    expect(worker.handlers).toHaveLength(handlers.length + 1);
    expect(worker.handlers.slice(0, handlers.length)).toEqual(handlers);
    const events = worker.handlers.at(-1) as { info: { method: string; path: string } };
    expect(events.info).toMatchObject({ method: "GET", path: "/api/events" });
  });

  it("시작에 성공하면 window.__nutrisightMock의 reset·finishAll을 모의 런타임에 연결한다", async () => {
    worker.start.mockResolvedValue(undefined);
    const install = vi.spyOn(runtime, "installMockRuntime");

    await startMockApi({ target: window });

    const installed = install.mock.results[0]!.value as runtime.MockRuntime;
    const finishAll = vi.spyOn(installed, "finishAll");
    const reset = vi.spyOn(mockState, "reset");
    window.__nutrisightMock!.finishAll();
    window.__nutrisightMock!.reset();
    expect(finishAll).toHaveBeenCalledTimes(1);
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("단계 모드가 manual이면 수동 모드 런타임을, 아니면 기본 런타임을 설치한다", async () => {
    worker.start.mockResolvedValue(undefined);
    const install = vi.spyOn(runtime, "installMockRuntime");

    await startMockApi({ target: window, steps: "manual" });
    await startMockApi({ target: window, steps: undefined });

    expect(install.mock.calls).toEqual([[{ manualSteps: true }], [{}]]);
  });

  it("워커 시작이 실패하면 예외를 그대로 넘기고 전역을 만들지 않는다", async () => {
    const error = new DOMException("insecure", "SecurityError");
    worker.start.mockRejectedValue(error);

    await expect(startMockApi({ target: window })).rejects.toBe(error);

    expect(window.__nutrisightMock).toBeUndefined();
  });

  // MSW 3의 start()는 서비스 워커를 쓸 수 없으면 예외 없이 fetch 가로채기로 대신 동작한다.
  // 그러면 HTTP 실기기에서 배너 없이 모의 REST가 응답하므로(스펙 3.2절 위반) 시작 전에 직접 확인한다.
  it.each([
    ["보안 컨텍스트가 아니면(HTTP 실기기)", { secure: false, serviceWorker: true }],
    ["navigator.serviceWorker가 없으면", { secure: true, serviceWorker: false }],
  ])("%s 워커·런타임·전역을 만들지 않고 MockApiUnavailableError로 실패한다", async (_, support) => {
    stubServiceWorkerSupport(support);
    worker.start.mockResolvedValue(undefined);
    const install = vi.spyOn(runtime, "installMockRuntime");

    await expect(startMockApi({ target: window })).rejects.toBeInstanceOf(MockApiUnavailableError);

    expect(worker.setupCalls).toBe(0);
    expect(worker.start).not.toHaveBeenCalled();
    expect(install).not.toHaveBeenCalled();
    expect(window.__nutrisightMock).toBeUndefined();
  });
});
