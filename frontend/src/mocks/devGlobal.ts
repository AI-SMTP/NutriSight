/**
 * 개발 전용 전역 `window.__nutrisightMock`(MSW 모드에서만 만든다)의 타입과 런타임 연결.
 *
 * - 정본: `docs/specs/frontend-shell-upload.md` 'finishAll과 reset'(E2E 단계 제어·E2E 시작 데이터 고정).
 * - `reset()`: 모의 상태를 픽스처 초기값으로 되돌린다(런타임 타이머도 취소된다).
 * - `finishAll()`: 현재 런타임의 작업 전부를 종료 상태까지 진행한다(E2E가 단계 타이머와 경쟁하지 않게 하는 계약).
 */
import { currentMockRuntime, type MockRuntimeOptions } from "./runtime";
import { mockState } from "./state";

export interface NutrisightMockControls {
  reset(): void;
  finishAll(): void;
}

declare global {
  interface Window {
    /** MSW 모드에서만 있는 개발 전용 모의 제어 */
    __nutrisightMock?: NutrisightMockControls;
  }
}

/** 호출할 때마다 현재 런타임을 찾는다(나중에 런타임을 다시 설치해도 따라간다) */
export function createMockControls(): NutrisightMockControls {
  return {
    reset: () => mockState.reset(),
    finishAll: () => currentMockRuntime().finishAll(),
  };
}

/** `VITE_MOCK_STEPS` 값으로 런타임 옵션을 정한다. `manual`이면 첫 analyzing에서 멈춘다 */
export function runtimeOptionsFor(steps: string | undefined): MockRuntimeOptions {
  return steps === "manual" ? { manualSteps: true } : {};
}
