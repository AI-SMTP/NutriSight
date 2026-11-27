/// <reference types="vitest/config" />
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// 개발 서버는 /api를 실제 백엔드로 프록시한다(스펙 3.2절). 모의 모드(VITE_API_MOCK=1)에서는
// MSW 워커가 요청을 가로채므로 프록시까지 가지 않는다.
const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

// 번들 검사(Story 12)용 보고서 경로. dist 밖(git 무시 대상)에 빌드 모드별로 쓴다.
const BUILD_REPORT_DIR = path.join(import.meta.dirname, ".build-report");

/**
 * 출력 청크마다 실제로 들어간 모듈 ID를 `{청크 파일명: 모듈 ID[]}`로 기록한다.
 * `scripts/check-bundle.mjs`가 이 보고서로 기본 빌드에 MSW·`src/mocks/`가 없는지 확인한다.
 */
function bundleModuleReport(): Plugin {
  return {
    name: "nutrisight-bundle-module-report",
    apply: "build",
    generateBundle(_options, bundle) {
      const report: Record<string, string[]> = {};
      for (const [fileName, output] of Object.entries(bundle)) {
        if (output.type === "chunk") {
          report[fileName] = Object.keys(output.modules).sort();
        }
      }
      const mode = process.env.VITE_API_MOCK ? "mock" : "default";
      mkdirSync(BUILD_REPORT_DIR, { recursive: true });
      writeFileSync(
        path.join(BUILD_REPORT_DIR, `modules.${mode}.json`),
        `${JSON.stringify(report, null, 2)}\n`,
      );
    },
  };
}

export default defineConfig({
  plugins: [react(), bundleModuleReport()],
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
