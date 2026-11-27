/**
 * 화면 ①②(기준 식전 사진·식후 사진)의 임시 API 계약.
 *
 * - 정본: 스펙 `docs/_local/active/frontend-shell-upload/spec.md` 3.3절 "임시 계약" 표와 그 아래 항목.
 *   필드 이름과 상태 값은 `docs/data-model.md`를 따른다. 이 파일과 스펙이 어긋나면 스펙을 기준으로 고친다.
 * - 화면·훅은 `fetch`를 직접 부르지 않고 이 파일의 함수만 부른다. 오류는 `ApiError.kind`(상태 코드
 *   기반 분류)로만 판단하고 서버 본문의 `detail`에 의존하지 않는다.
 * - T3 연결 시 교체 절차: (1) T3 라우터가 생기면 `pnpm gen:api`로 `generated/schema.d.ts`를 다시 만든다.
 *   (2) 이 파일의 함수 본문을 `client.ts`의 `apiClient`(openapi-fetch) 호출로 바꾼다. 함수 이름·인자·
 *   반환 타입과 `ApiError` 분류는 그대로 둔다. (3) 아래 타입을 생성 타입의 별칭으로 교체한다.
 *   화면 코드는 바꾸지 않는 것을 목표로 한다.
 */

// ── 값 집합 (data-model.md) ──────────────────────────────────────────────

/** 끼니 (`meal_plans.meal`) */
export type Meal = "breakfast" | "lunch" | "dinner";
/** 칸 음식 종류 (`meal_plan_slots.dish_type`) */
export type DishType = "rice" | "soup" | "main" | "side" | "kimchi";
/** 발주 상태 (`meal_orders.order_status`) */
export type OrderStatus = "ordered" | "npo" | "cancelled";
/** 기록 상태 (`meal_orders.record_status`) */
export type RecordStatus = "not_recorded" | "pending" | "recorded" | "not_determinable" | "failed";
/** 전량 기록 사유 (`meal_orders.staff_zero_reason`) */
export type StaffZeroReason = "refused" | "not_eaten";
/** 사진 종류 (`photos.kind`) */
export type PhotoKind = "baseline" | "post";
/** 사진 처리 상태 (`photos.status`) */
export type PhotoStatus =
  "uploaded" | "waiting_baseline" | "queued" | "analyzing" | "done" | "not_determinable" | "failed";
/** 식후 사진 처리 단계 (`photos.stage`) */
export type PhotoStage = "intake" | "nutrition" | "alert" | "recommendation";
/** 식후 사진 처리 결과 (`photos.outcome`). `done`일 때만 남는다 */
export type PhotoOutcome = "no_change" | "alert_changed" | "warning_raised";

// ── 요청·응답 타입 (스펙 3.3절 표) ───────────────────────────────────────

/** 배식 계획 한 칸 (`meal_plan_slots`). 미배식 칸이면 `menu_name = null`, `served_g = 0` */
export interface Slot {
  slot_id: string;
  position: string;
  dish_type: DishType;
  menu_name: string | null;
  served_g: number;
  energy_kcal: number;
  protein_g: number;
}

/** 끼니의 기준 식전 사진. `POST .../baseline` 201 응답 본문과 같다 */
export interface BaselinePhoto {
  photo_id: string;
  uploaded_at: string;
}

/** 화면 ② 환자 목록·업로드 현황용 발주 요약 (제안 확장) */
export interface MealOrderSummary {
  meal_order_id: string;
  patient_id: string;
  display_name: string;
  room: string;
  order_status: OrderStatus;
  record_status: RecordStatus;
  staff_zero_reason: StaffZeroReason | null;
  /** 발주에 현재 연결된 식후 사진 */
  post_photo: { photo_id: string; status: PhotoStatus; stage: PhotoStage | null } | null;
}

/** `GET /api/meals/{date}/{meal}` 200 */
export interface MealDetail {
  meal_plan_id: string;
  date: string;
  meal: Meal;
  slots: Slot[];
  baseline_photo: BaselinePhoto | null;
  orders: MealOrderSummary[];
}

/** `GET /api/meta` 200 (제안 확장) */
export interface MetaResponse {
  /** `YYYY-MM-DD` */
  demo_date: string;
}

/** `POST /api/photos` 202 */
export interface PostPhotoAccepted {
  photo_id: string;
  meal_order_id: string;
  status: PhotoStatus;
}

/** `POST /api/meal-orders/{id}/staff-zero` 200 */
export interface StaffZeroResult {
  meal_order_id: string;
  record_status: "recorded";
  staff_zero_reason: StaffZeroReason;
}

/** SSE 스트림 경로와 이벤트 이름(시스템 구조 8-1절). 모의 SSE 핸들러도 이 값을 쓴다 */
export const EVENTS_PATH = "/api/events";
export const PHOTO_STATUS_CHANGED_EVENT = "photo.status_changed";

/**
 * SSE `photo.status_changed` 이벤트 데이터 (시스템 구조 8-1절).
 * `kind`와 기준 사진 이벤트(환자·발주 `null`)는 제안 확장이라 화면은 `kind`에 의존하지 않는다.
 */
export interface PhotoStatusChangedEvent {
  photo_id: string;
  kind?: PhotoKind;
  patient_id: string | null;
  meal_plan_id: string;
  meal_order_id: string | null;
  status: PhotoStatus;
  stage: PhotoStage | null;
  /** 처리 결과. 완료(`done`) 이벤트에만 온다(시스템 구조 3-2절). 기준 사진은 쓰지 않는다 */
  outcome?: PhotoOutcome | null;
  at: string;
}

// ── 오류 ────────────────────────────────────────────────────────────────

export type ApiErrorKind =
  "not_found" | "conflict" | "too_large" | "invalid" | "network" | "server";

/** 호출 실패. `status`는 서버가 응답했을 때만 있다(`network`에는 없다) */
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;

  constructor(kind: ApiErrorKind, status?: number, options?: ErrorOptions) {
    super(
      status === undefined ? `API 오류: ${kind}` : `API 오류: ${kind} (HTTP ${status})`,
      options,
    );
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

/** 표에 있는 상태 코드. 그 밖의 실패 응답은 모두 `server`다 */
const STATUS_KINDS: ReadonlyMap<number, ApiErrorKind> = new Map([
  [404, "not_found"],
  [409, "conflict"],
  [413, "too_large"],
  [422, "invalid"],
]);

// ── 공용 요청 도우미 ─────────────────────────────────────────────────────

/** 업로드 파일 이름. 사용자 기기의 원래 파일 이름은 보내지 않는다 */
const JPEG_UPLOAD_NAME = "photo.jpg";
const OTHER_UPLOAD_NAME = "photo";

/** 배식 계획 ID (data-model.md 3절 ID 규칙. 파일럿은 일반식 하나) */
export function mealPlanId(date: string, meal: Meal): string {
  return `${date}_${meal}_general`;
}

// `client.ts`와 같은 이유로 현재 출처를 붙인 절대 URL을 쓰고(jsdom `Request`는 상대 URL을 거부한다),
// `fetch`는 호출할 때마다 전역에서 찾는다(MSW가 나중에 바꾼 `fetch`를 쓰기 위해서다).
function apiUrl(path: string): string {
  return `${globalThis.location?.origin ?? ""}${path}`;
}

/** URL 정규화로 경로를 위로 올리는 조각. 인코딩해도 그대로 남으므로 요청 전에 막는다 */
const DOT_SEGMENTS: ReadonlySet<string> = new Set([".", ".."]);

/** 경로 조각 하나를 인코딩한다. `.`·`..`이면 요청을 보내지 않고 `invalid`로 던진다 */
function segment(value: string): string {
  if (DOT_SEGMENTS.has(value)) throw new ApiError("invalid");
  return encodeURIComponent(value);
}

/** 요청을 보내고 실패 응답·네트워크 오류를 `ApiError`로 바꾼다. 취소(abort)는 그대로 다시 던진다 */
async function send(path: string, init: RequestInit = {}): Promise<Response> {
  let response: Response;
  try {
    response = await globalThis.fetch(apiUrl(path), init);
  } catch (err) {
    if (init.signal?.aborted) throw err;
    throw new ApiError("network", undefined, { cause: err });
  }
  if (!response.ok) {
    throw new ApiError(STATUS_KINDS.get(response.status) ?? "server", response.status);
  }
  return response;
}

/** 성공 본문을 JSON으로 읽고 계약 필드가 모두 있는지 확인한다. 어긋나면 `server`다 */
async function readBody<T extends object>(
  response: Response,
  requiredKeys: readonly (keyof T & string)[],
  signal?: AbortSignal | null,
): Promise<T> {
  let body: unknown;
  try {
    body = await response.json();
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new ApiError("server", response.status, { cause: err });
  }
  if (typeof body !== "object" || body === null) {
    throw new ApiError("server", response.status);
  }
  const record: object = body;
  if (!requiredKeys.every((key) => key in record)) {
    throw new ApiError("server", response.status);
  }
  return record as T;
}

/** 끼니 경로 `/api/meals/{date}/{meal}` */
function mealPath(date: string, meal: Meal): string {
  return `/api/meals/${segment(date)}/${segment(meal)}`;
}

function photoForm(blob: Blob): FormData {
  const form = new FormData();
  form.append("file", blob, blob.type === "image/jpeg" ? JPEG_UPLOAD_NAME : OTHER_UPLOAD_NAME);
  return form;
}

// ── 호출 함수 (스펙 3.3절 표) ────────────────────────────────────────────

/** `GET /api/meta` — 시연일 */
export async function getMeta(): Promise<MetaResponse> {
  const response = await send("/api/meta");
  return readBody<MetaResponse>(response, ["demo_date"]);
}

/** `GET /api/meals/{date}/{meal}` — 배식 계획 6칸, 기준 사진, 발주 요약. 404는 배식 계획 없음 */
export async function getMeal(
  date: string,
  meal: Meal,
  options: { signal?: AbortSignal } = {},
): Promise<MealDetail> {
  const { signal } = options;
  const response = await send(mealPath(date, meal), { signal });
  return readBody<MealDetail>(
    response,
    ["meal_plan_id", "date", "meal", "slots", "baseline_photo", "orders"],
    signal,
  );
}

/** `POST /api/meals/{date}/{meal}/baseline` — 기준 식전 사진 등록(201) */
export async function uploadBaseline(date: string, meal: Meal, blob: Blob): Promise<BaselinePhoto> {
  const response = await send(`${mealPath(date, meal)}/baseline`, {
    method: "POST",
    body: photoForm(blob),
  });
  return readBody<BaselinePhoto>(response, ["photo_id", "uploaded_at"]);
}

/** `POST /api/photos` — 식후 사진 업로드(202) */
export async function uploadPostPhoto(args: {
  patientId: string;
  date: string;
  meal: Meal;
  blob: Blob;
}): Promise<PostPhotoAccepted> {
  const form = photoForm(args.blob);
  form.append("patient_id", args.patientId);
  form.append("date", args.date);
  form.append("meal", args.meal);
  const response = await send("/api/photos", { method: "POST", body: form });
  return readBody<PostPhotoAccepted>(response, ["photo_id", "meal_order_id", "status"]);
}

/** `POST /api/meal-orders/{id}/staff-zero` — 사진 없이 전량 거부·미섭취 기록(200) */
export async function recordStaffZero(
  mealOrderId: string,
  reason: StaffZeroReason,
): Promise<StaffZeroResult> {
  const response = await send(`/api/meal-orders/${segment(mealOrderId)}/staff-zero`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return readBody<StaffZeroResult>(response, [
    "meal_order_id",
    "record_status",
    "staff_zero_reason",
  ]);
}
