// 임시 계약(provisional.ts) 테스트. 공용 MSW 서버에 테스트마다 핸들러를 얹는다(얹은 핸들러가 기본 모의
// 핸들러보다 먼저 응답하므로 기본 핸들러 유무와 무관하게 돈다).
import { delay, http, HttpResponse, type HttpResponseResolver } from "msw";

import { orderBadge, type OrderStatusInput } from "../lib/mealStatus";
import { server } from "../mocks/server";
import { expectApiError, jpegBlob } from "../test/apiError";
import { useNodeFileForMultipart } from "../test/nodeFile";
import {
  ApiError,
  getMeal,
  getMeta,
  mealPlanId,
  recordStaffZero,
  uploadBaseline,
  uploadPostPhoto,
  type ApiErrorKind,
  type Meal,
  type MealDetail,
  type MealOrderSummary,
  type PhotoStatusChangedEvent,
} from "./provisional";

const DATE = "2026-11-27";
/** 스텁 전의 jsdom `File`(화면이 넘기는 원본 파일과 같은 종류) */
const JsdomFile = globalThis.File;

const summary: MealOrderSummary = {
  meal_order_id: "NS03_2026-11-27_lunch",
  patient_id: "NS03",
  display_name: "환자 C",
  room: "301",
  order_status: "ordered",
  record_status: "not_recorded",
  staff_zero_reason: null,
  post_photo: null,
};

const mealDetail: MealDetail = {
  meal_plan_id: "2026-11-27_lunch_general",
  date: DATE,
  meal: "lunch",
  slots: [
    {
      slot_id: "slot_1",
      position: "아랫줄 왼쪽",
      dish_type: "rice",
      menu_name: "쌀밥",
      served_g: 210,
      energy_kcal: 315,
      protein_g: 5.5,
    },
  ],
  baseline_photo: { photo_id: "p_1", uploaded_at: "2026-11-27T11:50:00+09:00" },
  orders: [summary],
};

/** 다섯 함수를 같은 표로 돌리기 위한 엔드포인트 정의 */
interface Endpoint {
  name: string;
  method: "get" | "post";
  path: string;
  call: () => Promise<unknown>;
}

const endpoints: Endpoint[] = [
  { name: "getMeta", method: "get", path: "/api/meta", call: () => getMeta() },
  {
    name: "getMeal",
    method: "get",
    path: "/api/meals/:date/:meal",
    call: () => getMeal(DATE, "lunch"),
  },
  {
    name: "uploadBaseline",
    method: "post",
    path: "/api/meals/:date/:meal/baseline",
    call: () => uploadBaseline(DATE, "dinner", jpegBlob()),
  },
  {
    name: "uploadPostPhoto",
    method: "post",
    path: "/api/photos",
    call: () => uploadPostPhoto({ patientId: "NS03", date: DATE, meal: "lunch", blob: jpegBlob() }),
  },
  {
    name: "recordStaffZero",
    method: "post",
    path: "/api/meal-orders/:id/staff-zero",
    call: () => recordStaffZero("NS03_2026-11-27_lunch", "refused"),
  },
];

function use(endpoint: Endpoint, resolver: HttpResponseResolver): void {
  server.use(http[endpoint.method](endpoint.path, resolver));
}

describe("mealPlanId", () => {
  it("날짜·끼니로 일반식 배식 계획 ID를 만든다", () => {
    expect(mealPlanId("2026-11-27", "lunch")).toBe("2026-11-27_lunch_general");
  });
});

describe("성공 응답", () => {
  it("getMeta가 시연일을 돌려준다", async () => {
    server.use(http.get("/api/meta", () => HttpResponse.json({ demo_date: DATE })));

    await expect(getMeta()).resolves.toEqual({ demo_date: DATE });
  });

  it("getMeal이 경로에 날짜·끼니를 넣어 조회하고 끼니 상세를 돌려준다", async () => {
    let params: Record<string, unknown> = {};
    server.use(
      http.get("/api/meals/:date/:meal", (info) => {
        params = info.params;
        return HttpResponse.json(mealDetail);
      }),
    );

    await expect(getMeal(DATE, "lunch")).resolves.toEqual(mealDetail);
    expect(params).toEqual({ date: DATE, meal: "lunch" });
  });

  it("recordStaffZero가 JSON {reason}을 보내고 200 본문을 돌려준다", async () => {
    let body: unknown;
    let contentType: string | null = null;
    let params: Record<string, unknown> = {};
    const recorded = {
      meal_order_id: summary.meal_order_id,
      record_status: "recorded",
      staff_zero_reason: "not_eaten",
    };
    server.use(
      http.post("/api/meal-orders/:id/staff-zero", async (info) => {
        params = info.params;
        contentType = info.request.headers.get("content-type");
        body = await info.request.json();
        return HttpResponse.json(recorded);
      }),
    );

    await expect(recordStaffZero(summary.meal_order_id, "not_eaten")).resolves.toEqual(recorded);
    expect(params).toEqual({ id: summary.meal_order_id });
    expect(contentType).toContain("application/json");
    expect(body).toEqual({ reason: "not_eaten" });
  });
});

describe("multipart 업로드", () => {
  // jsdom `File`로는 multipart 본문이 깨지므로 이 묶음에서만 Node `File`로 바꿔 둔다(src/test/nodeFile.ts).
  useNodeFileForMultipart();

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /** 받은 파일 항목이 보낸 JPEG 3바이트와 같은지 */
  async function expectSentFile(value: FormDataEntryValue | null | undefined): Promise<void> {
    expect(typeof value).toBe("object");
    const file = value as Blob;
    expect(file.type).toBe("image/jpeg");
    expect(Array.from(new Uint8Array(await file.arrayBuffer()))).toEqual([0xff, 0xd8, 0xff]);
  }

  it("uploadBaseline이 multipart file 필드로 보내고 201 본문을 돌려준다", async () => {
    let form: FormData | undefined;
    let params: Record<string, unknown> = {};
    server.use(
      http.post("/api/meals/:date/:meal/baseline", async (info) => {
        params = info.params;
        form = await info.request.formData();
        return HttpResponse.json({ photo_id: "p_9", uploaded_at: "t" }, { status: 201 });
      }),
    );

    await expect(uploadBaseline(DATE, "dinner", jpegBlob())).resolves.toEqual({
      photo_id: "p_9",
      uploaded_at: "t",
    });
    expect(params).toEqual({ date: DATE, meal: "dinner" });
    expect([...(form?.keys() ?? [])]).toEqual(["file"]);
    await expectSentFile(form?.get("file"));
  });

  it("uploadPostPhoto가 file·patient_id·date·meal 필드로 보내고 202 본문을 돌려준다", async () => {
    let form: FormData | undefined;
    const accepted = { photo_id: "p_10", meal_order_id: summary.meal_order_id, status: "uploaded" };
    server.use(
      http.post("/api/photos", async ({ request }) => {
        form = await request.formData();
        return HttpResponse.json(accepted, { status: 202 });
      }),
    );

    const result = uploadPostPhoto({
      patientId: "NS03",
      date: DATE,
      meal: "lunch",
      blob: jpegBlob(),
    });

    await expect(result).resolves.toEqual(accepted);
    expect([...(form?.keys() ?? [])].sort()).toEqual(["date", "file", "meal", "patient_id"]);
    await expectSentFile(form?.get("file"));
    expect(form?.get("patient_id")).toBe("NS03");
    expect(form?.get("date")).toBe(DATE);
    expect(form?.get("meal")).toBe("lunch");
  });

  // Vitest jsdom 환경은 multipart 변환 중 파일 이름을 "blob"으로 바꾸므로 전송 본문 대신
  // `FormData.append`에 넘긴 이름을 확인한다.
  it.each([
    ["JPEG는 photo.jpg", jpegBlob, "photo.jpg"],
    ["그 밖의 형식은 photo", () => new Blob(["x"], { type: "image/heic" }), "photo"],
  ])("업로드 파일 이름: %s (원래 파일 이름은 보내지 않는다)", async (_label, makeBlob, name) => {
    server.use(
      http.post("/api/meals/:date/:meal/baseline", () =>
        HttpResponse.json({ photo_id: "p_9", uploaded_at: "t" }, { status: 201 }),
      ),
    );
    const append = vi.spyOn(FormData.prototype, "append");
    const blob = makeBlob();
    const named = new JsdomFile([blob], "환자_NS03_원본.heic", { type: blob.type });

    await uploadBaseline(DATE, "dinner", named);

    expect(append).toHaveBeenCalledWith("file", named, name);
  });
});

describe("상태 코드별 오류 분류", () => {
  const statusCases: [number, ApiErrorKind][] = [
    [404, "not_found"],
    [409, "conflict"],
    [413, "too_large"],
    [422, "invalid"],
    [500, "server"],
  ];

  for (const endpoint of endpoints) {
    describe(endpoint.name, () => {
      it.each(statusCases)("HTTP %i → %s", async (status, kind) => {
        use(endpoint, () => HttpResponse.json({ detail: "무시되는 본문" }, { status }));

        await expectApiError(endpoint.call(), kind, status);
      });

      it("네트워크 오류 → network(상태 코드 없음)", async () => {
        use(endpoint, () => HttpResponse.error());

        await expectApiError(endpoint.call(), "network", undefined);
      });
    });
  }

  it("표에 없는 상태 코드(400·503)는 server로 분류하고 상태 코드를 남긴다", async () => {
    server.use(http.get("/api/meta", () => new HttpResponse(null, { status: 400 })));
    await expectApiError(getMeta(), "server", 400);

    server.use(http.get("/api/meta", () => new HttpResponse(null, { status: 503 })));
    await expectApiError(getMeta(), "server", 503);
  });

  it("detail 문구가 달라도 상태 코드로만 분류한다", async () => {
    server.use(
      http.get("/api/meals/:date/:meal", () =>
        HttpResponse.json({ detail: "conflict" }, { status: 404 }),
      ),
    );

    await expectApiError(getMeal(DATE, "lunch"), "not_found", 404);
  });
});

describe("응답 본문 검증", () => {
  it("성공 응답이 JSON이 아니면 server로 던진다", async () => {
    server.use(http.get("/api/meta", () => HttpResponse.text("<html>")));

    await expectApiError(getMeta(), "server", 200);
  });

  it("성공 응답에 계약 필드가 없으면 server로 던진다", async () => {
    server.use(http.get("/api/meta", () => HttpResponse.json({ date: DATE })));

    await expectApiError(getMeta(), "server", 200);
  });

  it.each([
    ["orders가 null", { orders: null }],
    ["slots가 객체", { slots: {} }],
  ])("getMeal 응답의 배열 필드가 배열이 아니면(%s) server로 던진다", async (_label, patch) => {
    server.use(
      http.get("/api/meals/:date/:meal", () => HttpResponse.json({ ...mealDetail, ...patch })),
    );

    await expectApiError(getMeal(DATE, "lunch"), "server", 200);
  });

  it("성공 응답이 객체가 아니면 server로 던진다", async () => {
    server.use(http.get("/api/meta", () => HttpResponse.json(null)));

    await expectApiError(getMeta(), "server", 200);
  });
});

describe("getMeal 취소", () => {
  it("이미 취소된 signal이면 ApiError가 아니라 AbortError를 그대로 던진다", async () => {
    server.use(http.get("/api/meals/:date/:meal", () => HttpResponse.json(mealDetail)));
    const controller = new AbortController();
    controller.abort();

    const error = await getMeal(DATE, "lunch", { signal: controller.signal }).catch(
      (err: unknown) => err,
    );

    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ name: "AbortError" });
  });

  it("응답을 기다리는 중에 취소하면 AbortError를 그대로 던진다", async () => {
    server.use(http.get("/api/meals/:date/:meal", () => delay("infinite")));
    const controller = new AbortController();

    const pending = getMeal(DATE, "lunch", { signal: controller.signal }).catch(
      (err: unknown) => err,
    );
    controller.abort();

    await expect(pending).resolves.toMatchObject({ name: "AbortError" });
  });

  it("본문을 읽는 중에 취소하면 AbortError를 그대로 던진다", async () => {
    // 첫 청크만 보내고 닫지 않는 스트림: 응답 헤더는 도착하지만 JSON 읽기가 끝나지 않는다
    const openBody = new ReadableStream<Uint8Array>({
      start(stream) {
        stream.enqueue(new TextEncoder().encode("{"));
      },
    });
    server.use(
      http.get(
        "/api/meals/:date/:meal",
        () => new HttpResponse(openBody, { headers: { "Content-Type": "application/json" } }),
      ),
    );
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const controller = new AbortController();

    const pending = getMeal(DATE, "lunch", { signal: controller.signal }).catch(
      (err: unknown) => err,
    );
    // `fetch`가 Response로 끝났다 = 헤더가 도착했다. 이 뒤의 취소는 본문 읽기(readBody)에서만 드러난다
    const response = await fetchSpy.mock.results[0]?.value;
    expect(response).toBeInstanceOf(Response);
    controller.abort();

    const error = await pending;
    fetchSpy.mockRestore();
    expect(error).not.toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ name: "AbortError" });
  });

  it("취소되지 않은 signal은 조회를 그대로 진행한다", async () => {
    server.use(http.get("/api/meals/:date/:meal", () => HttpResponse.json(mealDetail)));

    const result = getMeal(DATE, "lunch", { signal: new AbortController().signal });

    await expect(result).resolves.toEqual(mealDetail);
  });
});

describe("경로 조각 검증", () => {
  // `.`·`..`은 URL 정규화로 경로를 위로 올리므로 요청을 보내지 않고 막는다.
  // 요청이 나가면 상태 코드가 붙은 오류나 처리되지 않은 요청 오류로 드러난다.
  it.each([".", ".."])("조각이 %s이면 요청 없이 invalid로 막는다", async (bad) => {
    await expectApiError(getMeal(bad, "lunch"), "invalid", undefined);
    await expectApiError(getMeal(DATE, bad as Meal), "invalid", undefined);
    await expectApiError(uploadBaseline(bad, "dinner", jpegBlob()), "invalid", undefined);
    await expectApiError(recordStaffZero(bad, "refused"), "invalid", undefined);
  });

  it("점이 들어 있어도 . 또는 ..이 아니면 인코딩해 보낸다", async () => {
    let id: unknown;
    server.use(
      http.post("/api/meal-orders/:id/staff-zero", ({ params }) => {
        id = params.id;
        return HttpResponse.json({
          meal_order_id: "a..b",
          record_status: "recorded",
          staff_zero_reason: "refused",
        });
      }),
    );

    await recordStaffZero("a..b", "refused");

    expect(id).toBe("a..b");
  });
});

describe("ApiError", () => {
  it("Error를 상속하고 kind·status를 담는다", () => {
    const error = new ApiError("conflict", 409);

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
    expect(error.kind).toBe("conflict");
    expect(error.status).toBe(409);
  });
});

describe("PhotoStatusChangedEvent", () => {
  it("완료 이벤트에 outcome을 담을 수 있고 없어도 된다", () => {
    const done: PhotoStatusChangedEvent = {
      photo_id: "p_81",
      patient_id: "NS07",
      meal_plan_id: "2026-11-27_lunch_general",
      meal_order_id: "NS07_2026-11-27_lunch",
      status: "done",
      stage: "alert",
      outcome: "warning_raised",
      at: "2026-11-27T12:31:05+09:00",
    };
    const withoutOutcome: PhotoStatusChangedEvent = { ...done, outcome: undefined };

    expectTypeOf<NonNullable<PhotoStatusChangedEvent["outcome"]>>().toEqualTypeOf<
      "no_change" | "alert_changed" | "warning_raised"
    >();
    expect(done.outcome).toBe("warning_raised");
    expect(withoutOutcome.outcome).toBeUndefined();
  });
});

describe("타입 호환", () => {
  it("MealOrderSummary를 OrderStatusInput 매개변수에 넘길 수 있다", () => {
    expectTypeOf<MealOrderSummary>().toExtend<OrderStatusInput>();
    // 할당문으로도 확인한다(pnpm typecheck가 검사한다).
    const input: OrderStatusInput = summary;

    expect(orderBadge(input).kind).toBe("not_recorded");
    expect(orderBadge(summary).kind).toBe("not_recorded");
  });
});
