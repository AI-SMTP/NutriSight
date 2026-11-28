// 모의 픽스처(fixtures.ts)와 모의 상태 보관소(state.ts) 테스트.
import { createInitialState, DEMO_DATE, mealOrderId, NPO_PATIENT_ID } from "./fixtures";
import { mockState } from "./state";

const NS03_LUNCH = mealOrderId("NS03", DEMO_DATE, "lunch");

describe("createInitialState", () => {
  it("부를 때마다 새 객체를 만든다", () => {
    const a = createInitialState();
    const b = createInitialState();

    expect(a).not.toBe(b);
    expect(a.orders).not.toBe(b.orders);
    expect(a.orders[0]).not.toBe(b.orders[0]);
    expect(a).toEqual(b);
  });

  it("시연일 세 끼 배식 계획과 환자 10명의 끼니별 발주를 둔다", () => {
    const state = createInitialState();

    expect(state.demoDate).toBe("2026-11-27");
    expect(state.plans.map((p) => p.meal_plan_id)).toEqual([
      "2026-11-27_breakfast_general",
      "2026-11-27_lunch_general",
      "2026-11-27_dinner_general",
    ]);
    expect(state.patients.map((p) => p.patient_id)).toEqual([
      "NS01",
      "NS02",
      "NS03",
      "NS04",
      "NS05",
      "NS06",
      "NS07",
      "NS08",
      "NS09",
      "NS10",
    ]);
    expect(state.orders).toHaveLength(30);
  });

  it("금식 환자 한 명은 세 끼 모두 npo다", () => {
    const state = createInitialState();
    const npoOrders = state.orders.filter((o) => o.order_status === "npo");

    expect(npoOrders).toHaveLength(3);
    expect(new Set(npoOrders.map((o) => o.patient_id))).toEqual(new Set([NPO_PATIENT_ID]));
  });

  it("기본 픽스처에는 취소 발주가 없다", () => {
    const state = createInitialState();

    expect(state.orders.some((o) => o.order_status === "cancelled")).toBe(false);
  });

  it("overrides로 특정 발주를 바꾼다(다른 발주와 기본값은 그대로)", () => {
    const state = createInitialState({
      overrides: { orders: { [NS03_LUNCH]: { order_status: "cancelled" } } },
    });
    const fresh = createInitialState();

    expect(state.orders.find((o) => o.meal_order_id === NS03_LUNCH)).toMatchObject({
      order_status: "cancelled",
      record_status: "not_recorded",
    });
    expect(state.orders.filter((o) => o.meal_order_id !== NS03_LUNCH)).toEqual(
      fresh.orders.filter((o) => o.meal_order_id !== NS03_LUNCH),
    );
  });

  it("overrides에서 null을 준 발주는 뺀다", () => {
    const state = createInitialState({ overrides: { orders: { [NS03_LUNCH]: null } } });

    expect(state.orders.some((o) => o.meal_order_id === NS03_LUNCH)).toBe(false);
    expect(state.orders).toHaveLength(29);
  });

  it("없는 발주 ID를 overrides에 주면 오타를 알리도록 던진다", () => {
    expect(() =>
      createInitialState({ overrides: { orders: { "NS99_2026-11-27_lunch": null } } }),
    ).toThrow("NS99_2026-11-27_lunch");
  });
});

describe("createInitialState overrides(사진·계획)", () => {
  it("photos로 특정 사진의 상태를 바꾼다(다른 사진은 그대로)", () => {
    const state = createInitialState({
      overrides: { photos: { fx_lunch_NS02: { status: "failed", stage: "intake" } } },
    });
    const base = createInitialState();

    expect(state.photos.find((p) => p.photo_id === "fx_lunch_NS02")).toMatchObject({
      status: "failed",
      stage: "intake",
      kind: "post",
    });
    expect(state.photos.filter((p) => p.photo_id !== "fx_lunch_NS02")).toEqual(
      base.photos.filter((p) => p.photo_id !== "fx_lunch_NS02"),
    );
  });

  it("plans로 끼니의 기준 사진 연결을 바꾼다", () => {
    const lunchId = `${DEMO_DATE}_lunch_general`;
    const state = createInitialState({
      overrides: { plans: { [lunchId]: { baseline_photo_id: null } } },
    });

    expect(state.plans.find((p) => p.meal_plan_id === lunchId)?.baseline_photo_id).toBeNull();
    expect(
      state.plans.find((p) => p.meal_plan_id === `${DEMO_DATE}_breakfast_general`)
        ?.baseline_photo_id,
    ).toBe("fx_breakfast_baseline");
  });

  it("없는 사진 ID나 계획 ID를 주면 던진다", () => {
    expect(() =>
      createInitialState({ overrides: { photos: { fx_missing: { status: "done" } } } }),
    ).toThrow(/fx_missing/);
    expect(() =>
      createInitialState({
        overrides: { plans: { "2026-11-28_lunch_general": { baseline_photo_id: null } } },
      }),
    ).toThrow(/2026-11-28_lunch_general/);
  });
});

describe("mockState", () => {
  it("reset은 등록한 정리 콜백을 부르고, 해제한 콜백은 부르지 않는다", () => {
    const kept = vi.fn();
    const removed = vi.fn();
    const unsubscribeKept = mockState.onReset(kept);
    const unsubscribeRemoved = mockState.onReset(removed);
    unsubscribeRemoved();

    mockState.reset();

    expect(kept).toHaveBeenCalledTimes(1);
    expect(removed).not.toHaveBeenCalled();
    unsubscribeKept();
  });

  it("update는 새 상태로 바꾸고 reset은 픽스처 초기값으로 되돌린다", () => {
    const before = mockState.get();

    mockState.update((state) => ({ ...state, orders: [] }));
    expect(mockState.get().orders).toEqual([]);
    expect(before.orders).toHaveLength(30);

    mockState.reset();
    expect(mockState.get()).toEqual(createInitialState());
  });

  it("reset(overrides)는 주입한 값으로 시작한다", () => {
    mockState.reset({ orders: { [NS03_LUNCH]: { order_status: "cancelled" } } });

    expect(mockState.get().orders.find((o) => o.meal_order_id === NS03_LUNCH)?.order_status).toBe(
      "cancelled",
    );
  });
});
