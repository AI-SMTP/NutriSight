/**
 * 모의 API 기본 REST 핸들러. 브라우저 워커와 Vitest node 서버가 함께 쓴다.
 *
 * - 정본: `docs/specs/frontend-shell-upload.md` '임시 API 계약' 표와 404·409 구분, 'MSW 픽스처'의 모의 규칙,
 *   '제출과 잠금 규칙'의 업로드·전량 기록 임시 규칙.
 * - 상태는 `mockState`(메모리)에 두고, 상태 전이는 `operations.ts`의 순수 함수가 만든다.
 * - 식후 사진·기준 사진 저장이 성공하면 처리 단계 런타임(`runtime.ts`)에 넘긴다. 단계 진행과
 *   `photo.status_changed` 발행, 기준 사진 재처리 규칙은 런타임이 맡는다.
 */
import { http, HttpResponse, type HttpHandler } from "msw";

import type { StaffZeroReason } from "../api/provisional";
import {
  acceptPostPhoto,
  findPlan,
  recordStaffZero,
  registerBaseline,
  toMealDetail,
  type Outcome,
} from "./operations";
import { detailResponse as detail } from "./errorHandlers";
import { currentMockRuntime } from "./runtime";
import { mockState } from "./state";
import type { MockState } from "./types";

export { errorHandlers } from "./errorHandlers";

const STAFF_ZERO_REASONS: ReadonlySet<unknown> = new Set<StaffZeroReason>(["refused", "not_eaten"]);

function isStaffZeroReason(value: unknown): value is StaffZeroReason {
  return STAFF_ZERO_REASONS.has(value);
}

const invalid = () => detail(422, "요청 형식이 올바르지 않습니다");

/**
 * 상태 전이를 적용하고 결과를 응답으로 바꾼다. 실패면 상태를 바꾸지 않는다.
 * `after`는 성공해 상태를 바꾼 뒤 부른다(바뀌기 전 상태를 함께 받는다).
 */
function commit<T extends object>(
  run: (state: MockState) => Outcome<T>,
  successStatus: number,
  after?: (value: T, before: MockState) => void,
): Response {
  const before = mockState.get();
  const outcome = run(before);
  if (!outcome.ok) {
    return detail(
      outcome.status,
      outcome.status === 404 ? "대상을 찾을 수 없습니다" : "지금 기록할 수 없습니다",
    );
  }
  mockState.update(() => outcome.state);
  after?.(outcome.value, before);
  return HttpResponse.json(outcome.value, { status: successStatus });
}

/**
 * multipart 본문을 읽는다. 본문을 multipart로 해석할 수 없으면 `null`(→ 422).
 * `Request.formData()`는 Content-Type이 multipart·urlencoded가 아니거나 본문이 깨졌을 때
 * `TypeError`를 던진다(Fetch 표준). 그 밖의 예외는 핸들러 자체의 결함이므로 422로 숨기지 않고 다시 던진다.
 */
async function readForm(request: Request): Promise<FormData | null> {
  try {
    return await request.formData();
  } catch (err) {
    if (err instanceof TypeError) return null;
    throw err;
  }
}

/** 파일 항목이 있는지. 문자열 필드는 파일이 아니다 */
function hasFile(form: FormData): boolean {
  const file = form.get("file");
  return file !== null && typeof file !== "string";
}

/** 문자열 필드 값. 없거나 파일이면 `null` */
function textField(form: FormData, name: string): string | null {
  const value = form.get(name);
  return typeof value === "string" && value !== "" ? value : null;
}

function now(): string {
  return new Date().toISOString();
}

export const handlers: HttpHandler[] = [
  http.get("/api/meta", () => HttpResponse.json({ demo_date: mockState.get().demoDate })),

  http.get<{ date: string; meal: string }>("/api/meals/:date/:meal", ({ params }) => {
    const state = mockState.get();
    const plan = findPlan(state, params.date, params.meal);
    if (!plan) return detail(404, "배식 계획이 없습니다");
    return HttpResponse.json(toMealDetail(state, plan));
  }),

  http.post<{ date: string; meal: string }>(
    "/api/meals/:date/:meal/baseline",
    async ({ params, request }) => {
      const form = await readForm(request);
      if (!form || !hasFile(form)) return invalid();
      return commit(
        (state) => registerBaseline(state, { date: params.date, meal: params.meal, now: now() }),
        201,
        (value, before) => {
          const previous = findPlan(before, params.date, params.meal)?.baseline_photo_id ?? null;
          currentMockRuntime().baselineRegistered({
            photoId: value.photo_id,
            replaced: previous !== null,
          });
        },
      );
    },
  ),

  http.post("/api/photos", async ({ request }) => {
    const form = await readForm(request);
    if (!form || !hasFile(form)) return invalid();
    const patientId = textField(form, "patient_id");
    const date = textField(form, "date");
    const meal = textField(form, "meal");
    if (!patientId || !date || !meal) return invalid();
    return commit(
      (state) => acceptPostPhoto(state, { patientId, date, meal, now: now() }),
      202,
      (value) => currentMockRuntime().photoAccepted(value.photo_id),
    );
  }),

  http.post<{ id: string }>("/api/meal-orders/:id/staff-zero", async ({ params, request }) => {
    const body: unknown = await request.json().catch(() => null);
    const reason =
      typeof body === "object" && body !== null && "reason" in body ? body.reason : null;
    if (!isStaffZeroReason(reason)) return invalid();
    return commit((state) => recordStaffZero(state, { mealOrderId: params.id, reason }), 200);
  }),
];
