import { defineConfig, devices } from "@playwright/test";

// E2E 설정(`docs/specs/frontend-shell-upload.md` '실행 모드'·'테스트와 E2E', E2E 단계 제어).
// MSW 모드 개발 서버를 수동 단계(`VITE_MOCK_STEPS=manual`)로 띄우고 390×844 모바일 뷰포트에서 돈다.
// localhost는 보안 컨텍스트라 서비스 워커가 시작되고 `window.__nutrisightMock`이 생긴다.
const PORT = 5180;
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: "list",
  use: {
    baseURL: BASE_URL,
    viewport: { width: 390, height: 844 },
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: {
    command: `VITE_MOCK_STEPS=manual pnpm dev:mock --port ${PORT} --strictPort`,
    url: BASE_URL,
    // 수동 단계 모드가 아닌 서버를 재사용하지 않도록 늘 새로 띄운다
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
