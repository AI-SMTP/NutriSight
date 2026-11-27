// 모의 REST 핸들러(handlers.ts) 테스트. 공용 서버의 기본 핸들러를 임시 계약 호출 함수로 부른다.
// 모의 상태는 공용 설정(src/test/setup.ts)의 afterEach에서 픽스처 초기값으로 되돌아간다.
import {
  getMeal,
  getMeta,
  recordStaffZero,
  uploadBaseline,
  uploadPostPhoto,
  type ApiErrorKind,
  type Meal,
  type MealDetail,
  type MealOrderSummary,
} from "../api/provisional";
import { orderBadge } from "../lib/mealStatus";
import { expectApiError, jpegBlob } from "../test/apiError";
import { useNodeFileForMultipart } from "../test/nodeFile";
import { DEMO_DATE, mealOrderId, NPO_PATIENT_ID } from "./fixtures";
import { errorHandlers } from "./handlers";
import { server } from "./server";
import { mockState } from "./state";

function orderOf(detail: MealDetail, patientId: string): MealOrderSummary {
  const order = detail.orders.find((o) => o.patient_id === patientId);
  if (!order) throw new Error(`${patientId} 발주가 없다`);
  return order;
}

async function lunchOrder(patientId: string): Promise<MealOrderSummary> {
  return orderOf(await getMeal(DEMO_DATE, "lunch"), patientId);
}

function upload(patientId: string, meal: Meal = "lunch", date = DEMO_DATE) {
  return uploadPostPhoto({ patientId, date, meal, blob: jpegBlob() });
}

describe("GET /api/meta", () => {
  it("시연일을 돌려준다", async () => {
    await expect(getMeta()).resolves.toEqual({ demo_date: "2026-11-27" });
  });
});

describe("GET /api/meals/:date/:meal 픽스처", () => {
  it("아침: D0 메뉴 6칸(합계 698 kcal), 기준 사진 있음, NS03 미기록", async () => {
    const detail = await getMeal(DEMO_DATE, "breakfast");

    expect(detail.meal_plan_id).toBe("2026-11-27_breakfast_general");
    expect(detail.slots.map((s) => s.menu_name)).toEqual([
      "쌀밥",
      "어묵국",
      "달걀야채찜",
      "시금치나물",
      "마늘종볶음",
      "열무김치",
    ]);
    expect(detail.slots.reduce((sum, s) => sum + s.energy_kcal, 0)).toBe(698);
    expect(detail.baseline_photo).not.toBeNull();
    expect(orderBadge(orderOf(detail, "NS03")).kind).toBe("not_recorded");
  });

  it("칸 ID·위치·종류는 시드 표기를 그대로 쓴다", async () => {
    const { slots } = await getMeal(DEMO_DATE, "lunch");

    expect(slots.map((s) => [s.slot_id, s.position, s.dish_type])).toEqual([
      ["slot_1", "아랫줄 왼쪽", "rice"],
      ["slot_2", "아랫줄 오른쪽", "soup"],
      ["slot_3", "윗줄 1 (왼쪽 끝)", "main"],
      ["slot_4", "윗줄 2", "side"],
      ["slot_5", "윗줄 3", "side"],
      ["slot_6", "윗줄 4 (오른쪽 끝)", "kimchi"],
    ]);
    expect(slots[2]).toMatchObject({ menu_name: "소불고기", served_g: 90, energy_kcal: 250 });
    expect(slots[2]?.protein_g).toBeCloseTo(25);
  });

  it("점심: 기준 사진 있음, NS03 미기록, 여섯 가지 배지 대상이 모두 있다", async () => {
    const detail = await getMeal(DEMO_DATE, "lunch");
    const labels = new Set(detail.orders.map((o) => orderBadge(o).label));

    expect(detail.baseline_photo).not.toBeNull();
    expect(orderBadge(orderOf(detail, "NS03")).kind).toBe("not_recorded");
    for (const label of ["미기록", "처리 중", "완료", "재촬영 필요", "완료 · 전량 거부", "금식"]) {
      expect(labels).toContain(label);
    }
  });

  it("점심 발주 요약에 환자 이름·병실과 발주 ID가 있다", async () => {
    const detail = await getMeal(DEMO_DATE, "lunch");

    expect(detail.orders).toHaveLength(10);
    expect(orderOf(detail, "NS03")).toMatchObject({
      meal_order_id: "NS03_2026-11-27_lunch",
      display_name: "NS03",
      room: "302호",
      post_photo: null,
    });
    expect(orderOf(detail, NPO_PATIENT_ID).order_status).toBe("npo");
  });

  it("저녁: 기준 사진 없음, 식사가 나가는 발주는 모두 미기록", async () => {
    const detail = await getMeal(DEMO_DATE, "dinner");
    const ordered = detail.orders.filter((o) => o.order_status === "ordered");

    expect(detail.baseline_photo).toBeNull();
    expect(ordered).toHaveLength(9);
    expect(ordered.every((o) => orderBadge(o).kind === "not_recorded")).toBe(true);
  });

  it.each([
    ["없는 날짜", "2026-11-28", "lunch"],
    ["없는 끼니", DEMO_DATE, "brunch"],
  ])("%s는 404다", async (_label, date, meal) => {
    await expectApiError(getMeal(date, meal as Meal), "not_found", 404);
  });
});

describe("POST /api/meals/:date/:meal/baseline", () => {
  useNodeFileForMultipart();

  it("201로 기준 사진을 등록하고 끼니 조회에 반영한다", async () => {
    const created = await uploadBaseline(DEMO_DATE, "dinner", jpegBlob());

    expect(created.photo_id).toEqual(expect.any(String));
    expect((await getMeal(DEMO_DATE, "dinner")).baseline_photo).toEqual(created);
  });

  it("배식 계획이 없으면 404다", async () => {
    await expectApiError(uploadBaseline("2026-11-28", "dinner", jpegBlob()), "not_found", 404);
  });

  it("file 필드가 없으면 422다", async () => {
    const response = await fetch(`${location.origin}/api/meals/${DEMO_DATE}/dinner/baseline`, {
      method: "POST",
      body: new FormData(),
    });

    expect(response.status).toBe(422);
  });
});

describe("POST /api/photos 성공", () => {
  useNodeFileForMultipart();

  it("기준 사진이 있는 끼니면 202 uploaded, 발주는 처리 중이 된다", async () => {
    const accepted = await upload("NS03");
    const order = await lunchOrder("NS03");

    expect(accepted).toMatchObject({ meal_order_id: "NS03_2026-11-27_lunch", status: "uploaded" });
    expect(order).toMatchObject({
      record_status: "pending",
      post_photo: { photo_id: accepted.photo_id, status: "uploaded", stage: null },
    });
    expect(orderBadge(order).label).toBe("처리 중");
  });

  it("기준 사진이 없는 끼니면 waiting_baseline에 머문다", async () => {
    const accepted = await upload("NS03", "dinner");
    const order = orderOf(await getMeal(DEMO_DATE, "dinner"), "NS03");

    expect(accepted.status).toBe("waiting_baseline");
    expect(orderBadge(order).label).toBe("처리 중 · 기준 사진 대기");
  });

  it("재촬영 필요 발주에 올리면 새 사진이 이전 사진을 대신하고 이전 사진 행은 남는다", async () => {
    const previous = (await lunchOrder("NS05")).post_photo;
    expect(previous?.status).toBe("not_determinable");

    const accepted = await upload("NS05");
    const order = await lunchOrder("NS05");

    expect(accepted.photo_id).not.toBe(previous?.photo_id);
    expect(order.post_photo?.photo_id).toBe(accepted.photo_id);
    expect(order.record_status).toBe("pending");
    expect(mockState.get().photos.map((p) => p.photo_id)).toContain(previous?.photo_id);
  });

  it("multipart 필드가 빠지면 422다", async () => {
    const form = new FormData();
    form.append("file", jpegBlob(), "photo.jpg");
    form.append("patient_id", "NS03");
    const response = await fetch(`${location.origin}/api/photos`, { method: "POST", body: form });

    expect(response.status).toBe(422);
  });
});

describe("POST /api/photos 본문 형식", () => {
  it("multipart가 아닌 본문은 422다(formData 파싱 실패)", async () => {
    const response = await fetch(`${location.origin}/api/photos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient_id: "NS03" }),
    });

    expect(response.status).toBe(422);
  });
});

describe("POST /api/photos 409·404", () => {
  useNodeFileForMultipart();

  it("발주가 없으면(계획·환자는 있음) 409다", async () => {
    mockState.reset({ orders: { [mealOrderId("NS03", DEMO_DATE, "lunch")]: null } });

    await expectApiError(upload("NS03"), "conflict", 409);
  });

  it("금식(npo) 발주는 409다", async () => {
    await expectApiError(upload(NPO_PATIENT_ID), "conflict", 409);
  });

  it("주입한 취소(cancelled) 발주는 409다", async () => {
    mockState.reset({
      orders: { [mealOrderId("NS03", DEMO_DATE, "lunch")]: { order_status: "cancelled" } },
    });

    await expectApiError(upload("NS03"), "conflict", 409);
  });

  it.each([
    ["처리 중", "NS04"],
    ["완료", "NS02"],
    ["완료 · 전량 거부", "NS06"],
  ])("%s 환자(%s) 업로드는 409다", async (label, patientId) => {
    expect(orderBadge(await lunchOrder(patientId)).label).toBe(label);

    await expectApiError(upload(patientId), "conflict", 409);
  });

  it("처리 실패(record_status failed) 발주 업로드는 409다", async () => {
    mockState.reset({
      orders: { [mealOrderId("NS03", DEMO_DATE, "lunch")]: { record_status: "failed" } },
    });
    expect(orderBadge(await lunchOrder("NS03")).label).toBe("처리 중");

    await expectApiError(upload("NS03"), "conflict", 409);
  });

  it("방금 올려 처리 중이 된 환자에 다시 올리면 409다", async () => {
    await upload("NS03");

    await expectApiError(upload("NS03"), "conflict", 409);
  });

  it("없는 환자는 404다", async () => {
    await expectApiError(upload("NS99"), "not_found", 404);
  });

  it("없는 배식 계획(날짜)은 404다", async () => {
    await expectApiError(upload("NS03", "lunch", "2026-11-28"), "not_found", 404);
  });
});

describe("POST /api/meal-orders/:id/staff-zero", () => {
  const NS03_LUNCH = mealOrderId("NS03", DEMO_DATE, "lunch");

  it("200으로 recorded와 사유를 저장하고 배지가 완료 · 전량 거부가 된다", async () => {
    await expect(recordStaffZero(NS03_LUNCH, "refused")).resolves.toEqual({
      meal_order_id: NS03_LUNCH,
      record_status: "recorded",
      staff_zero_reason: "refused",
    });
    const order = await lunchOrder("NS03");

    expect(order).toMatchObject({ record_status: "recorded", staff_zero_reason: "refused" });
    expect(orderBadge(order).label).toBe("완료 · 전량 거부");
  });

  it("전량 미섭취 사유도 저장한다", async () => {
    await recordStaffZero(NS03_LUNCH, "not_eaten");

    expect(orderBadge(await lunchOrder("NS03")).label).toBe("완료 · 전량 미섭취");
  });

  it("재촬영 필요 발주를 전량 기록하면 사진 행은 남기고 post_photo_id 연결을 끊는다", async () => {
    const previous = (await lunchOrder("NS05")).post_photo;

    await recordStaffZero(mealOrderId("NS05", DEMO_DATE, "lunch"), "refused");
    const order = await lunchOrder("NS05");

    expect(order).toMatchObject({ record_status: "recorded", post_photo: null });
    expect(mockState.get().photos.map((p) => p.photo_id)).toContain(previous?.photo_id);
    expect(
      mockState.get().orders.find((o) => o.meal_order_id === order.meal_order_id)?.post_photo_id,
    ).toBeNull();
  });

  it("금식(npo) 발주는 409다", async () => {
    await expectApiError(
      recordStaffZero(mealOrderId(NPO_PATIENT_ID, DEMO_DATE, "lunch"), "refused"),
      "conflict",
      409,
    );
  });

  it("주입한 취소(cancelled) 발주는 409다", async () => {
    mockState.reset({ orders: { [NS03_LUNCH]: { order_status: "cancelled" } } });

    await expectApiError(recordStaffZero(NS03_LUNCH, "refused"), "conflict", 409);
  });

  it.each([
    ["처리 중", "NS04"],
    ["완료", "NS02"],
    ["완료 · 전량 거부", "NS06"],
  ])("%s 발주(%s) 전량 기록은 409다", async (_label, patientId) => {
    const id = mealOrderId(patientId, DEMO_DATE, "lunch");

    await expectApiError(recordStaffZero(id, "not_eaten"), "conflict", 409);
  });

  it("없는 발주 ID는 404다", async () => {
    await expectApiError(recordStaffZero("NS99_2026-11-27_lunch", "refused"), "not_found", 404);
  });

  it("없는 발주 ID라도 reason이 잘못되면 본문 검증이 먼저라 422다", async () => {
    const response = await fetch(
      `${location.origin}/api/meal-orders/NS99_2026-11-27_lunch/staff-zero`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "skipped" }),
      },
    );

    expect(response.status).toBe(422);
  });

  it("처리 실패(record_status failed) 발주 전량 기록은 409다", async () => {
    mockState.reset({ orders: { [NS03_LUNCH]: { record_status: "failed" } } });
    expect(orderBadge(await lunchOrder("NS03")).label).toBe("처리 중");

    await expectApiError(recordStaffZero(NS03_LUNCH, "refused"), "conflict", 409);
  });

  it("reason이 refused·not_eaten이 아니면 422다", async () => {
    const response = await fetch(`${location.origin}/api/meal-orders/${NS03_LUNCH}/staff-zero`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "skipped" }),
    });

    expect(response.status).toBe(422);
  });
});

describe("errorHandlers", () => {
  useNodeFileForMultipart();

  const calls = {
    meta: () => getMeta(),
    meal: () => getMeal(DEMO_DATE, "lunch"),
    baselineUpload: () => uploadBaseline(DEMO_DATE, "dinner", jpegBlob()),
    postUpload: () => upload("NS03"),
    staffZero: () => recordStaffZero(mealOrderId("NS03", DEMO_DATE, "lunch"), "refused"),
  } satisfies Record<keyof typeof errorHandlers, () => Promise<unknown>>;

  const kinds: [Exclude<ApiErrorKind, "network">, number][] = [
    ["not_found", 404],
    ["conflict", 409],
    ["too_large", 413],
    ["invalid", 422],
    ["server", 500],
  ];

  for (const name of Object.keys(calls) as (keyof typeof calls)[]) {
    describe(name, () => {
      it.each(kinds)("%s → HTTP %i", async (kind, status) => {
        server.use(errorHandlers[name](kind));

        await expectApiError(calls[name](), kind, status);
      });

      it("network → 네트워크 오류", async () => {
        server.use(errorHandlers[name]("network"));

        await expectApiError(calls[name](), "network", undefined);
      });
    });
  }

  it("오류 핸들러는 resetHandlers 뒤 기본 핸들러로 돌아간다", async () => {
    server.use(errorHandlers.meta("server"));
    server.resetHandlers();

    await expect(getMeta()).resolves.toEqual({ demo_date: DEMO_DATE });
  });
});

describe("모의 상태 초기화", () => {
  it("전량 기록으로 바뀐 상태가 reset 뒤 픽스처 초기값으로 돌아간다", async () => {
    await recordStaffZero(mealOrderId("NS03", DEMO_DATE, "lunch"), "refused");
    expect((await lunchOrder("NS03")).record_status).toBe("recorded");

    mockState.reset();

    expect((await lunchOrder("NS03")).record_status).toBe("not_recorded");
  });
});
