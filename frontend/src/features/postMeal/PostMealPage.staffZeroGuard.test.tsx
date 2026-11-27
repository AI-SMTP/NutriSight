// 화면 ② 전량 기록 버튼 활성·비활성 테스트(스펙 3.5절 업로드·전량 기록 임시 규칙, 시연일 초기화,
// 요청 대상 고정과 선택 전환 규칙). 버튼은 미기록·재촬영 필요 환자를 골랐고 요청이 없을 때만 열린다.
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { errorHandlers } from "../../mocks/errorHandlers";
import { DEMO_DATE, mealOrderId } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { mockState } from "../../mocks/state";
import { holdPost } from "../../test/heldRequests";
import { localTime, pickPhoto, useMealScreenEnv } from "../../test/mealScreen";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import {
  POST_MEAL_TEXT,
  confirmStaffZero,
  expectStaffZeroDisabled,
  expectStaffZeroEnabled,
  patientItem,
  postMealControls,
  staffZeroButton,
  waitForOrders,
} from "../../test/postMealScreen";
import { renderRoute } from "../../test/renderRoute";

describe("화면 ② 전량 기록 버튼: 시연일 조회 실패", () => {
  useMealScreenEnv(() => localTime(12, 0));

  it.each([
    ["네트워크 오류", "network"],
    ["서버 오류(500)", "server"],
  ] as const)("%s → '전량 거부'·'전량 미섭취' 비활성", async (_l, kind) => {
    server.use(errorHandlers.meta(kind));
    renderRoute("/post-meal");

    expect(await screen.findByText("시연일을 불러오지 못했습니다")).toBeInTheDocument();
    expectStaffZeroDisabled();
  });
});

describe("화면 ② 전량 기록 버튼: 고른 환자", () => {
  useMealScreenEnv(() => localTime(12, 0));

  it("환자를 고르기 전에는 비활성이다", async () => {
    renderRoute("/post-meal");
    await waitForOrders();

    expectStaffZeroDisabled();
  });

  it.each([
    ["처리 중", "NS04"],
    ["완료", "NS02"],
  ])("%s 환자(%s) → 두 버튼 비활성, 임시 규칙 안내", async (_l, name) => {
    const user = userEvent.setup();
    renderRoute("/post-meal");
    await waitForOrders();

    await user.click(patientItem(name));

    expectStaffZeroDisabled();
    expect(screen.getByText(POST_MEAL_TEXT.notRecordable)).toBeInTheDocument();
    // 막힌 이유를 버튼의 설명으로 읽는다
    expect(staffZeroButton("refused")).toHaveAccessibleDescription(POST_MEAL_TEXT.notRecordable);
  });

  it.each([
    ["미기록", "NS03"],
    ["재촬영 필요", "NS05"],
  ])("%s 환자(%s) → 두 버튼 활성", async (_l, name) => {
    const user = userEvent.setup();
    renderRoute("/post-meal");
    await waitForOrders();

    await user.click(patientItem(name));

    expectStaffZeroEnabled();
    expect(screen.queryByText(POST_MEAL_TEXT.notRecordable)).not.toBeInTheDocument();
  });

  it("금식·취소 환자는 목록에서 고를 수 없어 버튼이 대상 없음 상태로 비활성이다", async () => {
    const user = userEvent.setup();
    mockState.reset({
      orders: { [mealOrderId("NS08", DEMO_DATE, "lunch")]: { order_status: "cancelled" } },
    });
    renderRoute("/post-meal");
    await waitForOrders();

    for (const name of ["NS01", "NS08"]) {
      await user.click(patientItem(name));
      expect(patientItem(name)).toHaveAttribute("aria-pressed", "false");
      expectStaffZeroDisabled();
    }
  });
});

describe("화면 ② 전량 기록 버튼: 요청 진행 중", () => {
  useNodeFileForMultipart();
  useMealScreenEnv(() => localTime(12, 0));

  it("업로드 요청 중에는 두 버튼이 비활성이고, 끝나면 다른 환자에서 다시 열린다", async () => {
    const user = userEvent.setup();
    const { gate, arrived } = holdPost("/api/photos");
    renderRoute("/post-meal");
    await waitForOrders();
    await user.click(patientItem("NS03"));
    await pickPhoto(user);
    expectStaffZeroEnabled();

    await user.click(postMealControls().submit);
    await arrived.promise;

    expectStaffZeroDisabled();

    await act(async () => gate.resolve());
    expect(await screen.findByText("NS03 식후 사진을 올렸습니다")).toBeInTheDocument();
    await user.click(patientItem("NS08"));
    expectStaffZeroEnabled();
  });

  it("전량 기록 요청 중에는 두 버튼·업로드·끼니·환자 선택이 비활성이다", async () => {
    const user = userEvent.setup();
    const { gate, arrived } = holdPost("/api/meal-orders/:id/staff-zero");
    renderRoute("/post-meal");
    await waitForOrders();
    await user.click(patientItem("NS03"));
    await pickPhoto(user);

    await user.click(staffZeroButton("refused"));
    await confirmStaffZero(user);
    await arrived.promise;

    expectStaffZeroDisabled();
    const controls = postMealControls();
    expect(controls.submit).toBeDisabled();
    expect(controls.album).toBeDisabled();
    expect(controls.meal("dinner")).toBeDisabled();
    expect(patientItem("NS08")).toBeDisabled();
    expect(screen.getByRole("heading", { name: "사진 올리기" })).toHaveFocus();

    await act(async () => gate.resolve());
    expect(await screen.findByText("NS03 점심을 전량 거부로 기록했습니다")).toBeInTheDocument();
  });
});
