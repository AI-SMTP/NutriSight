// 빌드 모듈 보고서(.build-report/modules.*.json)를 읽어 모의 코드 포함 여부를 확인한다.
//   node scripts/check-bundle.mjs --report <경로>               기본 빌드: MSW·src/mocks/가 없어야 통과
//   node scripts/check-bundle.mjs --report <경로> --expect-mock 모의 빌드: 둘 다 있어야 통과
import { readFileSync } from "node:fs";
import process from "node:process";

const MOCK_PATTERNS = [
  { name: "MSW 패키지", test: (id) => id.includes("/node_modules/msw/") },
  { name: "src/mocks/", test: (id) => id.includes("/src/mocks/") },
];

function parseArgs(argv) {
  const reportIndex = argv.indexOf("--report");
  const reportPath = reportIndex === -1 ? undefined : argv[reportIndex + 1];
  if (reportPath === undefined) {
    throw new Error("사용법: check-bundle.mjs --report <보고서 경로> [--expect-mock]");
  }
  return { reportPath, expectMock: argv.includes("--expect-mock") };
}

function findMockModules(report) {
  const found = [];
  for (const [chunk, modules] of Object.entries(report)) {
    for (const rawId of modules) {
      // Windows 역슬래시 경로도 같은 패턴으로 판정하도록 먼저 정규화한다.
      const id = rawId.replaceAll("\\", "/");
      const pattern = MOCK_PATTERNS.find((p) => p.test(id));
      if (pattern !== undefined) found.push({ chunk, id, pattern: pattern.name });
    }
  }
  return found;
}

function main() {
  const { reportPath, expectMock } = parseArgs(process.argv.slice(2));
  const report = JSON.parse(readFileSync(reportPath, "utf8"));
  const found = findMockModules(report);
  if (expectMock) {
    const missing = MOCK_PATTERNS.filter((p) => !found.some((f) => f.pattern === p.name));
    if (missing.length > 0) {
      process.stderr.write(`모의 빌드에서 찾지 못했다: ${missing.map((p) => p.name).join(", ")}\n`);
      return 1;
    }
    process.stdout.write(`모의 빌드 확인: 모의 모듈 ${found.length}개 포함 (${reportPath})\n`);
    return 0;
  }
  if (found.length > 0) {
    for (const f of found) process.stderr.write(`[${f.pattern}] ${f.chunk}: ${f.id}\n`);
    process.stderr.write(`기본 빌드에 모의 코드가 들어갔다: ${found.length}개 모듈\n`);
    return 1;
  }
  process.stdout.write(`기본 빌드 확인: 모의 코드 없음 (${reportPath})\n`);
  return 0;
}

process.exitCode = main();
