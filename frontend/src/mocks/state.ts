// 모의 API 메모리 상태 보관소. 브라우저 탭 하나(또는 Vitest 파일 하나) 안에서만 공유된다.
// 핸들러·처리 단계 런타임은 `update`로 새 상태 객체를 넣고, 테스트는 afterEach에서 `reset()`한다.
// reset은 등록된 정리 콜백(`onReset`)을 먼저 부른 뒤 초기값으로 되돌린다.
import { createInitialState, type StateOverrides } from "./fixtures";
import type { MockState } from "./types";

let current: MockState = createInitialState();
/** reset 때 부를 정리 콜백(처리 단계 런타임의 타이머 취소 등) */
let resetListeners: ReadonlySet<() => void> = new Set();

export const mockState = {
  /** 현재 상태 */
  get(): MockState {
    return current;
  },
  /** 현재 상태로 새 상태를 만들어 바꾼다. `next`는 받은 상태를 고치지 않고 새 객체를 돌려준다 */
  update(next: (state: MockState) => MockState): MockState {
    current = next(current);
    return current;
  },
  /** 픽스처 초기값(필요하면 `overrides`를 얹은 값)으로 되돌린다 */
  reset(overrides?: StateOverrides): void {
    for (const listener of resetListeners) listener();
    current = createInitialState({ overrides });
  },
  /**
   * reset 때 부를 정리 콜백을 등록하고 해제 함수를 돌려준다. 처리 단계 런타임이 타이머를 취소해,
   * reset 뒤 같은 사진 번호(`mock_photo_n`)가 다시 쓰여도 이전 타이머가 새 사진을 건드리지 않게 한다.
   */
  onReset(listener: () => void): () => void {
    resetListeners = new Set([...resetListeners, listener]);
    return () => {
      resetListeners = new Set([...resetListeners].filter((l) => l !== listener));
    };
  },
};
