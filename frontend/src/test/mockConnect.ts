// SSE 구독 테스트 도우미: `EventSource` 대신 모의 이벤트 버스를 발행기로 쓰는 연결 함수.
// jsdom·node에는 `EventSource`가 없으므로 Vitest는 이 연결을 `SystemEventsProvider`에 주입한다
// (스펙 3.4절 마지막 항목, 계획 구현 전제의 MSW 이벤트 경로).
import { PHOTO_STATUS_CHANGED_EVENT } from "../api/provisional";
import type { SystemEventSource } from "../api/events";
import { eventBus as sharedBus, type EventBus } from "../mocks/eventBus";

/** 모의 연결 하나. `open`을 보낸 뒤부터 버스 이벤트를 받는다(실제 EventSource처럼). */
export class MockEventSource extends EventTarget implements SystemEventSource {
  private unsubscribe: (() => void) | null = null;
  closed = false;

  constructor(private readonly bus: Pick<EventBus, "subscribe">) {
    super();
  }

  /** 연결(또는 재연결) `open`을 보낸다. 닫힌 연결이면 아무것도 하지 않는다 */
  open(): void {
    if (this.closed) return;
    this.unsubscribe ??= this.bus.subscribe((event) => {
      this.emitRaw(JSON.stringify(event));
    });
    this.dispatchEvent(new Event("open"));
  }

  /**
   * 연결이 끊긴 구간을 흉내 낸다. 버스 구독만 해제하고 연결은 닫지 않는다.
   * 이후 `open()`을 부르면 버스를 다시 구독하고 재연결 `open`을 알린다.
   */
  disconnect(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
  }

  /** `photo.status_changed` 메시지를 원문 데이터 그대로 보낸다(형식 오류 확인용) */
  emitRaw(data: string): void {
    if (this.closed) return;
    this.dispatchEvent(new MessageEvent(PHOTO_STATUS_CHANGED_EVENT, { data }));
  }

  readonly close = vi.fn(() => {
    this.closed = true;
    this.disconnect();
  });
}

export interface MockConnect {
  /** Provider에 넣는 연결 함수. 호출 횟수를 기록한다 */
  connect: ReturnType<typeof vi.fn<() => MockEventSource>>;
  /** 지금까지 만든 연결(닫힌 것 포함) */
  readonly connections: readonly MockEventSource[];
  /** 닫히지 않은 연결 모두에 `open`을 보낸다. 다시 부르면 재연결 `open`이 된다 */
  open(): void;
  /** 닫히지 않은 연결 모두의 버스 구독을 끊는다(연결이 끊긴 구간). 다시 `open()`하면 재연결된다 */
  disconnect(): void;
  /** 모든 연결의 `close()` 호출 횟수 합 */
  closeCount(): number;
}

/** 모의 버스(기본은 모의 API 공용 버스)를 발행기로 쓰는 연결 함수를 만든다. `open` 시점은 테스트가 정한다 */
export function createMockConnect(bus: Pick<EventBus, "subscribe"> = sharedBus): MockConnect {
  const connections: MockEventSource[] = [];
  const connect = vi.fn(() => {
    const source = new MockEventSource(bus);
    connections.push(source);
    return source;
  });
  return {
    connect,
    connections,
    open() {
      for (const source of connections) source.open();
    },
    disconnect() {
      for (const source of connections) source.disconnect();
    },
    closeCount() {
      return connections.reduce((sum, source) => sum + source.close.mock.calls.length, 0);
    },
  };
}
