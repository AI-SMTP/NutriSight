/**
 * `GET /api/events` SSE 모의 핸들러. 모의 이벤트 버스의 `photo.status_changed` 데이터를
 * 연결된 `EventSource`에 `event: photo.status_changed` 메시지(데이터는 JSON)로 내보낸다.
 *
 * - 정본: 스펙 3.3절(SSE 구독), 3.4절(MSW 모의), 계획 구현 전제의 MSW 이벤트 경로.
 * - 브라우저 워커(`browser.ts`)만 쓴다. Vitest는 SSE 대신 `api/events.tsx`의 주입식 구독을 쓴다.
 * - msw `sse()`는 만들 때 `EventSource`가 있어야 하므로 모듈을 불러올 때가 아니라 호출할 때 만든다.
 */
import { sse } from "msw/sse";

import {
  EVENTS_PATH,
  PHOTO_STATUS_CHANGED_EVENT,
  type PhotoStatusChangedEvent,
} from "../api/provisional";
import { eventBus as sharedBus, type EventBus } from "./eventBus";

/**
 * 연결 직후 보내는 재연결 간격(ms). 첫 프레임을 곧바로 보내야 응답이 열린다
 * (msw node 인터셉터는 첫 덩어리가 올 때까지 fetch 응답을 넘기지 않는다).
 */
export const SSE_RETRY_MS = 2000;

type EventMap = { [PHOTO_STATUS_CHANGED_EVENT]: PhotoStatusChangedEvent };

export function createEventsHandler(bus: Pick<EventBus, "subscribe"> = sharedBus) {
  return sse<EventMap>(EVENTS_PATH, ({ client, request }) => {
    client.send({ retry: SSE_RETRY_MS });
    const unsubscribe = bus.subscribe((event) => {
      client.send({ event: PHOTO_STATUS_CHANGED_EVENT, data: event });
    });
    // 탭을 닫거나 EventSource를 닫아 요청이 중단되면 버스 구독도 끊는다.
    request.signal.addEventListener("abort", unsubscribe, { once: true });
  });
}
