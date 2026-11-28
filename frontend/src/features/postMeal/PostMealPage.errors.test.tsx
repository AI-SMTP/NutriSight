// 화면 ② 오류 테스트(`docs/specs/frontend-shell-upload.md` '끼니 조회 순서 규칙'·'제출과 잠금 규칙', '오류 안내 문구'의
// 409·404 공통 안내, '테스트와 E2E'의 오류 주입).
// 시연일 조회 실패, 끼니 조회 실패, 업로드 오류, 선택 변경, 202 뒤 재조회 실패를 확인한다.
// 제출 중 이탈은 `PostMealPage.leave.test.tsx`에 있다.
import { screen, waitFor } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { http } from "msw";

import type { ApiErrorKind } from "../../api/provisional";
import { errorHandlers, errorResponse } from "../../mocks/errorHandlers";
import { DEMO_DATE, mealOrderId } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { mockState } from "../../mocks/state";
import { holdMealRequests, recordApiRequests } from "../../test/heldRequests";
import {
  PREVIEW,
  flushApiRequest,
  localTime,
  mealGets,
  mealPath,
  pickPhoto,
  postRequests,
  useMealScreenEnv,
} from "../../test/mealScreen";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import {
  POST_MEAL_TEXT,
  badgeOf,
  baselineGuide,
  expectAllPostMealInputsDisabled,
  orderSummary,
  patientItem,
  patientItemCount,
  postMealControls,
  waitForBadge,
  waitForOrders,
  submitNotice,
} from "../../test/postMealScreen";
import { renderRoute } from "../../test/renderRoute";

const NS03_LUNCH = mealOrderId("NS03", DEMO_DATE, "lunch");

/** 점심 화면에서 환자를 고르고 사진을 고른다 */
async function selectAndPick(user: UserEvent, name = "NS03"): Promise<void> {
  renderRoute("/post-meal");
  await waitForOrders();
  await user.click(patientItem(name));
  await pickPhoto(user);
}

describe("화면 ② 시연일 조회 실패", () => {
  useMealScreenEnv(() => localTime(12, 0));

  it.each([
    ["네트워크 오류", "network"],
    ["서버 오류(500)", "server"],
  ] as const)(
    "%s → 안내와 끼니·환자·사진 입력·업로드 차단, 끼니 조회 0건 → 다시 시도 성공 → 환자 목록·현황",
    async (_l, kind) => {
      const user = userEvent.setup();
      server.use(errorHandlers.meta(kind));
      const { requests } = recordApiRequests();
      renderRoute("/post-meal");

      expect(await screen.findByText("시연일을 불러오지 못했습니다")).toBeInTheDocument();
      expectAllPostMealInputsDisabled();
      expect(baselineGuide()).toBeEmptyDOMElement();
      expect(patientItemCount()).toBe(0);
      expect(mealGets(requests)).toEqual([]);

      server.resetHandlers();
      const after = recordApiRequests();
      await user.click(screen.getByRole("button", { name: "다시 시도" }));

      await waitForOrders();
      expect(mealGets(after.requests)).toEqual([`GET ${mealPath("lunch")}`]);
      expect(orderSummary()).toHaveTextContent("완료 4 / 9 · 금식 1");
      expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineReady);
      expect(patientItem("NS03")).toBeEnabled();
      expect(postMealControls().meal("dinner")).toBeEnabled();
    },
  );
});

describe("화면 ② 끼니 조회 실패", () => {
  useMealScreenEnv(() => localTime(12, 0));

  async function injectMealError(
    user: UserEvent,
    timing: "initial" | "switch",
    kind: ApiErrorKind,
  ) {
    if (timing === "initial") {
      server.use(errorHandlers.meal(kind));
      renderRoute("/post-meal");
      return;
    }
    renderRoute("/post-meal");
    await waitForOrders();
    server.use(errorHandlers.meal(kind));
    await user.click(postMealControls().meal("dinner"));
  }

  it.each(["initial", "switch"] as const)(
    "404(%s) → '배식 계획이 없습니다', 끼니는 고를 수 있고 환자·사진 입력·업로드는 막힌다",
    async (timing) => {
      const user = userEvent.setup();
      await injectMealError(user, timing, "not_found");

      expect(await screen.findByText("이 날짜·끼니의 배식 계획이 없습니다")).toBeInTheDocument();
      const controls = postMealControls();
      expect(controls.meal("breakfast")).toBeEnabled();
      expect(controls.album).toBeDisabled();
      expect(controls.submit).toBeDisabled();
      expect(patientItemCount()).toBe(0);
    },
  );

  it.each(["initial", "switch"] as const)(
    "네트워크 오류(%s) → '서버에 연결할 수 없습니다 · 다시 시도', 업로드 차단 → 다시 시도 성공",
    async (timing) => {
      const user = userEvent.setup();
      await injectMealError(user, timing, "network");

      expect(await screen.findByText("서버에 연결할 수 없습니다")).toBeInTheDocument();
      expect(postMealControls().submit).toBeDisabled();
      expect(patientItemCount()).toBe(0);

      server.resetHandlers();
      await user.click(screen.getByRole("button", { name: "다시 시도" }));
      await waitForOrders();
      expect(screen.queryByText("서버에 연결할 수 없습니다")).not.toBeInTheDocument();
    },
  );

  it("끼니를 바꾼 직후 새 조회가 끝나기 전에는 환자 선택·업로드가 막히고, 끝나면 풀린다", async () => {
    const user = userEvent.setup();
    const { held } = holdMealRequests();
    renderRoute("/post-meal");
    await waitFor(() => expect(held).toHaveLength(1));
    held[0]?.pass();
    await waitForOrders();
    await user.click(patientItem("NS03"));
    expect(postMealControls().album).toBeEnabled();

    await user.click(postMealControls().meal("dinner"));

    await waitFor(() => expect(held).toHaveLength(2));
    expect(patientItemCount()).toBe(0);
    expect(postMealControls().album).toBeDisabled();
    expect(postMealControls().submit).toBeDisabled();

    held[1]?.pass();
    await waitForOrders();
    // 끼니를 바꾸면 환자 선택도 지운다
    expect(patientItem("NS03")).toHaveAttribute("aria-pressed", "false");
    expect(postMealControls().submit).toHaveAccessibleName("식후 사진 업로드");
  });
});

describe("화면 ② 업로드 오류", () => {
  useNodeFileForMultipart();
  useMealScreenEnv(() => localTime(12, 0));

  it.each([
    ["404", "not_found", "대상을 찾을 수 없습니다. 목록을 새로 고칩니다", true],
    ["409", "conflict", POST_MEAL_TEXT.conflict, true],
    ["413", "too_large", "사진이 너무 큽니다", false],
    ["422", "invalid", "사진을 확인할 수 없습니다. 다른 사진을 골라 주세요", false],
    ["네트워크 오류", "network", "서버에 연결할 수 없습니다. 다시 시도해 주세요", false],
    ["500", "server", "식후 사진을 올리지 못했습니다. 다시 시도해 주세요", false],
  ] as const)("%s → 한국어 안내, 입력 유지", async (_l, kind, message, refetches) => {
    const user = userEvent.setup();
    server.use(errorHandlers.postUpload(kind));
    const { requests } = recordApiRequests();
    await selectAndPick(user);

    await user.click(postMealControls().submit);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("img", PREVIEW)).toBeInTheDocument();
    expect(patientItem("NS03")).toHaveAttribute("aria-pressed", "true");
    expect(postMealControls().submit).toBeEnabled();
    expect(submitNotice()).toBeEmptyDOMElement();
    // 404·409만 그 끼니를 다시 읽는다. 다시 읽지 않는 경우는 요청 하나를 흘려 보낸 뒤에도 1건이어야 한다
    await flushApiRequest();
    await waitFor(() => expect(mealGets(requests)).toHaveLength(refetches ? 2 : 1));
    expect(mealGets(requests)[0]).toBe(`GET ${mealPath("lunch")}`);
  });

  it("목록 갱신 전에 취소로 바뀐 발주 → 서버 409 → 공통 안내와 재조회, 그 환자는 '취소'로 고를 수 없다", async () => {
    const user = userEvent.setup();
    const { requests } = recordApiRequests();
    await selectAndPick(user);
    // 화면이 다시 읽기 전에 모의 상태에서만 취소로 바꾼다(이벤트 없음)
    mockState.update((state) => ({
      ...state,
      orders: state.orders.map((o) =>
        o.meal_order_id === NS03_LUNCH ? { ...o, order_status: "cancelled" } : o,
      ),
    }));
    expect(badgeOf("NS03")).toHaveTextContent("미기록");

    await user.click(postMealControls().submit);

    expect(await screen.findByRole("alert")).toHaveTextContent(POST_MEAL_TEXT.conflict);
    await waitForBadge("NS03", "취소");
    expect(patientItem("NS03")).toBeDisabled();
    expect(postMealControls().submit).toBeDisabled();
    expect(orderSummary()).toHaveTextContent("완료 4 / 8 · 금식 1");
    expect(postRequests(requests)).toEqual(["POST /api/photos"]);
  });

  it("오류가 난 뒤 끼니를 바꾸면 사진·오류를 지우고, 환자를 바꿔도 지운다", async () => {
    const user = userEvent.setup();
    server.use(errorHandlers.postUpload("too_large"));
    await selectAndPick(user);
    await user.click(postMealControls().submit);
    expect(await screen.findByRole("alert")).toHaveTextContent("사진이 너무 큽니다");

    await user.click(patientItem("NS08"));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("img", PREVIEW)).not.toBeInTheDocument();

    await pickPhoto(user);
    await user.click(postMealControls().submit);
    expect(await screen.findByRole("alert")).toHaveTextContent("사진이 너무 큽니다");

    await user.click(postMealControls().meal("dinner"));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("img", PREVIEW)).not.toBeInTheDocument();
  });
});

describe("화면 ② 202 뒤 재조회 실패", () => {
  useNodeFileForMultipart();
  useMealScreenEnv(() => localTime(12, 0));

  it("성공 안내 유지, 그 발주 재제출 불가, 새로 고침 안내 → 다시 시도는 조회만 보낸다", async () => {
    const user = userEvent.setup();
    const meals = { fail: false };
    server.use(
      http.get("/api/meals/:date/:meal", () => (meals.fail ? errorResponse("network") : undefined)),
    );
    const { requests } = recordApiRequests();
    await selectAndPick(user);

    meals.fail = true;
    await user.click(postMealControls().submit);

    expect(await screen.findByText("목록을 새로 고치지 못했습니다")).toBeInTheDocument();
    expect(submitNotice()).toHaveTextContent("NS03 식후 사진을 올렸습니다");
    // 목록은 제출 전 그대로지만 로컬 제출 완료로 잠긴다
    expect(badgeOf("NS03")).toHaveTextContent("미기록");
    expect(screen.getByText(POST_MEAL_TEXT.notRecordable)).toBeInTheDocument();
    expect(postMealControls().album).toBeDisabled();
    expect(postMealControls().submit).toBeDisabled();
    // 다른 환자는 그대로 올릴 수 있다
    await user.click(patientItem("NS08"));
    expect(postMealControls().album).toBeEnabled();
    await user.click(patientItem("NS03"));
    expect(postMealControls().album).toBeDisabled();

    meals.fail = false;
    await user.click(screen.getByRole("button", { name: "다시 시도" }));

    await waitForBadge("NS03", "처리 중");
    expect(postRequests(requests)).toEqual(["POST /api/photos"]);
    expect(screen.queryByText("목록을 새로 고치지 못했습니다")).not.toBeInTheDocument();
    expect(submitNotice()).toHaveTextContent("NS03 식후 사진을 올렸습니다");
  });
});
