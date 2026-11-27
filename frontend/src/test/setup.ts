// Vitest 공용 설정: jest-dom 매처, MSW node 서버 수명주기, DOM 정리.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";

import { server } from "../mocks/server";

beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
});
afterAll(() => server.close());
