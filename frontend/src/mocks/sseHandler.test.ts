// GET /api/events SSE 모의 핸들러(sseHandler.ts) 테스트.
// node에는 EventSource가 없어 msw `sse()`가 핸들러를 만들지 못하므로, 생성 전에 대역을 붙인다.
// 스트림은 EventSource 대신 `accept: text/event-stream` fetch로 직접 읽는다.
import type { PhotoStatusChangedEvent } from "../api/provisional";
import { createEventBus } from "./eventBus";
import { server } from "./server";
import { createEventsHandler, SSE_RETRY_MS } from "./sseHandler";

const EVENT: PhotoStatusChangedEvent = {
  photo_id: "mock_photo_1",
  kind: "post",
  patient_id: "NS03",
  meal_plan_id: "2026-11-27_lunch_general",
  meal_order_id: "NS03_2026-11-27_lunch",
  status: "queued",
  stage: null,
  at: "2026-11-27T12:00:00.000Z",
};

const decoder = new TextDecoder();

beforeEach(() => {
  vi.stubGlobal("EventSource", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function openStream(signal?: AbortSignal) {
  return fetch(new URL("/api/events", globalThis.location.origin), {
    headers: { accept: "text/event-stream" },
    signal,
  });
}

/** 스트림에서 프레임(빈 줄로 끝나는 덩어리) `count`개를 읽는다. 여러 프레임이 한 덩어리로 올 수 있다 */
async function readFrames(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  count: number,
): Promise<string[]> {
  let text = "";
  while (text.split("\n\n").length - 1 < count) {
    const { value, done } = await reader.read();
    if (done) break;
    text += decoder.decode(value);
  }
  return text
    .split("\n\n")
    .slice(0, count)
    .map((frame) => `${frame}\n\n`);
}

async function readFrame(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<string> {
  const [frame] = await readFrames(reader, 1);
  return frame!;
}

describe("createEventsHandler", () => {
  it("연결 직후 재연결 간격 프레임을 보내 응답을 곧바로 연다", async () => {
    server.use(createEventsHandler(createEventBus()));
    const response = await openStream();
    const reader = response.body!.getReader();

    expect(response.headers.get("content-type")).toBe("text/event-stream");
    expect(await readFrame(reader)).toBe(`retry:${SSE_RETRY_MS}\n\n`);
    await reader.cancel();
  });

  it("버스 이벤트를 event: photo.status_changed 메시지(JSON 데이터)로 내보낸다", async () => {
    const bus = createEventBus();
    server.use(createEventsHandler(bus));
    const response = await openStream();
    const reader = response.body!.getReader();
    await readFrame(reader);

    bus.publish(EVENT);
    bus.publish({ ...EVENT, status: "done" });

    const [first, second] = await readFrames(reader, 2);
    expect(first).toBe(`event:photo.status_changed\ndata:${JSON.stringify(EVENT)}\n\n`);
    expect(JSON.parse(second!.split("data:")[1]!)).toEqual({ ...EVENT, status: "done" });
    await reader.cancel();
  });

  it("연결이 끊기면(요청 중단) 버스 구독을 해제한다", async () => {
    const unsubscribe = vi.fn();
    const bus = { publish: vi.fn(), subscribe: vi.fn(() => unsubscribe) };
    server.use(createEventsHandler(bus));
    const controller = new AbortController();

    await openStream(controller.signal);
    expect(bus.subscribe).toHaveBeenCalledTimes(1);
    expect(unsubscribe).not.toHaveBeenCalled();

    controller.abort();
    expect(unsubscribe).toHaveBeenCalledTimes(1);
  });

  it("버스를 주지 않으면 모의 API 공용 버스를 쓴다", async () => {
    const { eventBus } = await import("./eventBus");
    server.use(createEventsHandler());
    const response = await openStream();
    const reader = response.body!.getReader();
    await readFrame(reader);

    eventBus.publish(EVENT);

    expect(await readFrame(reader)).toContain(`"photo_id":"mock_photo_1"`);
    await reader.cancel();
  });
});
