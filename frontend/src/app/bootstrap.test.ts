// 앱 부트스트랩(bootstrap.ts) 테스트. jsdom에서는 서비스 워커를 띄울 수 없으므로
// `msw/browser`의 setupWorker를 대역으로 바꿔 워커 시작 성공·실패를 주입한다.
import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { SetupWorker } from "msw/browser";
import type { Root } from "react-dom/client";

import { jpegBlob, makeBitmap, stubDecode, stubOffscreenCanvas } from "../test/imageStubs";
import { makePhoto, stubObjectUrl } from "../test/objectUrl";
import {
  restoreServiceWorkerSupport,
  stubServiceWorkerSupport,
} from "../test/serviceWorkerSupport";
import { bootstrap } from "./bootstrap";
import { MOCK_UNAVAILABLE_MESSAGE } from "./MockUnavailableBanner";

const { workerStart, setupWorker } = vi.hoisted(() => {
  const start = vi.fn<() => Promise<unknown>>();
  return {
    workerStart: start,
    setupWorker: vi.fn<(...handlers: unknown[]) => { start: typeof start }>(() => ({ start })),
  };
});

vi.mock("msw/browser", () => ({
  setupWorker: (...handlers: unknown[]) => setupWorker(...handlers) as unknown as SetupWorker,
}));

const loadBrowserMock = () => import("../mocks/browser");

let container: HTMLElement;
let root: Root | null = null;
let urls: ReturnType<typeof stubObjectUrl>;

beforeEach(() => {
  container = document.body.appendChild(document.createElement("div"));
  urls = stubObjectUrl();
  // msw `sse()`는 만들 때 EventSource가 있어야 한다. 호출 여부는 각 테스트가 확인한다.
  vi.stubGlobal("EventSource", vi.fn());
  workerStart.mockReset();
  setupWorker.mockClear();
  // 기본은 서비스 워커를 쓸 수 있는 보안 컨텍스트다. 실패 사례는 테스트 안에서 바꾼다.
  stubServiceWorkerSupport({ secure: true, serviceWorker: true });
});

afterEach(async () => {
  await act(async () => root?.unmount());
  root = null;
  container.remove();
  urls.restore();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  restoreServiceWorkerSupport();
  delete window.__nutrisightMock;
  window.history.replaceState(null, "", "/");
});

async function run(options: Parameters<typeof bootstrap>[1]) {
  await act(async () => {
    root = await bootstrap(container, options);
  });
}

describe("bootstrap", () => {
  it("보안 컨텍스트가 아니면 배너를 띄우고, 배너 링크의 촬영 확인에서 API 없이 변환 결과를 본다", async () => {
    const fetch = vi.fn();
    const EventSource = vi.fn();
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("EventSource", EventSource);
    // HTTP로 접속한 실기기: 보안 컨텍스트가 아니고 서비스 워커 API도 없다.
    stubServiceWorkerSupport({ secure: false, serviceWorker: false });
    workerStart.mockResolvedValue(undefined);
    stubDecode(makeBitmap(4032, 3024));
    stubOffscreenCanvas({ convertToBlob: () => Promise.resolve(jpegBlob(1229)) });

    await run({ loadMockApi: loadBrowserMock });

    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent(MOCK_UNAVAILABLE_MESSAGE);
    expect(MOCK_UNAVAILABLE_MESSAGE).toBe("모의 API를 쓸 수 없습니다(보안 컨텍스트 아님)");
    await userEvent.click(within(banner).getByRole("link", { name: "촬영 확인" }));
    expect(screen.getByRole("heading", { level: 1, name: "촬영 확인" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/camera-check");

    await userEvent.upload(
      screen.getByLabelText("촬영하기"),
      makePhoto("tray.jpg", "image/jpeg", 4_194_304),
    );
    expect(
      await screen.findByText("변환됨 · JPEG · 원본 4032×3024, 4.0 MB → 변환 2048×1536, 1.2 KB"),
    ).toBeInTheDocument();

    expect(setupWorker).not.toHaveBeenCalled();
    expect(window.__nutrisightMock).toBeUndefined();
    expect(fetch).not.toHaveBeenCalled();
    expect(EventSource).not.toHaveBeenCalled();
  });

  it("서비스 워커 등록이 실패해도(start reject) 배너와 함께 앱을 렌더한다", async () => {
    workerStart.mockRejectedValue(new DOMException("blocked", "SecurityError"));

    await run({ loadMockApi: loadBrowserMock });

    expect(workerStart).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("alert")).toHaveTextContent(MOCK_UNAVAILABLE_MESSAGE);
    expect(window.__nutrisightMock).toBeUndefined();
  });

  it("모의 API를 불러오지 못해도(청크 실패) 배너와 함께 앱을 렌더한다", async () => {
    await run({ loadMockApi: () => Promise.reject(new TypeError("chunk")) });

    expect(screen.getByRole("alert")).toHaveTextContent(MOCK_UNAVAILABLE_MESSAGE);
    expect(screen.getByRole("heading", { level: 1, name: "역할 선택" })).toBeInTheDocument();
  });

  it("워커 시작에 성공하면 배너 없이 렌더하고 개발 전역을 만든다", async () => {
    workerStart.mockResolvedValue(undefined);

    await run({ loadMockApi: loadBrowserMock });

    expect(workerStart).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "역할 선택" })).toBeInTheDocument();
    expect(window.__nutrisightMock).toEqual({
      reset: expect.any(Function),
      finishAll: expect.any(Function),
    });
  });

  it("모의 API를 쓰지 않으면(loadMockApi null) 불러오지 않고 배너 없이 렌더한다", async () => {
    await run({ loadMockApi: null });

    expect(workerStart).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "역할 선택" })).toBeInTheDocument();
    expect(window.__nutrisightMock).toBeUndefined();
  });

  it("VITE_API_MOCK이 있으면 옵션 없이도 mocks/browser를 불러와 워커를 시작한다", async () => {
    vi.stubEnv("VITE_API_MOCK", "1");
    vi.resetModules();
    workerStart.mockResolvedValue(undefined);
    const fresh = await import("./bootstrap");

    await act(async () => {
      root = await fresh.bootstrap(container);
    });

    expect(workerStart).toHaveBeenCalledTimes(1);
    expect(window.__nutrisightMock).toBeDefined();
  });

  it("워커 시작을 기다린 뒤에 렌더한다", async () => {
    let finish!: () => void;
    workerStart.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));

    const pending = bootstrap(container, { loadMockApi: loadBrowserMock });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container).toBeEmptyDOMElement();

    await act(async () => {
      finish();
      root = await pending;
    });
    expect(screen.getByRole("heading", { level: 1, name: "역할 선택" })).toBeInTheDocument();
  });
});
