// Vitest 공용 설정: jest-dom 매처, MSW node 서버 수명주기, 모의 상태 초기화, DOM 정리.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";

import { HOLD_STEP_DELAY_MS, installMockRuntime } from "../mocks/runtime";
import { server } from "../mocks/server";
import { mockState } from "../mocks/state";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
// 모의 처리 단계가 실제 시간에 따라 진행되지 않도록, 테스트마다 단계를 멈춰 둔 런타임을 설치한다.
// 수동 모드(manualSteps)는 첫 analyzing(intake)까지는 타이머로 진행하므로 업로드 직후 상태가 시간에 따라
// 바뀐다. 그래서 수동 모드 대신 단계 간격을 setTimeout 최댓값으로 둔다. 단계 진행이 필요한 테스트는
// 자기 런타임을 설치하고, 남은 타이머는 afterEach의 reset이 취소한다.
beforeEach(() => {
  installMockRuntime({ stepDelayMs: HOLD_STEP_DELAY_MS });
});
afterEach(() => {
  server.resetHandlers();
  // 테스트가 바꾼 모의 상태(업로드·전량 기록·주입한 overrides)를 픽스처 초기값으로 되돌린다.
  mockState.reset();
  cleanup();
});
afterAll(() => server.close());
