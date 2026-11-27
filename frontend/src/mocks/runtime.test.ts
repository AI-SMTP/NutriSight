// 모의 처리 단계 런타임(runtime.ts) 테스트. 공용 서버의 기본 핸들러를 임시 계약 호출 함수로 부르고,
// 모의 이벤트 버스로 나간 `photo.status_changed`를 모아 순서를 확인한다.
// 단계 타이머는 가짜 타이머(setTimeout·clearTimeout만)로 돌린다.
import {
  recordStaffZero,
  uploadBaseline,
  uploadPostPhoto,
  type Meal,
  type PhotoStatusChangedEvent,
} from "../api/provisional";
import { jpegBlob } from "../test/apiError";
import { useNodeFileForMultipart } from "../test/nodeFile";
import { eventBus } from "./eventBus";
import { DEMO_DATE, mealOrderId } from "./fixtures";
import { installMockRuntime as install } from "./runtime";
import { mockState } from "./state";
import type { MockOrder, MockPhoto } from "./types";

const STEP_MS = 100;
const LUNCH_PLAN = `${DEMO_DATE}_lunch_general`;
const DINNER_PLAN = `${DEMO_DATE}_dinner_general`;
/** 처리 단계 전체(스펙 3.4절) */
const FULL = [
  "uploaded",
  "queued",
  "analyzing:intake",
  "analyzing:nutrition",
  "analyzing:alert",
  "done",
];
/** 재처리(기준 사진 등록·교체) 단계 */
const REPROCESS = FULL.slice(1);

let events: PhotoStatusChangedEvent[] = [];
let unsubscribe: () => void = () => undefined;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  events = [];
  unsubscribe = eventBus.subscribe((event) => {
    events = [...events, event];
  });
});

afterEach(() => {
  unsubscribe();
  vi.useRealTimers();
});

/** 이벤트 하나를 `status`(분석 중이면 `analyzing:<stage>`)로 줄인다 */
function label(event: PhotoStatusChangedEvent): string {
  return event.status === "analyzing" ? `analyzing:${event.stage}` : event.status;
}

/** 사진 하나에 대해 나간 이벤트 순서 */
function trail(photoId: string): string[] {
  return events.filter((e) => e.photo_id === photoId).map(label);
}

function photoOf(photoId: string): MockPhoto {
  const photo = mockState.get().photos.find((p) => p.photo_id === photoId);
  if (!photo) throw new Error(`${photoId} 사진이 없다`);
  return photo;
}

function orderOf(patientId: string, meal: Meal = "lunch"): MockOrder {
  const id = mealOrderId(patientId, DEMO_DATE, meal);
  const order = mockState.get().orders.find((o) => o.meal_order_id === id);
  if (!order) throw new Error(`${id} 발주가 없다`);
  return order;
}

async function upload(patientId: string, meal: Meal = "lunch"): Promise<string> {
  const accepted = await uploadPostPhoto({ patientId, date: DEMO_DATE, meal, blob: jpegBlob() });
  return accepted.photo_id;
}

async function registerBaseline(meal: Meal): Promise<string> {
  const baseline = await uploadBaseline(DEMO_DATE, meal, jpegBlob());
  return baseline.photo_id;
}

describe("처리 단계(자동 진행)", () => {
  useNodeFileForMultipart();

  it("uploaded부터 done까지 단계마다 사진 상태·발주 record_status를 바꾸고 이벤트를 낸다", async () => {
    install({ stepDelayMs: STEP_MS });
    const photoId = await upload("NS03");

    expect(trail(photoId)).toEqual(["uploaded"]);
    expect(orderOf("NS03").record_status).toBe("pending");

    vi.advanceTimersByTime(STEP_MS * 3);
    expect(trail(photoId)).toEqual(FULL.slice(0, 4));
    expect(photoOf(photoId)).toMatchObject({ status: "analyzing", stage: "nutrition" });
    expect(orderOf("NS03").record_status).toBe("pending");

    vi.runAllTimers();
    expect(trail(photoId)).toEqual(FULL);
    expect(photoOf(photoId)).toMatchObject({ status: "done", stage: "alert" });
    expect(orderOf("NS03").record_status).toBe("recorded");
    expect(events.at(-1)).toEqual({
      photo_id: photoId,
      kind: "post",
      patient_id: "NS03",
      meal_plan_id: LUNCH_PLAN,
      meal_order_id: mealOrderId("NS03", DEMO_DATE, "lunch"),
      status: "done",
      stage: "alert",
      outcome: "no_change",
      at: expect.any(String) as unknown,
    });
    expect(events.slice(0, -1).every((e) => !("outcome" in e))).toBe(true);
  });

  it("stepDelayMs 0이면 다음 타이머 차례에 끝까지 진행한다", async () => {
    install({ stepDelayMs: 0 });
    const photoId = await upload("NS03");

    vi.runAllTimers();

    expect(trail(photoId)).toEqual(FULL);
  });

  it.each([
    ["not_determinable", "not_determinable"],
    ["failed", "failed"],
  ] as const)("주입한 결과 %s면 섭취 추정 단계에서 끝나고 발주는 %s다", async (result, record) => {
    install({ stepDelayMs: 0, resolveResult: () => result });
    const photoId = await upload("NS03");

    vi.runAllTimers();

    expect(trail(photoId)).toEqual([...FULL.slice(0, 3), result]);
    expect(photoOf(photoId)).toMatchObject({ status: result, stage: "intake" });
    expect(orderOf("NS03").record_status).toBe(record);
  });

  it("기준 사진이 없는 끼니의 업로드는 waiting_baseline 이벤트 하나만 내고 진행하지 않는다", async () => {
    install({ stepDelayMs: 0 });
    const photoId = await upload("NS03", "dinner");

    vi.runAllTimers();

    expect(trail(photoId)).toEqual(["waiting_baseline"]);
    expect(photoOf(photoId).status).toBe("waiting_baseline");
  });
});

describe("기준 사진 등록·교체(스펙 2절 모의 핸들러 테스트)", () => {
  useNodeFileForMultipart();

  it("analyzing 중 재등록하면 지금 처리를 마친 뒤 queued부터 한 번 더 처리한다", async () => {
    install({ stepDelayMs: STEP_MS });
    const photoId = await upload("NS03");
    vi.advanceTimersByTime(STEP_MS * 2);
    expect(photoOf(photoId)).toMatchObject({ status: "analyzing", stage: "intake" });

    const baselineId = await registerBaseline("lunch");
    expect(photoOf(photoId).status).toBe("analyzing");
    vi.runAllTimers();

    expect(trail(photoId)).toEqual([...FULL, ...REPROCESS]);
    const order = events.map((e) => (e.photo_id === baselineId ? "baseline" : label(e)));
    expect(order.indexOf("baseline")).toBe(3);
    expect(photoOf(photoId).status).toBe("done");
    expect(orderOf("NS03").record_status).toBe("recorded");
  });

  it("점심 재등록: 완료·재촬영 필요 사진이 queued부터 다시 처리되고 pending, 전량 거부는 그대로", async () => {
    const runtime = install({ stepDelayMs: 0, manualSteps: true });
    const reprocessed = ["NS02", "NS05", "NS07", "NS10"];

    const baselineId = await registerBaseline("lunch");

    expect(events[0]).toMatchObject({ photo_id: baselineId, kind: "baseline" });
    for (const patientId of reprocessed) {
      const photoId = `fx_lunch_${patientId}`;
      expect(trail(photoId)).toEqual(["queued"]);
      expect(photoOf(photoId)).toMatchObject({ status: "queued", stage: null });
      expect(orderOf(patientId).record_status).toBe("pending");
    }
    expect(orderOf("NS06")).toMatchObject({
      record_status: "recorded",
      staff_zero_reason: "refused",
    });
    expect(events.some((e) => e.meal_order_id === mealOrderId("NS06", DEMO_DATE, "lunch"))).toBe(
      false,
    );

    runtime.finishAll();
    for (const patientId of reprocessed) {
      expect(trail(`fx_lunch_${patientId}`)).toEqual(REPROCESS);
      expect(orderOf(patientId).record_status).toBe("recorded");
    }
  });

  it("교체 때 실패(failed) 사진도 queued부터 다시 처리한다", async () => {
    mockState.reset({
      photos: { fx_lunch_NS02: { status: "failed", stage: "intake" } },
      orders: { [mealOrderId("NS02", DEMO_DATE, "lunch")]: { record_status: "failed" } },
    });
    const runtime = install({ stepDelayMs: 0, manualSteps: true });

    await registerBaseline("lunch");
    expect(orderOf("NS02").record_status).toBe("pending");
    runtime.finishAll();

    expect(trail("fx_lunch_NS02")).toEqual(REPROCESS);
    expect(orderOf("NS02").record_status).toBe("recorded");
  });

  it("재촬영 필요에서 전량 기록한 발주는 기준 교체 뒤에도 recorded + refused다", async () => {
    const runtime = install({ stepDelayMs: 0 });
    await recordStaffZero(mealOrderId("NS05", DEMO_DATE, "lunch"), "refused");

    await registerBaseline("lunch");
    runtime.finishAll();
    vi.runAllTimers();

    expect(orderOf("NS05")).toMatchObject({
      record_status: "recorded",
      staff_zero_reason: "refused",
      post_photo_id: null,
    });
    expect(trail("fx_lunch_NS05")).toEqual([]);
    expect(photoOf("fx_lunch_NS05").status).toBe("not_determinable");
  });

  it("대기 사진이 없는 끼니(저녁)에도 kind baseline 이벤트를 낸다", async () => {
    install({ stepDelayMs: 0 });

    const baselineId = await registerBaseline("dinner");
    vi.runAllTimers();

    expect(events).toEqual([
      {
        photo_id: baselineId,
        kind: "baseline",
        meal_plan_id: DINNER_PLAN,
        patient_id: null,
        meal_order_id: null,
        status: "uploaded",
        stage: null,
        at: expect.any(String) as unknown,
      },
    ]);
  });

  it("최초 등록: waiting_baseline 사진을 queued부터 처리한다", async () => {
    install({ stepDelayMs: 0 });
    const photoId = await upload("NS03", "dinner");

    const baselineId = await registerBaseline("dinner");
    vi.runAllTimers();

    expect(trail(photoId)).toEqual(["waiting_baseline", ...REPROCESS]);
    expect(events[1]).toMatchObject({ photo_id: baselineId, kind: "baseline" });
    expect(orderOf("NS03", "dinner").record_status).toBe("recorded");
  });

  it("최초 등록은 이미 끝난 사진을 다시 처리하지 않는다(계획 overrides로 기준 사진 제거)", async () => {
    mockState.reset({ plans: { [LUNCH_PLAN]: { baseline_photo_id: null } } });
    install({ stepDelayMs: 0 });
    const photoId = await upload("NS03");

    await registerBaseline("lunch");
    vi.runAllTimers();

    expect(trail(photoId)).toEqual(["waiting_baseline", ...REPROCESS]);
    expect(trail("fx_lunch_NS02")).toEqual([]);
    expect(photoOf("fx_lunch_NS02").status).toBe("done");
  });
});

describe("수동 모드와 finishAll()", () => {
  useNodeFileForMultipart();

  it("수동 모드는 첫 analyzing(intake)에서 멈추고 finishAll() 뒤 done이 된다", async () => {
    const runtime = install({ stepDelayMs: STEP_MS, manualSteps: true });
    const photoId = await upload("NS03");

    vi.runAllTimers();
    expect(trail(photoId)).toEqual(FULL.slice(0, 3));
    expect(orderOf("NS03").record_status).toBe("pending");

    runtime.finishAll();
    expect(trail(photoId)).toEqual(FULL);
    expect(photoOf(photoId).status).toBe("done");
    expect(orderOf("NS03").record_status).toBe("recorded");
  });

  it.each([
    ["uploaded", 0],
    ["queued", STEP_MS],
    ["analyzing:intake", STEP_MS * 2],
  ])("%s 시점에 부르면 남은 단계를 한 번씩만 보내 done·recorded로 끝낸다", async (at, waitMs) => {
    const runtime = install({ stepDelayMs: STEP_MS, manualSteps: true });
    const photoId = await upload("NS03");
    vi.advanceTimersByTime(waitMs);
    expect(trail(photoId).at(-1)).toBe(at);

    runtime.finishAll();

    expect(trail(photoId)).toEqual(FULL);
    expect(photoOf(photoId).status).toBe("done");
    expect(orderOf("NS03").record_status).toBe("recorded");
    expect(vi.getTimerCount()).toBe(0);

    vi.advanceTimersByTime(STEP_MS * 20);
    vi.runAllTimers();
    expect(trail(photoId)).toEqual(FULL);
  });

  it("재분석 예약이 걸린 사진의 결과가 not_determinable이어도 예약된 재처리를 한다", async () => {
    const runtime = install({
      stepDelayMs: STEP_MS,
      manualSteps: true,
      resolveResult: () => "not_determinable",
    });
    const photoId = await upload("NS03");
    vi.runAllTimers();

    await registerBaseline("lunch");
    runtime.finishAll();

    const once = ["queued", "analyzing:intake", "not_determinable"];
    expect(trail(photoId)).toEqual(["uploaded", ...once, ...once]);
    expect(photoOf(photoId).status).toBe("not_determinable");
    expect(orderOf("NS03").record_status).toBe("not_determinable");
  });

  it("종료 이벤트를 받은 구독자가 기준 사진을 교체해도 재시작한 처리를 끝까지 진행한다", async () => {
    const runtime = install({ stepDelayMs: 0 });
    const photoId = await upload("NS03");
    let replaced = false;
    const stop = eventBus.subscribe((event) => {
      if (replaced || event.photo_id !== photoId || event.status !== "done") return;
      replaced = true;
      runtime.baselineRegistered({ photoId: "fx_lunch_baseline", replaced: true });
    });

    vi.runAllTimers();
    stop();

    expect(trail(photoId)).toEqual([...FULL, ...REPROCESS]);
    expect(photoOf(photoId).status).toBe("done");
    expect(orderOf("NS03").record_status).toBe("recorded");
  });

  it("재분석 예약이 걸린 analyzing 사진은 현재 처리 뒤 queued부터 재처리까지 끝낸다", async () => {
    const runtime = install({ stepDelayMs: STEP_MS, manualSteps: true });
    const photoId = await upload("NS03");
    vi.runAllTimers();

    await registerBaseline("lunch");
    runtime.finishAll();

    expect(trail(photoId)).toEqual([...FULL, ...REPROCESS]);
    expect(photoOf(photoId).status).toBe("done");
    expect(orderOf("NS03").record_status).toBe("recorded");
    vi.runAllTimers();
    expect(trail(photoId)).toEqual([...FULL, ...REPROCESS]);
  });

  it("교체 때 이미 처리 중이던 픽스처 사진(NS04 analyzing·NS09 queued)도 예약대로 재처리까지 끝낸다", async () => {
    const runtime = install({ stepDelayMs: STEP_MS, manualSteps: true });

    await registerBaseline("lunch");
    runtime.finishAll();

    expect(trail("fx_lunch_NS04")).toEqual([...FULL.slice(3), ...REPROCESS]);
    expect(trail("fx_lunch_NS09")).toEqual([...FULL.slice(2), ...REPROCESS]);
    expect(orderOf("NS04").record_status).toBe("recorded");
    expect(orderOf("NS09").record_status).toBe("recorded");
  });

  it("같은 끼니의 waiting_baseline 사진은 finishAll() 뒤에도 그대로다", async () => {
    mockState.reset({ photos: { fx_lunch_NS09: { status: "waiting_baseline", stage: null } } });
    const runtime = install({ stepDelayMs: STEP_MS, manualSteps: true });
    const photoId = await upload("NS03");

    runtime.finishAll();

    expect(photoOf(photoId).status).toBe("done");
    expect(photoOf("fx_lunch_NS09").status).toBe("waiting_baseline");
    expect(trail("fx_lunch_NS09")).toEqual([]);
  });
});

describe("런타임 정리", () => {
  useNodeFileForMultipart();

  it("공용 테스트 설정의 런타임은 업로드 뒤 단계를 스스로 진행하지 않는다", async () => {
    const photoId = await upload("NS03");

    vi.advanceTimersByTime(60 * 60 * 1000);

    expect(trail(photoId)).toEqual(["uploaded"]);
    expect(photoOf(photoId).status).toBe("uploaded");
  });

  it("mockState.reset()은 단계 타이머를 취소해, 번호가 다시 쓰인 새 사진을 건드리지 않는다", async () => {
    const runtime = install({ stepDelayMs: STEP_MS });
    const before = await upload("NS03");
    expect(vi.getTimerCount()).toBe(1);
    mockState.reset();
    expect(vi.getTimerCount()).toBe(0);
    events = [];

    const after = await upload("NS03", "dinner");
    expect(after).toBe(before);
    vi.advanceTimersByTime(STEP_MS * 20);
    runtime.finishAll();

    expect(photoOf(after).status).toBe("waiting_baseline");
    expect(trail(after)).toEqual(["waiting_baseline"]);
  });

  it("installMockRuntime은 이전 런타임을 정리하고 새 런타임이 핸들러를 맡는다", async () => {
    install({ stepDelayMs: STEP_MS });
    const first = await upload("NS03");
    install({ stepDelayMs: STEP_MS, manualSteps: true });

    vi.runAllTimers();
    expect(trail(first)).toEqual(["uploaded"]);

    const second = await upload("NS08");
    vi.runAllTimers();
    expect(trail(second)).toEqual(FULL.slice(0, 3));
  });
});
