// 모의 API 메모리 상태 보관소. 브라우저 탭 하나(또는 Vitest 파일 하나) 안에서만 공유된다.
// 핸들러·처리 단계 런타임은 `update`로 새 상태 객체를 넣고, 테스트는 afterEach에서 `reset()`한다.
import { createInitialState, type StateOverrides } from "./fixtures";
import type { MockState } from "./types";

let current: MockState = createInitialState();

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
    current = createInitialState({ overrides });
  },
};
