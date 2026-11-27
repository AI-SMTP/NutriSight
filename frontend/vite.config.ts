/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 개발 서버는 /api를 실제 백엔드로 프록시한다(스펙 3.2절). 모의 모드(VITE_API_MOCK=1)에서는
// MSW 워커가 요청을 가로채므로 프록시까지 가지 않는다.
const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**"],
      exclude: [
        "src/api/generated/**",
        "src/mocks/**",
        "src/test/**",
        "src/**/*.test.*",
        "src/**/*.d.ts",
        // 진입점은 렌더 호출만 둔다. 분기가 있는 부트스트랩 로직은 테스트되는 모듈에 둔다.
        "src/main.tsx",
      ],
      thresholds: { lines: 80 },
    },
  },
});
