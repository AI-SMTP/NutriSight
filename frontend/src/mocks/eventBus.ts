// 모의 이벤트 버스. 처리 단계 런타임이 `photo.status_changed` 데이터를 발행하고,
// 브라우저에서는 SSE 모의 핸들러가, Vitest에서는 테스트 발행기가 구독한다.
// 브라우저 API(`window`, `msw/browser`)를 쓰지 않아 node에서도 그대로 동작한다.
import type { PhotoStatusChangedEvent } from "../api/provisional";

export type MockEventListener = (event: PhotoStatusChangedEvent) => void;

export interface EventBus {
  /** 지금 구독 중인 모두에게 이벤트를 전달한다 */
  publish(event: PhotoStatusChangedEvent): void;
  /** 구독하고 해제 함수를 돌려준다 */
  subscribe(listener: MockEventListener): () => void;
}

export function createEventBus(): EventBus {
  let listeners: ReadonlySet<MockEventListener> = new Set();
  return {
    publish(event) {
      // 전달 중 구독·해제가 일어나도 이번 발행 대상은 바뀌지 않는다(집합을 새로 만들어 바꾸므로).
      for (const listener of listeners) listener(event);
    },
    subscribe(listener) {
      listeners = new Set([...listeners, listener]);
      return () => {
        listeners = new Set([...listeners].filter((l) => l !== listener));
      };
    },
  };
}

/** 모의 API 전체가 공유하는 버스 */
export const eventBus: EventBus = createEventBus();
