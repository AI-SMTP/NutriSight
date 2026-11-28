/**
 * 브라우저(개발 모드) 모의 API 시작. `app/bootstrap.ts`가 `VITE_API_MOCK`일 때만 동적 import한다.
 *
 * - 정본: `docs/specs/frontend-shell-upload.md` '실행 모드'·'워커 실패 배너'·'MSW 처리 단계'.
 * - REST 핸들러(`handlers.ts`)와 `GET /api/events` SSE 핸들러로 서비스 워커를 시작한다.
 * - 시작에 성공한 뒤에만 런타임을 설치하고 `window.__nutrisightMock`을 만든다. 실패하면 예외를
 *   그대로 넘겨 부트스트랩이 배너를 띄우게 한다.
 * - MSW 3의 `worker.start()`는 서비스 워커를 쓸 수 없어도 예외 없이 fetch 가로채기로 대신 동작한다.
 *   그러면 HTTP로 접속한 실기기에서 배너 없이 모의 REST가 응답하므로(참조 문서 '워커 실패 배너'와 어긋남),
 *   워커를 만들기 전에 보안 컨텍스트와 서비스 워커 API를 직접 확인한다.
 */
import { setupWorker } from "msw/browser";

import { createMockControls, runtimeOptionsFor } from "./devGlobal";
import { handlers } from "./handlers";
import { installMockRuntime } from "./runtime";
import { createEventsHandler } from "./sseHandler";

/** 서비스 워커를 쓸 수 없어 모의 API를 시작하지 않았다 */
export class MockApiUnavailableError extends Error {
  constructor() {
    super("서비스 워커를 쓸 수 없는 환경입니다(보안 컨텍스트 아님 또는 서비스 워커 미지원)");
    this.name = "MockApiUnavailableError";
  }
}

function assertServiceWorkerAvailable(target: Window): void {
  if (!target.isSecureContext || !("serviceWorker" in target.navigator)) {
    throw new MockApiUnavailableError();
  }
}

export interface StartMockApiOptions {
  /** 전역을 붙일 대상 */
  target?: Window;
  /** 처리 단계 모드(`VITE_MOCK_STEPS`). `manual`이면 수동 모드 */
  steps?: string;
}

export async function startMockApi({
  target = window,
  steps = import.meta.env.VITE_MOCK_STEPS,
}: StartMockApiOptions = {}): Promise<void> {
  assertServiceWorkerAvailable(target);
  // SSE 핸들러는 EventSource가 있어야 만들어지므로 모듈을 불러올 때가 아니라 시작할 때 만든다.
  const worker = setupWorker(...handlers, createEventsHandler());
  await worker.start({ onUnhandledFrame: "bypass" });
  installMockRuntime(runtimeOptionsFor(steps));
  target.__nutrisightMock = createMockControls();
}
