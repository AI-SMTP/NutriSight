// 화면 ② 전량 기록 테스트(`docs/specs/frontend-shell-upload.md` '식후 사진 화면' 6번 "사진 없이 기록", '오류 안내 문구'의
// 409·404 공통 안내, '테스트와 E2E'의 전량 기록 오류 주입과 제출 성공 뒤 재조회 실패).
// 버튼 활성·비활성은 `PostMealPage.staffZeroGuard.test.tsx`, 이탈은 `PostMealPage.leave.test.tsx`에 있다.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { http } from "msw";

import type { StaffZeroReason } from "../../api/provisional";
import { errorHandlers, errorResponse } from "../../mocks/errorHandlers";
import { DEMO_DATE, mealOrderId } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { mockState } from "../../mocks/state";
import { recordApiRequests } from "../../test/heldRequests";
import {
  PREVIEW,
  flushApiRequest,
  localTime,
  mealGets,
  pickPhoto,
  postRequests,
  useMealScreenEnv,
} from "../../test/mealScreen";
import {
  POST_MEAL_TEXT,
  STAFF_ZERO_TEXT,
  badgeOf,
  confirmSheet,
  confirmStaffZero,
  expectStaffZeroDisabled,
  orderSummary,
  patientItem,
  postMealControls,
  staffZeroButton,
  staffZeroGroup,
  submitNotice,
  waitForBadge,
  waitForOrders,
} from "../../test/postMealScreen";
import { createMockConnect } from "../../test/mockConnect";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import { renderRoute } from "../../test/renderRoute";

const NS03_LUNCH = mealOrderId("NS03", DEMO_DATE, "lunch");
/** 식후 사진 업로드의 계약 밖 실패(500) 문구 */
const UPLOAD_FAILED = "식후 사진을 올리지 못했습니다. 다시 시도해 주세요";
const STAFF_ZERO_PATH = `/api/meal-orders/${NS03_LUNCH}/staff-zero`;

/** 점심 화면에서 환자를 고른다 */
async function selectPatient(user: UserEvent, name = "NS03"): Promise<void> {
  renderRoute("/post-meal");
  await waitForOrders();
  await user.click(patientItem(name));
}

/** 전량 기록 버튼을 누르고 확인 시트에서 기록한다 */
async function recordZero(user: UserEvent, reason: StaffZeroReason = "refused"): Promise<void> {
  await user.click(staffZeroButton(reason));
  await confirmStaffZero(user);
}

describe("화면 ② 전량 기록", () => {
  useMealScreenEnv(() => localTime(12, 0));

  it.each([
    ["refused", "전량 거부", "NS03"],
    ["not_eaten", "전량 미섭취", "NS08"],
  ] as const)(
    "%s: 버튼 → 확인 시트 → 기록 → 200 → 재조회 '완료 · %s'",
    async (reason, label, name) => {
      const user = userEvent.setup();
      const bodies: unknown[] = [];
      server.use(
        http.post("/api/meal-orders/:id/staff-zero", async ({ request }) => {
          bodies.push(await request.clone().json());
          return undefined;
        }),
      );
      const { requests } = recordApiRequests();
      await selectPatient(user, name);

      await user.click(staffZeroButton(reason));

      const sheet = confirmSheet();
      expect(sheet).toHaveAccessibleName(STAFF_ZERO_TEXT.sheetTitle);
      expect(sheet).toHaveAccessibleDescription(`${name} 점심을 ${label}로 기록합니다`);
      expect(postRequests(requests)).toEqual([]);

      await confirmStaffZero(user);

      await waitForBadge(name, `완료 · ${label}`);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(bodies).toEqual([{ reason }]);
      const orderId = mealOrderId(name, DEMO_DATE, "lunch");
      expect(postRequests(requests)).toEqual([`POST /api/meal-orders/${orderId}/staff-zero`]);
      // 200 뒤 곧바로 그 끼니를 다시 읽는다(최초 조회 + 재조회)
      expect(mealGets(requests)).toHaveLength(2);
      expect(submitNotice()).toHaveTextContent(`${name} 점심을 ${label}로 기록했습니다`);
      expect(orderSummary()).toHaveTextContent(/^완료 5 \/ 9 · 금식 1$/);
      // 기록된 발주는 다시 기록할 수 없다
      expectStaffZeroDisabled();
    },
  );

  it("확인 시트에서 취소하면 요청하지 않고, 포커스를 누른 버튼으로 돌려준다", async () => {
    const user = userEvent.setup();
    const { requests } = recordApiRequests();
    await selectPatient(user);

    await user.click(staffZeroButton("not_eaten"));
    expect(confirmSheet()).toHaveAccessibleDescription("NS03 점심을 전량 미섭취로 기록합니다");
    await user.click(within(confirmSheet()).getByRole("button", { name: "취소" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(staffZeroButton("not_eaten")).toHaveFocus();
    await flushApiRequest();
    expect(postRequests(requests)).toEqual([]);
    expect(badgeOf("NS03")).toHaveTextContent("미기록");
  });

  it("Escape로 확인 시트를 닫으면 요청하지 않는다", async () => {
    const user = userEvent.setup();
    const { requests } = recordApiRequests();
    await selectPatient(user);

    await user.click(staffZeroButton("refused"));
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await flushApiRequest();
    expect(postRequests(requests)).toEqual([]);
  });

  it("전량 기록 버튼과 확인 시트 버튼은 공용 Button(터치 크기 적용)으로 그린다", async () => {
    const user = userEvent.setup();
    await selectPatient(user);

    // 공용 Button은 data-variant를 단다(Button.module.css의 min-height·min-width var(--touch-min))
    expect(staffZeroButton("refused")).toHaveAttribute("data-variant");
    expect(staffZeroButton("not_eaten")).toHaveAttribute("data-variant");

    await user.click(staffZeroButton("refused"));

    for (const button of within(confirmSheet()).getAllByRole("button")) {
      expect(button).toHaveAttribute("data-variant");
    }
  });

  it("확인 시트가 열린 동안 그 발주가 '처리 중'으로 바뀌면 기록해도 요청하지 않고 닫으며, 포커스는 업로드 영역 제목으로 간다", async () => {
    const user = userEvent.setup();
    const mock = createMockConnect();
    const { requests } = recordApiRequests();
    renderRoute("/post-meal", mock.connect);
    await waitForOrders();
    await user.click(patientItem("NS03"));
    await user.click(staffZeroButton("refused"));

    // 다른 기기가 먼저 올린 것처럼 모의 상태만 바꾸고, SSE open으로 다시 읽게 한다
    mockState.update((state) => ({
      ...state,
      orders: state.orders.map((o) =>
        o.meal_order_id === NS03_LUNCH ? { ...o, record_status: "pending" } : o,
      ),
    }));
    act(() => mock.open());
    await waitForBadge("NS03", "처리 중");
    await confirmStaffZero(user);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // 시트를 연 버튼이 막혔으므로 포커스는 body가 아니라 업로드 영역 제목으로 간다(바로 아래가 막힌 이유 안내)
    expect(screen.getByRole("heading", { name: "사진 올리기" })).toHaveFocus();
    expect(screen.getByText(POST_MEAL_TEXT.notRecordable)).toBeInTheDocument();
    await flushApiRequest();
    expect(postRequests(requests)).toEqual([]);
  });
});

describe("화면 ② 전량 기록 오류", () => {
  useMealScreenEnv(() => localTime(12, 0));

  it.each([
    ["404", "not_found", "대상을 찾을 수 없습니다. 목록을 새로 고칩니다", true],
    ["409", "conflict", POST_MEAL_TEXT.conflict, true],
    ["네트워크 오류", "network", "서버에 연결할 수 없습니다. 다시 시도해 주세요", false],
    ["500", "server", STAFF_ZERO_TEXT.failed, false],
  ] as const)("%s → 한국어 안내, 입력 유지", async (_l, kind, message, refetches) => {
    const user = userEvent.setup();
    server.use(errorHandlers.staffZero(kind));
    const { requests } = recordApiRequests();
    await selectPatient(user);
    await pickPhoto(user);

    await recordZero(user);

    const alerts = await screen.findAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(message);
    // 안내는 "사진 없이 기록" 묶음 안에만 뜬다(업로드 영역에는 없다)
    expect(within(staffZeroGroup()).getByRole("alert")).toBe(alerts[0]);
    // 고른 환자·사진이 남고 다시 시도할 수 있다
    expect(patientItem("NS03")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("img", PREVIEW)).toBeInTheDocument();
    expect(staffZeroButton("refused")).toBeEnabled();
    expect(postMealControls().submit).toBeEnabled();
    expect(submitNotice()).toBeEmptyDOMElement();
    expect(postRequests(requests)).toEqual([`POST ${STAFF_ZERO_PATH}`]);
    // 404·409만 그 끼니를 다시 읽는다
    await flushApiRequest();
    await waitFor(() => expect(mealGets(requests)).toHaveLength(refetches ? 2 : 1));
  });

  it("목록 갱신 전에 취소로 바뀐 발주 → 서버 409 → 공통 안내와 재조회, 그 환자는 '취소'로 고를 수 없다", async () => {
    const user = userEvent.setup();
    const { requests } = recordApiRequests();
    await selectPatient(user);
    // 화면이 다시 읽기 전에 모의 상태에서만 취소로 바꾼다(이벤트 없음)
    mockState.update((state) => ({
      ...state,
      orders: state.orders.map((o) =>
        o.meal_order_id === NS03_LUNCH ? { ...o, order_status: "cancelled" } : o,
      ),
    }));
    expect(badgeOf("NS03")).toHaveTextContent("미기록");

    await recordZero(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(POST_MEAL_TEXT.conflict);
    await waitForBadge("NS03", "취소");
    expect(patientItem("NS03")).toBeDisabled();
    expect(staffZeroButton("refused")).toBeDisabled();
    expect(orderSummary()).toHaveTextContent("완료 4 / 8 · 금식 1");
    expect(postRequests(requests)).toEqual([`POST ${STAFF_ZERO_PATH}`]);
  });

  it("전량 기록 오류는 환자를 바꾸면 지워지고, 새 환자에서 다시 실패하면 다시 보인다", async () => {
    const user = userEvent.setup();
    server.use(errorHandlers.staffZero("server"));
    await selectPatient(user);

    await recordZero(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(STAFF_ZERO_TEXT.failed);

    await user.click(patientItem("NS08"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await recordZero(user, "not_eaten");
    expect(await screen.findByRole("alert")).toHaveTextContent(STAFF_ZERO_TEXT.failed);
  });
});

describe("화면 ② 업로드 오류와 전량 기록 오류의 구분", () => {
  useNodeFileForMultipart();
  useMealScreenEnv(() => localTime(12, 0));

  /** 화면에 뜬 실패 안내가 하나뿐이고 `text`이며, 전량 기록 묶음 안에 있는지가 `inGroup`이다 */
  async function expectOnlyAlert(text: string, inGroup: boolean): Promise<void> {
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(text));
    const alert = screen.getByRole("alert");
    expect(staffZeroGroup().contains(alert)).toBe(inGroup);
  }

  it("업로드 500 → 업로드 문구(업로드 영역) → 전량 기록 500 → 묶음 안의 전량 기록 문구 → 업로드 실패 → 업로드 문구", async () => {
    const user = userEvent.setup();
    server.use(errorHandlers.postUpload("server"), errorHandlers.staffZero("server"));
    await selectPatient(user);
    await pickPhoto(user);

    await user.click(postMealControls().submit);
    await expectOnlyAlert(UPLOAD_FAILED, false);

    await recordZero(user);
    await expectOnlyAlert(STAFF_ZERO_TEXT.failed, true);
    expect(screen.queryByText(UPLOAD_FAILED)).not.toBeInTheDocument();

    await user.click(postMealControls().submit);
    await expectOnlyAlert(UPLOAD_FAILED, false);
    expect(screen.queryByText(STAFF_ZERO_TEXT.failed)).not.toBeInTheDocument();
  });
});

describe("화면 ② 전량 기록 200 뒤 재조회 실패", () => {
  useMealScreenEnv(() => localTime(12, 0));

  it("성공 안내 유지, 그 발주 재제출 불가, 새로 고침 안내 → 다시 시도는 조회만 보낸다", async () => {
    const user = userEvent.setup();
    const meals = { fail: false };
    server.use(
      http.get("/api/meals/:date/:meal", () => (meals.fail ? errorResponse("network") : undefined)),
    );
    const { requests } = recordApiRequests();
    await selectPatient(user);

    meals.fail = true;
    await recordZero(user);

    expect(await screen.findByText("목록을 새로 고치지 못했습니다")).toBeInTheDocument();
    expect(submitNotice()).toHaveTextContent("NS03 점심을 전량 거부로 기록했습니다");
    // 목록은 제출 전 그대로지만 로컬 제출 완료로 잠긴다
    expect(badgeOf("NS03")).toHaveTextContent("미기록");
    expect(screen.getByText(POST_MEAL_TEXT.notRecordable)).toBeInTheDocument();
    expectStaffZeroDisabled();
    expect(postMealControls().album).toBeDisabled();
    // 다른 환자는 그대로 기록할 수 있다
    await user.click(patientItem("NS08"));
    expect(staffZeroButton("refused")).toBeEnabled();
    await user.click(patientItem("NS03"));
    expect(staffZeroButton("refused")).toBeDisabled();

    meals.fail = false;
    await user.click(screen.getByRole("button", { name: "다시 시도" }));

    await waitForBadge("NS03", "완료 · 전량 거부");
    expect(postRequests(requests)).toEqual([`POST ${STAFF_ZERO_PATH}`]);
    expect(screen.queryByText("목록을 새로 고치지 못했습니다")).not.toBeInTheDocument();
    expect(submitNotice()).toHaveTextContent("NS03 점심을 전량 거부로 기록했습니다");
  });
});
