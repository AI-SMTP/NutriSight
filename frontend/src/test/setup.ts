// Vitest 공용 설정: jest-dom 매처, MSW node 서버 수명주기, 모의 상태 초기화, DOM 정리.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";

import { server } from "../mocks/server";
import { mockState } from "../mocks/state";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  server.resetHandlers();
  // 테스트가 바꾼 모의 상태(업로드·전량 기록·주입한 overrides)를 픽스처 초기값으로 되돌린다.
  mockState.reset();
  cleanup();
});
afterAll(() => server.close());
