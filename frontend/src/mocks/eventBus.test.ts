// 모의 이벤트 버스(eventBus.ts) 테스트.
import type { PhotoStatusChangedEvent } from "../api/provisional";
import { createEventBus } from "./eventBus";

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

describe("createEventBus", () => {
  it("구독자 모두에게 발행 순서대로 전달한다", () => {
    const bus = createEventBus();
    const a: PhotoStatusChangedEvent[] = [];
    const b: PhotoStatusChangedEvent[] = [];
    bus.subscribe((e) => a.push(e));
    bus.subscribe((e) => b.push(e));

    bus.publish(EVENT);
    bus.publish({ ...EVENT, status: "done" });

    expect(a.map((e) => e.status)).toEqual(["queued", "done"]);
    expect(b).toEqual(a);
  });

  it("구독 해제 뒤에는 받지 않는다", () => {
    const bus = createEventBus();
    const listener = vi.fn();
    const unsubscribe = bus.subscribe(listener);

    unsubscribe();
    bus.publish(EVENT);

    expect(listener).not.toHaveBeenCalled();
  });

  it("버스마다 구독자가 따로다", () => {
    const first = createEventBus();
    const second = createEventBus();
    const listener = vi.fn();
    first.subscribe(listener);

    second.publish(EVENT);

    expect(listener).not.toHaveBeenCalled();
  });
});
