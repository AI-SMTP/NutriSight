// SSE 구독 Provider(api/events.tsx) 테스트. 연결은 모의 버스를 발행기로 쓰는 주입식 연결이다.
import { act, render } from "@testing-library/react";
import { StrictMode } from "react";

import { createEventBus } from "../mocks/eventBus";
import { createMockConnect } from "../test/mockConnect";
import { SystemEventsProvider, useSystemEvents, type SystemEventsHandlers } from "./events";
import { PHOTO_STATUS_CHANGED_EVENT, type PhotoStatusChangedEvent } from "./provisional";

const LUNCH = "2026-11-27_lunch_general";

const POST_EVENT: PhotoStatusChangedEvent = {
  photo_id: "mock_photo_1",
  kind: "post",
  patient_id: "NS03",
  meal_plan_id: LUNCH,
  meal_order_id: "NS03_2026-11-27_lunch",
  status: "queued",
  stage: null,
  at: "2026-11-27T12:00:00.000Z",
};

function Subscriber(props: SystemEventsHandlers) {
  useSystemEvents(props);
  return null;
}

function setup(handlers: SystemEventsHandlers = {}) {
  const bus = createEventBus();
  const mock = createMockConnect(bus);
  const onPhotoStatusChanged = vi.fn<(event: PhotoStatusChangedEvent) => void>();
  const onOpen = vi.fn<() => void>();
  const view = render(
    <SystemEventsProvider connect={mock.connect}>
      <Subscriber onPhotoStatusChanged={onPhotoStatusChanged} onOpen={onOpen} {...handlers} />
    </SystemEventsProvider>,
  );
  return { bus, mock, onPhotoStatusChanged, onOpen, view };
}

describe("SystemEventsProvider", () => {
  it("마운트하면 연결을 하나 열고, open 전에는 콜백을 부르지 않는다", () => {
    const { mock, onPhotoStatusChanged, onOpen } = setup();

    expect(mock.connect).toHaveBeenCalledTimes(1);
    expect(onOpen).not.toHaveBeenCalled();
    expect(onPhotoStatusChanged).not.toHaveBeenCalled();
  });

  it("open·이벤트·재연결 open을 구독 콜백에 차례로 알린다", () => {
    const { bus, mock, onPhotoStatusChanged, onOpen } = setup();

    act(() => mock.open());
    expect(onOpen).toHaveBeenCalledTimes(1);

    act(() => bus.publish(POST_EVENT));
    expect(onPhotoStatusChanged).toHaveBeenCalledTimes(1);
    expect(onPhotoStatusChanged).toHaveBeenLastCalledWith(POST_EVENT);

    // 재연결: 같은 연결에서 open이 다시 온다
    act(() => mock.open());
    expect(onOpen).toHaveBeenCalledTimes(2);
    expect(mock.connect).toHaveBeenCalledTimes(1);
  });

  // 이 테스트는 Provider가 아니라 모의 연결(mockConnect)의 동작을 확인한다. 실제 EventSource처럼
  // open 전에는 버스를 구독하지 않아, 첫 open 전 변경을 화면이 open 뒤 재조회로 잡는 상황을 만든다.
  it("open 전에 발행된 이벤트는 전달되지 않는다", () => {
    const { bus, mock, onPhotoStatusChanged } = setup();

    act(() => bus.publish(POST_EVENT));
    act(() => mock.open());

    expect(onPhotoStatusChanged).not.toHaveBeenCalled();
  });

  it.each([
    ["kind 없음", { ...POST_EVENT, kind: undefined }],
    [
      "기준 사진(kind: baseline)",
      {
        ...POST_EVENT,
        photo_id: "mock_baseline_1",
        kind: "baseline" as const,
        patient_id: null,
        meal_order_id: null,
        status: "uploaded" as const,
      },
    ],
    ["식후 사진(kind: post)", POST_EVENT],
  ])("%s 이벤트도 meal_plan_id·photo_id를 전달한다", (_label, event) => {
    const { bus, mock, onPhotoStatusChanged } = setup();
    act(() => mock.open());

    act(() => bus.publish(event));

    expect(onPhotoStatusChanged).toHaveBeenCalledTimes(1);
    expect(onPhotoStatusChanged).toHaveBeenCalledWith(
      expect.objectContaining({ meal_plan_id: event.meal_plan_id, photo_id: event.photo_id }),
    );
  });

  it.each([
    ["JSON이 아님", "not-json"],
    ["객체가 아님", "42"],
    ["meal_plan_id 없음", JSON.stringify({ photo_id: "p1" })],
    ["photo_id가 문자열이 아님", JSON.stringify({ photo_id: 1, meal_plan_id: LUNCH })],
  ])("형식이 맞지 않는 이벤트(%s)는 무시한다", (_label, data) => {
    const { mock, onPhotoStatusChanged } = setup();
    act(() => mock.open());

    act(() => mock.connections[0]?.emitRaw(data));

    expect(onPhotoStatusChanged).not.toHaveBeenCalled();
  });

  it("연결이 끊긴 동안 발행한 이벤트는 전달되지 않고, 재연결 open은 전달된다", () => {
    const { bus, mock, onPhotoStatusChanged, onOpen } = setup();
    act(() => mock.open());

    act(() => mock.disconnect());
    act(() => bus.publish(POST_EVENT));
    expect(onPhotoStatusChanged).not.toHaveBeenCalled();

    act(() => mock.open());
    expect(onOpen).toHaveBeenCalledTimes(2);
    act(() => bus.publish(POST_EVENT));
    expect(onPhotoStatusChanged).toHaveBeenCalledTimes(1);
    expect(mock.connect).toHaveBeenCalledTimes(1);
    expect(mock.closeCount()).toBe(0);
  });

  it("StrictMode에서는 connect 2회·close 1회로 열린 연결이 하나만 남는다", () => {
    const bus = createEventBus();
    const mock = createMockConnect(bus);
    const onPhotoStatusChanged = vi.fn();
    render(
      <StrictMode>
        <SystemEventsProvider connect={mock.connect}>
          <Subscriber onPhotoStatusChanged={onPhotoStatusChanged} />
        </SystemEventsProvider>
      </StrictMode>,
    );

    expect(mock.connect).toHaveBeenCalledTimes(2);
    expect(mock.closeCount()).toBe(1);
    expect(mock.connections.filter((source) => !source.closed)).toHaveLength(1);

    act(() => mock.open());
    act(() => bus.publish(POST_EVENT));
    expect(onPhotoStatusChanged).toHaveBeenCalledTimes(1);
  });

  it("데이터가 없는 이벤트는 무시한다", () => {
    const { mock, onPhotoStatusChanged } = setup();
    act(() => mock.open());

    act(() => {
      mock.connections[0]?.dispatchEvent(new Event(PHOTO_STATUS_CHANGED_EVENT));
    });

    expect(onPhotoStatusChanged).not.toHaveBeenCalled();
  });

  it("언마운트하면 연결의 close()를 한 번 부른다", () => {
    const { mock, view } = setup();

    view.unmount();

    expect(mock.closeCount()).toBe(1);
    expect(mock.connections[0]?.close).toHaveBeenCalledTimes(1);
  });

  it("구독 화면이 여럿이면 모두에게 알리고, 언마운트한 구독은 더 받지 않는다", () => {
    const bus = createEventBus();
    const mock = createMockConnect(bus);
    const first = vi.fn();
    const second = vi.fn();
    const view = render(
      <SystemEventsProvider connect={mock.connect}>
        <Subscriber onPhotoStatusChanged={first} />
        <Subscriber onPhotoStatusChanged={second} />
      </SystemEventsProvider>,
    );
    act(() => mock.open());
    act(() => bus.publish(POST_EVENT));
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);

    view.rerender(
      <SystemEventsProvider connect={mock.connect}>
        <Subscriber onPhotoStatusChanged={first} />
      </SystemEventsProvider>,
    );
    act(() => bus.publish(POST_EVENT));

    expect(first).toHaveBeenCalledTimes(2);
    expect(second).toHaveBeenCalledTimes(1);
    expect(mock.connect).toHaveBeenCalledTimes(1);
    expect(mock.closeCount()).toBe(0);
  });

  it("다시 렌더하면 새 콜백을 쓰고 연결은 그대로다", () => {
    const bus = createEventBus();
    const mock = createMockConnect(bus);
    const before = vi.fn();
    const after = vi.fn();
    const view = render(
      <SystemEventsProvider connect={mock.connect}>
        <Subscriber onPhotoStatusChanged={before} />
      </SystemEventsProvider>,
    );
    act(() => mock.open());

    view.rerender(
      <SystemEventsProvider connect={() => mock.connect()}>
        <Subscriber onPhotoStatusChanged={after} />
      </SystemEventsProvider>,
    );
    act(() => bus.publish(POST_EVENT));

    expect(before).not.toHaveBeenCalled();
    expect(after).toHaveBeenCalledTimes(1);
    expect(mock.connect).toHaveBeenCalledTimes(1);
    expect(mock.closeCount()).toBe(0);
  });

  it("onOpen만 구독해도 이벤트에서 오류가 나지 않는다", () => {
    const bus = createEventBus();
    const mock = createMockConnect(bus);
    const onOpen = vi.fn();
    render(
      <SystemEventsProvider connect={mock.connect}>
        <Subscriber onOpen={onOpen} />
      </SystemEventsProvider>,
    );

    act(() => mock.open());
    act(() => bus.publish(POST_EVENT));

    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  describe("기본 연결", () => {
    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it("connect를 주지 않으면 EventSource('/api/events')를 열고 언마운트 때 닫는다", () => {
      const close = vi.fn();
      const EventSourceStub = vi.fn(function (this: Record<string, unknown>) {
        this.addEventListener = vi.fn();
        this.close = close;
      });
      vi.stubGlobal("EventSource", EventSourceStub);

      const view = render(
        <SystemEventsProvider>
          <Subscriber />
        </SystemEventsProvider>,
      );

      expect(EventSourceStub).toHaveBeenCalledTimes(1);
      expect(EventSourceStub).toHaveBeenCalledWith("/api/events");
      view.unmount();
      expect(close).toHaveBeenCalledTimes(1);
    });
  });
});

describe("useSystemEvents", () => {
  it("Provider 밖에서 쓰면 오류를 던진다", () => {
    // React가 렌더 오류를 콘솔에 남기므로 이 테스트에서만 출력을 막는다.
    const spy = vi.spyOn(globalThis.console, "error").mockImplementation(() => {});
    try {
      expect(() => render(<Subscriber />)).toThrow(/SystemEventsProvider/);
    } finally {
      spy.mockRestore();
    }
  });
});
