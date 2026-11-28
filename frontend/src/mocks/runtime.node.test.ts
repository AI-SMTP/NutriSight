// @vitest-environment node
// 이벤트 버스·처리 단계 런타임이 브라우저 없이(node 환경) 동작하는지 확인한다.
// HTTP를 거치지 않고 상태 전이 함수로 사진을 접수한 뒤 런타임에 넘긴다.
import { readFileSync } from "node:fs";

import type { PhotoStatusChangedEvent } from "../api/provisional";
import { eventBus } from "./eventBus";
import { DEMO_DATE } from "./fixtures";
import { acceptPostPhoto } from "./operations";
import { installMockRuntime } from "./runtime";
import { mockState } from "./state";

/** 주석을 뺀 소스. 설명 주석의 낱말이 아니라 코드의 참조만 본다 */
function codeOf(file: string): string {
  return readFileSync(new URL(file, import.meta.url), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");
}

let events: PhotoStatusChangedEvent[] = [];
let unsubscribe: () => void = () => undefined;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  events = [];
  unsubscribe = eventBus.subscribe((e) => {
    events = [...events, e];
  });
});

// 단언이 실패해도 가짜 타이머와 구독이 다음 테스트로 새지 않게 여기서 정리한다.
afterEach(() => {
  unsubscribe();
  vi.useRealTimers();
});

describe("node 환경의 모의 런타임", () => {
  it("브라우저 전역이 없는 환경이다", () => {
    expect(typeof globalThis.window).toBe("undefined");
  });

  it.each([
    "./eventBus.ts",
    "./pipeline.ts",
    "./runtime.ts",
    "./state.ts",
    "./fixtures.ts",
    "./operations.ts",
    "./types.ts",
    "./scenarios.ts",
  ])("%s는 msw/browser·window를 참조하지 않는다", (file) => {
    const code = codeOf(file);
    expect(code).not.toMatch(/msw\/browser/);
    expect(code).not.toMatch(/\bwindow\b/);
  });

  it("접수한 식후 사진을 done까지 진행하고 이벤트를 낸다", () => {
    const runtime = installMockRuntime({ stepDelayMs: 0 });
    const outcome = acceptPostPhoto(mockState.get(), {
      patientId: "NS03",
      date: DEMO_DATE,
      meal: "lunch",
      now: "2026-11-27T12:30:00+09:00",
    });
    if (!outcome.ok) throw new Error("접수가 성공해야 한다");
    mockState.update(() => outcome.state);

    runtime.photoAccepted(outcome.value.photo_id);
    vi.runAllTimers();

    expect(events.map((e) => e.status)).toEqual([
      "uploaded",
      "queued",
      "analyzing",
      "analyzing",
      "analyzing",
      "done",
    ]);
  });
});
