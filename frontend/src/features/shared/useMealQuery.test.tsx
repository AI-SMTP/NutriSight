// 끼니 조회 훅 테스트(스펙 3.5절 조회 순서 규칙·404·(가)·(나)·제출 성공 뒤 재조회 실패, 3.4절 SSE 재조회).
// 조회 응답 시점은 heldRequests 도우미로 테스트가 정하고, 요청 수는 MSW 요청 기록으로 센다.
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { StrictMode, type ReactNode } from "react";

import { SystemEventsProvider } from "../../api/events";
import {
  mealPlanId,
  uploadBaseline,
  type Meal,
  type MealDetail,
  type PhotoStatusChangedEvent,
} from "../../api/provisional";
import { errorHandlers } from "../../mocks/errorHandlers";
import { eventBus } from "../../mocks/eventBus";
import { DEMO_DATE } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { jpegBlob } from "../../test/apiError";
import { deferred } from "../../test/deferred";
import { holdMealRequests, recordApiRequests } from "../../test/heldRequests";
import { createMockConnect } from "../../test/mockConnect";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import { useMealQuery, type MealQueryOptions } from "./useMealQuery";
import { useSubmission } from "./useSubmission";

const NOTICE = "기준 사진 등록됨";

function mealPath(meal: Meal, date = DEMO_DATE): string {
  return `/api/meals/${date}/${meal}`;
}

/** 같은 끼니의 사진 이벤트 */
function photoEvent(meal: Meal): PhotoStatusChangedEvent {
  return {
    photo_id: "mock_photo_99",
    kind: "post",
    patient_id: "NS03",
    meal_plan_id: mealPlanId(DEMO_DATE, meal),
    meal_order_id: `NS03_${DEMO_DATE}_${meal}`,
    status: "queued",
    stage: null,
    at: "2026-11-27T12:00:00.000Z",
  };
}

/** 화면 하나처럼 조회 훅과 제출 훅을 함께 쓴다 */
function useScreen(options: MealQueryOptions) {
  return { query: useMealQuery(options), submission: useSubmission() };
}

function setup(initialProps: MealQueryOptions = { date: DEMO_DATE, meal: "lunch" }) {
  const mock = createMockConnect();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <SystemEventsProvider connect={mock.connect}>{children}</SystemEventsProvider>
  );
  const hook = renderHook((props: MealQueryOptions) => useScreen(props), { initialProps, wrapper });
  return { ...hook, mock };
}

type Hook = ReturnType<typeof setup>["result"];

/** 데이터가 들어올 때까지 기다린다 */
async function waitReady(result: Hook, meal: Meal) {
  await waitFor(() => expect(result.current.query.view).toBe("ready"));
  expect(result.current.query.data?.meal).toBe(meal);
}

/** 지금 보여 주는 데이터. 없으면 테스트를 멈춘다 */
function currentData(result: Hook): MealDetail {
  const data = result.current.query.data;
  if (data === null) throw new Error("데이터가 있어야 한다");
  return data;
}

/** 제출이 성공하면 잠금·성공 안내를 남기고 재조회한다(화면 ①의 흐름) */
async function submitBaseline(result: Hook, meal: Meal) {
  const key = mealPlanId(DEMO_DATE, meal);
  await act(async () => {
    result.current.submission.submit(
      { date: DEMO_DATE, meal, blob: jpegBlob() },
      (request) => uploadBaseline(request.date, request.meal, request.blob),
      {
        onSuccess: () => {
          result.current.query.markSubmitted(key, NOTICE);
          result.current.query.refetch();
        },
      },
    );
  });
  await waitFor(() => expect(result.current.submission.busy).toBe(false));
  return key;
}

/** 지금까지 쌓인 마이크로태스크와 MSW 응답 처리를 흘려보낸다 */
async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
}

describe("useMealQuery 조회와 분류", () => {
  it("시연일이 준비되지 않은 동안(enabled=false·date=null)은 open이 와도 조회 0건, 준비되면 1건", async () => {
    const { requests } = recordApiRequests();
    const { result, rerender, mock } = setup({ date: null, meal: "lunch" });

    act(() => mock.open());
    await flush();
    expect(requests).toEqual([]);
    expect(result.current.query.view).toBe("loading");

    rerender({ date: DEMO_DATE, meal: "lunch", enabled: false });
    act(() => result.current.query.refetch());
    await flush();
    expect(requests).toEqual([]);

    rerender({ date: DEMO_DATE, meal: "lunch" });
    await waitReady(result, "lunch");
    expect(requests).toEqual([`GET ${mealPath("lunch")}`]);
    expect(result.current.query.data?.meal_plan_id).toBe(mealPlanId(DEMO_DATE, "lunch"));
  });

  it("404면 no_plan이고 데이터가 없다", async () => {
    server.use(errorHandlers.meal("not_found"));
    const { result } = setup();

    await waitFor(() => expect(result.current.query.view).toBe("no_plan"));
    expect(result.current.query.data).toBeNull();
    expect(result.current.query.refreshError).toBe(false);
  });

  it.each([["network"], ["server"]] as const)(
    "보여 줄 데이터가 없을 때 %s 실패면 unreachable(가)",
    async (kind) => {
      server.use(errorHandlers.meal(kind));
      const { result } = setup();

      await waitFor(() => expect(result.current.query.view).toBe("unreachable"));
      expect(result.current.query.data).toBeNull();
      expect(result.current.query.refreshError).toBe(false);
    },
  );

  it("데이터가 있는데 재조회가 실패하면 데이터를 두고 refreshError(나), 다시 성공하면 풀린다", async () => {
    const { result } = setup();
    await waitReady(result, "lunch");
    const before = result.current.query.data;

    server.use(errorHandlers.meal("network"));
    act(() => result.current.query.refetch());
    await waitFor(() => expect(result.current.query.refreshError).toBe(true));
    expect(result.current.query.view).toBe("ready");
    expect(result.current.query.data).toBe(before);

    server.resetHandlers();
    act(() => result.current.query.refetch());
    await waitFor(() => expect(result.current.query.refreshError).toBe(false));
    expect(result.current.query.view).toBe("ready");
  });

  it("데이터가 있는데 재조회가 404면 no_plan이 된다", async () => {
    const { result } = setup();
    await waitReady(result, "lunch");

    server.use(errorHandlers.meal("not_found"));
    act(() => result.current.query.refetch());
    await waitFor(() => expect(result.current.query.view).toBe("no_plan"));
    expect(result.current.query.data).toBeNull();
  });

  it("날짜·끼니를 바꾸면 이전 데이터를 바로 지우고 새 조회 성공 전까지 ready가 아니다", async () => {
    const { result, rerender } = setup();
    await waitReady(result, "lunch");

    const { held } = holdMealRequests();
    rerender({ date: DEMO_DATE, meal: "dinner" });
    expect(result.current.query.view).toBe("loading");
    expect(result.current.query.data).toBeNull();

    await waitFor(() => expect(held).toHaveLength(1));
    // 아침으로 갔다가 점심으로 돌아와도 예전 점심 데이터를 다시 보여 주지 않는다
    rerender({ date: DEMO_DATE, meal: "lunch" });
    expect(result.current.query.view).toBe("loading");
    expect(result.current.query.data).toBeNull();

    await waitFor(() => expect(held).toHaveLength(2));
    // 전환 전 저녁 조회가 먼저 도착해도 점심 화면에는 반영되지 않는다
    act(() => held[0]?.pass());
    await flush();
    expect(result.current.query.view).toBe("loading");
    expect(result.current.query.data).toBeNull();

    act(() => held[1]?.pass());
    await waitReady(result, "lunch");
  });
});

describe("useMealQuery 조회 순서 규칙", () => {
  it.each([
    ["성공", (stale: MealDetail) => ({ type: "respond", stale }) as const],
    ["실패", () => ({ type: "fail" }) as const],
  ])("늦게 도착한 앞선 응답(%s)은 무시한다", async (_label, makeLate) => {
    const { result } = setup();
    await waitReady(result, "lunch");
    const fresh = currentData(result);

    const { held } = holdMealRequests();
    act(() => result.current.query.refetch());
    act(() => result.current.query.refetch());
    await waitFor(() => expect(held).toHaveLength(2));

    act(() => held[1]?.pass());
    await waitFor(() => expect(result.current.query.data).not.toBe(fresh));
    const latest = result.current.query.data;

    const late = makeLate({ ...fresh, baseline_photo: null });
    act(() => {
      if (late.type === "respond") held[0]?.respond(late.stale);
      else held[0]?.fail("network");
    });
    await flush();

    expect(result.current.query.data).toBe(latest);
    expect(result.current.query.data?.baseline_photo).not.toBeNull();
    expect(result.current.query.refreshError).toBe(false);
  });

  it("최신 요청이 대기 중이면 이전에 반영한 상태를 그대로 둔다", async () => {
    const { result } = setup();
    await waitReady(result, "lunch");
    const before = result.current.query.data;

    const { held } = holdMealRequests();
    act(() => result.current.query.refetch());
    await waitFor(() => expect(held).toHaveLength(1));

    expect(result.current.query.view).toBe("ready");
    expect(result.current.query.data).toBe(before);
  });

  it("끼니 전환 뒤 응답 전에 새 끼니 이벤트가 오면 재조회가 최신을 반영하고 늦은 응답은 버린다", async () => {
    const { result, rerender, mock } = setup();
    await waitReady(result, "lunch");
    // 첫 open의 재조회가 끝난 뒤부터 조회를 붙잡는다
    act(() => mock.open());
    await flush();

    const { held } = holdMealRequests();
    rerender({ date: DEMO_DATE, meal: "dinner" });
    await waitFor(() => expect(held).toHaveLength(1));

    act(() => eventBus.publish(photoEvent("dinner")));
    await waitFor(() => expect(held).toHaveLength(2));
    expect(held.map((h) => h.path)).toEqual([mealPath("dinner"), mealPath("dinner")]);

    act(() => held[1]?.pass());
    await waitReady(result, "dinner");
    const latest = currentData(result);

    // 전환 직후 보낸 조회가 이제야 (다른 내용으로) 도착한다
    act(() => held[0]?.respond({ ...latest, orders: [] }));
    await flush();
    expect(result.current.query.data).toBe(latest);
  });

  it("open마다 재조회하고, 같은 끼니 이벤트는 재조회, 다른 끼니 이벤트는 무시한다", async () => {
    const { result, mock } = setup();
    await waitReady(result, "lunch");
    const { requests } = recordApiRequests();

    act(() => mock.open());
    await waitFor(() => expect(requests).toHaveLength(1));

    act(() => eventBus.publish(photoEvent("dinner")));
    act(() => eventBus.publish(photoEvent("breakfast")));
    await flush();
    expect(requests).toHaveLength(1);

    act(() => eventBus.publish(photoEvent("lunch")));
    await waitFor(() => expect(requests).toHaveLength(2));

    act(() => mock.open());
    await waitFor(() => expect(requests).toHaveLength(3));
    expect(new Set(requests)).toEqual(new Set([`GET ${mealPath("lunch")}`]));
  });

  it("언마운트하면 진행 중인 조회를 취소하고 상태를 바꾸지 않으며 경고가 없다", async () => {
    const consoleError = vi.spyOn(console, "error");
    const { held } = holdMealRequests();
    const { result, unmount } = setup();
    await waitFor(() => expect(held).toHaveLength(1));
    expect(held[0]?.signal.aborted).toBe(false);

    unmount();
    expect(held[0]?.signal.aborted).toBe(true);
    act(() => held[0]?.pass());
    await flush();

    expect(result.current.query.view).toBe("loading");
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("StrictMode(이펙트 두 번 실행)에서도 첫 조회가 반영되고, 버려진 첫 조회는 취소된다", async () => {
    const { held } = holdMealRequests();
    const mock = createMockConnect();
    const wrapper = ({ children }: { children: ReactNode }) => (
      <StrictMode>
        <SystemEventsProvider connect={mock.connect}>{children}</SystemEventsProvider>
      </StrictMode>
    );
    const { result } = renderHook(() => useMealQuery({ date: DEMO_DATE, meal: "lunch" }), {
      wrapper,
    });
    await waitFor(() => expect(held.length).toBeGreaterThan(0));
    await flush();
    // 첫 이펙트의 조회는 정리 때 취소된다(보통 MSW 핸들러에 닿기 전에 끝나 기록되지 않는다).
    // 핸들러에 닿은 요청이 있다면 마지막 것만 살아 있어야 한다.
    const live = held.filter((h) => !h.signal.aborted);
    expect(live).toHaveLength(1);
    expect(live[0]).toBe(held.at(-1));

    act(() => {
      for (const request of held) request.pass();
    });
    await waitFor(() => expect(result.current.view).toBe("ready"));
    expect(result.current.data?.meal).toBe("lunch");
  });
});

describe("useMealQuery 로컬 제출 완료 잠금과 성공 안내", () => {
  useNodeFileForMultipart();

  it("제출 전에 보낸 조회가 제출 뒤 늦게 성공하고 제출 뒤 조회는 실패하면 잠금 유지, 데이터는 되돌아가지 않는다", async () => {
    const { result } = setup({ date: DEMO_DATE, meal: "dinner" });
    await waitReady(result, "dinner");
    const before = currentData(result);

    const { held } = holdMealRequests();
    act(() => result.current.query.refetch()); // 제출 전 조회
    await waitFor(() => expect(held).toHaveLength(1));

    const key = await submitBaseline(result, "dinner");
    await waitFor(() => expect(held).toHaveLength(2)); // 제출 뒤 조회
    expect(result.current.query.isLocked(key)).toBe(true);

    act(() => held[0]?.respond({ ...before, slots: [] }));
    await flush();
    expect(result.current.query.data).toBe(before);

    act(() => held[1]?.fail("network"));
    await waitFor(() => expect(result.current.query.refreshError).toBe(true));
    expect(result.current.query.data).toBe(before);
    expect(result.current.query.isLocked(key)).toBe(true);
    expect(result.current.query.submitNotice).toBe(NOTICE);
  });

  it("제출 전 순번의 조회는 최신으로 반영돼도 잠금을 지우지 못한다", async () => {
    const { result } = setup({ date: DEMO_DATE, meal: "dinner" });
    await waitReady(result, "dinner");
    const before = currentData(result);

    const { held } = holdMealRequests();
    act(() => result.current.query.refetch()); // 제출 전 조회(아직 최신)
    await waitFor(() => expect(held).toHaveLength(1));
    const key = mealPlanId(DEMO_DATE, "dinner");
    act(() => result.current.query.markSubmitted(key, NOTICE));

    act(() => held[0]?.respond({ ...before, orders: [] }));
    await waitFor(() => expect(result.current.query.data?.orders).toHaveLength(0));
    expect(result.current.query.isLocked(key)).toBe(true);

    act(() => result.current.query.refetch()); // 제출 뒤 조회
    await waitFor(() => expect(held).toHaveLength(2));
    act(() => held[1]?.pass());
    await waitFor(() => expect(result.current.query.isLocked(key)).toBe(false));
  });

  it("데이터가 있을 때 제출 성공 뒤 재조회 실패 → refreshError, 안내·잠금 유지, 다시 시도는 GET 1건·POST 0건", async () => {
    const { result } = setup({ date: DEMO_DATE, meal: "dinner" });
    await waitReady(result, "dinner");

    server.use(errorHandlers.meal("network"));
    const key = await submitBaseline(result, "dinner");
    await waitFor(() => expect(result.current.query.refreshError).toBe(true));
    expect(result.current.query.view).toBe("ready");
    expect(result.current.query.submitNotice).toBe(NOTICE);
    expect(result.current.query.isLocked(key)).toBe(true);

    // 다시 시도가 또 실패하면 잠금 유지
    const failed = recordApiRequests();
    act(() => result.current.query.refetch());
    await waitFor(() => expect(failed.requests).toHaveLength(1));
    await flush();
    expect(failed.requests).toEqual([`GET ${mealPath("dinner")}`]);
    expect(result.current.query.refreshError).toBe(true);
    expect(result.current.query.isLocked(key)).toBe(true);

    // 다시 시도가 성공하면 잠금이 풀리고 안내는 그대로다
    server.resetHandlers();
    const retried = recordApiRequests();
    act(() => result.current.query.refetch());
    await waitFor(() => expect(result.current.query.isLocked(key)).toBe(false));
    expect(retried.requests).toEqual([`GET ${mealPath("dinner")}`]);
    expect(result.current.query.refreshError).toBe(false);
    expect(result.current.query.data?.baseline_photo).not.toBeNull();
    expect(result.current.query.submitNotice).toBe(NOTICE);
  });

  it("데이터가 없을 때(끼니를 바꿨다 돌아온 조회 실패) → unreachable, 안내·잠금 유지, 다시 시도는 GET 1건·POST 0건", async () => {
    const { result, rerender } = setup({ date: DEMO_DATE, meal: "dinner" });
    await waitReady(result, "dinner");

    // 저녁 조회만 실패시킨다: 제출 뒤 재조회 실패 → 점심으로 갔다가 → 저녁으로 돌아온 조회도 실패
    server.use(http.get(mealPath("dinner"), () => HttpResponse.error()));
    const key = await submitBaseline(result, "dinner");
    await waitFor(() => expect(result.current.query.refreshError).toBe(true));

    rerender({ date: DEMO_DATE, meal: "lunch" });
    await waitReady(result, "lunch");
    rerender({ date: DEMO_DATE, meal: "dinner" });
    await waitFor(() => expect(result.current.query.view).toBe("unreachable"));
    expect(result.current.query.data).toBeNull();
    expect(result.current.query.refreshError).toBe(false);
    expect(result.current.query.submitNotice).toBe(NOTICE);
    expect(result.current.query.isLocked(key)).toBe(true);

    const failed = recordApiRequests();
    act(() => result.current.query.refetch());
    await waitFor(() => expect(failed.requests).toHaveLength(1));
    await flush();
    expect(failed.requests).toEqual([`GET ${mealPath("dinner")}`]);
    expect(result.current.query.view).toBe("unreachable");
    expect(result.current.query.isLocked(key)).toBe(true);

    server.resetHandlers();
    const retried = recordApiRequests();
    act(() => result.current.query.refetch());
    await waitReady(result, "dinner");
    expect(retried.requests).toEqual([`GET ${mealPath("dinner")}`]);
    expect(result.current.query.isLocked(key)).toBe(false);
    expect(result.current.query.submitNotice).toBe(NOTICE);
  });

  it("제출 중에 선택을 바꾼 뒤 성공 콜백이 제출 시점의 refetch를 불러도 현재 끼니 조회가 loading에 멈추지 않는다", async () => {
    const { result, rerender } = setup({ date: DEMO_DATE, meal: "dinner" });
    await waitReady(result, "dinner");

    // 제출 시점의 함수를 잡아 두고, 성공 콜백은 result.current를 다시 읽지 않는다
    const { refetch, markSubmitted } = result.current.query;
    const { submit } = result.current.submission;
    const upload = deferred<void>();
    act(() => {
      submit({ meal: "dinner" }, () => upload.promise, {
        onSuccess: () => {
          markSubmitted(mealPlanId(DEMO_DATE, "dinner"), NOTICE);
          refetch();
        },
      });
    });

    const { held } = holdMealRequests();
    rerender({ date: DEMO_DATE, meal: "lunch" });
    await waitFor(() => expect(held).toHaveLength(1));

    await act(async () => upload.resolve());
    await waitFor(() => expect(held).toHaveLength(2));
    expect(held[1]?.path).toBe(mealPath("lunch"));

    act(() => held[0]?.pass());
    act(() => held[1]?.pass());
    await waitReady(result, "lunch");
    expect(result.current.query.submitNotice).toBe(NOTICE);
  });

  it("clearSubmitNotice()로 성공 안내를 지운다", async () => {
    const { result } = setup();
    await waitReady(result, "lunch");

    act(() => result.current.query.markSubmitted("NS03_2026-11-27_lunch", "업로드했습니다"));
    expect(result.current.query.submitNotice).toBe("업로드했습니다");
    act(() => result.current.query.clearSubmitNotice());
    expect(result.current.query.submitNotice).toBeNull();
  });

  it("잠금은 대상 키별이다(같은 끼니의 다른 발주는 잠그지 않는다)", async () => {
    const { result } = setup();
    await waitReady(result, "lunch");

    act(() => result.current.query.markSubmitted("NS03_2026-11-27_lunch", "업로드했습니다"));
    expect(result.current.query.isLocked("NS03_2026-11-27_lunch")).toBe(true);
    expect(result.current.query.isLocked("NS04_2026-11-27_lunch")).toBe(false);
  });
});
