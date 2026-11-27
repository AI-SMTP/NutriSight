/**
 * 모의 API 픽스처: 시연일 세 끼 배식 계획, 환자 10명, 끼니별 발주와 식후·기준 사진의 초기 상태.
 *
 * - 정본: 스펙 3.4절(픽스처 규칙), 계획 T9.1. 필드 이름·상태 값은 `docs/data-model.md`를 따른다.
 * - 값 출처: `data/seed/demo_seed.json`의 D0 배식 계획(메뉴·칸·위치·배식량·열량·단백질),
 *   환자(`room`·`display_name`). 칸 위치는 현재 시드 표기를 그대로 쓴다.
 * - 끼니별 상태 분포(팀 제안안): 아침은 기준 사진 등록·NS03 미기록·나머지 완료, 점심은 기준 사진 등록·
 *   미기록·처리 중·완료·재촬영 필요·완료(전량 거부)가 섞임, 저녁은 기준 사진 없음·모두 미기록.
 *   금식 환자(NS01)는 세 끼 모두 `npo`다. 취소(`cancelled`)는 기본값에 두지 않고 테스트가 주입한다.
 */
import { mealPlanId, type Meal, type Slot } from "../api/provisional";
import { breakfastScenario, dinnerScenario, lunchScenario, type MealScenario } from "./scenarios";
import type { MockOrder, MockPatient, MockPhoto, MockPlan, MockState } from "./types";

export type { MockOrder, MockPatient, MockPhoto, MockPlan, MockState } from "./types";

/** 시연일 D (시드 `seed_meta.demo_date`와 같은 값) */
export const DEMO_DATE = "2026-11-27";

/**
 * 세 끼 모두 금식인 환자. 시드 D0에서 금식 발주를 가진 환자(NS01)를 고르되, 시드는 점심만 `npo`이고
 * 아침·저녁은 `ordered`다. 여기서는 스펙 3.4절 "1명은 npo"를 계획 T9.1대로 세 끼 모두에 적용해
 * 시드와 다르게 둔다(어느 끼니를 골라도 금식 배지가 보이도록 한 팀 제안안).
 */
export const NPO_PATIENT_ID = "NS01";

/** 발주 ID (data-model.md 4절 예: `NS07_2026-11-23_lunch`) */
export function mealOrderId(patientId: string, date: string, meal: Meal): string {
  return `${patientId}_${date}_${meal}`;
}

function patient(patient_id: string, room: string): MockPatient {
  return { patient_id, display_name: patient_id, room };
}

/** 환자 10명. `display_name`·`room`은 시드 값 */
const PATIENTS: readonly MockPatient[] = [
  patient("NS01", "301호"),
  patient("NS02", "301호"),
  patient("NS03", "302호"),
  patient("NS04", "302호"),
  patient("NS05", "303호"),
  patient("NS06", "303호"),
  patient("NS07", "304호"),
  patient("NS08", "304호"),
  patient("NS09", "305호"),
  patient("NS10", "305호"),
];

/** 칸 배치 (data-model.md 3절, 시드 표기). 순서가 곧 `slot_1`~`slot_6`이다 */
const SLOT_LAYOUT: readonly Pick<Slot, "position" | "dish_type">[] = [
  { position: "아랫줄 왼쪽", dish_type: "rice" },
  { position: "아랫줄 오른쪽", dish_type: "soup" },
  { position: "윗줄 1 (왼쪽 끝)", dish_type: "main" },
  { position: "윗줄 2", dish_type: "side" },
  { position: "윗줄 3", dish_type: "side" },
  { position: "윗줄 4 (오른쪽 끝)", dish_type: "kimchi" },
];

/** 칸별 [메뉴, 배식량 g, 열량 kcal, 단백질 g] (시드 D0) */
type SlotValues = readonly [string, number, number, number];

const D0_MENUS: Readonly<Record<Meal, readonly SlotValues[]>> = {
  breakfast: [
    ["쌀밥", 210, 300, 5],
    ["어묵국", 250, 60, 4],
    ["달걀야채찜", 90, 200, 17],
    ["시금치나물", 60, 90, 3],
    ["마늘종볶음", 50, 40, 1],
    ["열무김치", 40, 8, 0.7],
  ],
  lunch: [
    ["잡곡밥", 210, 320, 6],
    ["근대된장국", 250, 40, 2.5],
    ["소불고기", 90, 250, 25],
    ["애호박볶음", 60, 80, 2],
    ["어묵볶음", 50, 75, 4],
    ["배추김치", 40, 8, 0.6],
  ],
  dinner: [
    ["쌀밥", 210, 300, 5],
    ["맑은두부국", 250, 50, 4],
    ["동태조림", 90, 220, 23],
    ["무나물", 60, 80, 2],
    ["콩자반", 50, 70, 4.5],
    ["배추김치", 40, 8, 0.6],
  ],
};

const MEALS: readonly Meal[] = ["breakfast", "lunch", "dinner"];

const SCENARIOS: Readonly<Record<Meal, MealScenario>> = {
  breakfast: breakfastScenario,
  lunch: lunchScenario,
  dinner: dinnerScenario,
};

function buildSlots(meal: Meal): Slot[] {
  return D0_MENUS[meal].map(([menu_name, served_g, energy_kcal, protein_g], index) => ({
    slot_id: `slot_${index + 1}`,
    ...SLOT_LAYOUT[index]!,
    menu_name,
    served_g,
    energy_kcal,
    protein_g,
  }));
}

/** 한 끼의 배식 계획·발주·사진을 시나리오대로 만든다 */
function buildMeal(meal: Meal): { plan: MockPlan; orders: MockOrder[]; photos: MockPhoto[] } {
  const planId = mealPlanId(DEMO_DATE, meal);
  const scenario = SCENARIOS[meal];
  const baseline = scenario.baseline;
  const entries = PATIENTS.map((p) => ({
    patientId: p.patient_id,
    id: mealOrderId(p.patient_id, DEMO_DATE, meal),
    entry: scenario.orders[p.patient_id] ?? {},
  }));
  const orders = entries.map(({ patientId, id, entry }): MockOrder => ({
    meal_order_id: id,
    patient_id: patientId,
    meal_plan_id: planId,
    order_status: patientId === NPO_PATIENT_ID ? "npo" : "ordered",
    record_status: entry.record_status ?? "not_recorded",
    staff_zero_reason: entry.staff_zero_reason ?? null,
    post_photo_id: entry.photo?.photo_id ?? null,
  }));
  const postPhotos = entries.flatMap(({ id, entry }): MockPhoto[] =>
    entry.photo ? [{ ...entry.photo, kind: "post", meal_plan_id: planId, meal_order_id: id }] : [],
  );
  const baselinePhotos: MockPhoto[] = baseline
    ? [{ ...baseline, kind: "baseline", meal_plan_id: planId, meal_order_id: null }]
    : [];
  const plan: MockPlan = {
    meal_plan_id: planId,
    date: DEMO_DATE,
    meal,
    slots: buildSlots(meal),
    baseline_photo_id: baseline?.photo_id ?? null,
  };
  return { plan, orders, photos: [...baselinePhotos, ...postPhotos] };
}

/** 발주 덮어쓰기. `null`이면 그 발주를 뺀다(예: "발주 없음" 409 사례) */
export type OrderOverride = Partial<Omit<MockOrder, "meal_order_id">> | null;

/** 사진 덮어쓰기(ID·종류·끼니·발주 연결은 바꾸지 않는다) */
export type PhotoOverride = Partial<Pick<MockPhoto, "status" | "stage" | "uploaded_at">>;

/** 배식 계획 덮어쓰기(기준 사진 유무) */
export type PlanOverride = Partial<Pick<MockPlan, "baseline_photo_id">>;

/** 테스트가 픽스처 초기값 위에 주입하는 값 */
export interface StateOverrides {
  orders?: Readonly<Record<string, OrderOverride>>;
  photos?: Readonly<Record<string, PhotoOverride>>;
  plans?: Readonly<Record<string, PlanOverride>>;
}

/** 덮어쓰기 키가 모두 픽스처에 있는지 확인한다. 오타를 조용히 넘기지 않도록 던진다 */
function assertKnownIds(label: string, ids: Iterable<string>, overrides: object): void {
  const known = new Set(ids);
  const unknown = Object.keys(overrides).filter((id) => !known.has(id));
  if (unknown.length > 0) {
    throw new Error(`픽스처에 없는 ${label} ID: ${unknown.join(", ")}`);
  }
}

function applyOrderOverrides(
  orders: readonly MockOrder[],
  overrides: Readonly<Record<string, OrderOverride>>,
): MockOrder[] {
  assertKnownIds(
    "발주",
    orders.map((o) => o.meal_order_id),
    overrides,
  );
  return orders.flatMap((order) => {
    if (!Object.hasOwn(overrides, order.meal_order_id)) return [order];
    const override = overrides[order.meal_order_id];
    return override === null ? [] : [{ ...order, ...override }];
  });
}

/** ID별 부분 덮어쓰기(사진·계획 공용). 없는 ID는 던진다 */
function applyPatches<T extends object>(
  label: string,
  items: readonly T[],
  idOf: (item: T) => string,
  patches: Readonly<Record<string, NoInfer<Partial<T>>>>,
): T[] {
  assertKnownIds(label, items.map(idOf), patches);
  return items.map((item) =>
    Object.hasOwn(patches, idOf(item)) ? { ...item, ...patches[idOf(item)] } : item,
  );
}

/** 픽스처 초기 상태를 매번 새 객체로 만든다 */
export function createInitialState(options: { overrides?: StateOverrides } = {}): MockState {
  const meals = MEALS.map(buildMeal);
  const overrides = options.overrides ?? {};
  return {
    demoDate: DEMO_DATE,
    patients: PATIENTS,
    plans: applyPatches(
      "배식 계획",
      meals.map((m) => m.plan),
      (p) => p.meal_plan_id,
      overrides.plans ?? {},
    ),
    orders: applyOrderOverrides(
      meals.flatMap((m) => m.orders),
      overrides.orders ?? {},
    ),
    photos: applyPatches(
      "사진",
      meals.flatMap((m) => m.photos),
      (p) => p.photo_id,
      overrides.photos ?? {},
    ),
    nextPhotoSeq: 1,
  };
}
