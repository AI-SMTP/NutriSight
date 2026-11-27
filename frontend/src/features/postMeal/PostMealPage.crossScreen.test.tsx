// 화면 ①② 연동 모의 테스트(스펙 2절 완료 기준의 "모의 테스트", 3.4절 기준 사진 등록·교체 규칙, 3.3절 SSE 연결과
// 조회 순서). 한 테스트 안에서 화면 ①(/baseline)과 화면 ②(/post-meal)를 함께 그려 같은 모의 상태·이벤트 버스를
// 쓴다. 두 화면은 각자 SSE 모의 연결을 가지며, `open`을 보낸 연결만 버스 이벤트를 받는다.
// 같은 라벨의 입력이 두 화면에 있으므로 화면 ①의 입력은 그 화면의 컨테이너 안에서 찾는다.
import { act, screen, waitFor, within, type RenderResult } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";

import type { PhotoStatusChangedEvent } from "../../api/provisional";
import { eventBus } from "../../mocks/eventBus";
import { confirmResubmit, waitForPlan } from "../../test/baselineScreen";
import { flushApiRequest, localTime, pickPhoto, useMealScreenEnv } from "../../test/mealScreen";
import { createMockConnect, type MockConnect } from "../../test/mockConnect";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import {
  POST_MEAL_TEXT,
  baselineGuide,
  confirmStaffZero,
  patientItem,
  staffZeroButton,
  waitForBadge,
  waitForOrders,
} from "../../test/postMealScreen";
import { renderRoute } from "../../test/renderRoute";
import { RESUBMIT_SHEET } from "../baseline/messages";

/** 화면 ②를 그리고 첫 조회를 기다린다. `open`이 참이면 SSE 연결을 연다 */
async function renderPostMeal(open: boolean): Promise<MockConnect> {
  const mock = createMockConnect();
  renderRoute("/post-meal", mock.connect);
  await waitForOrders();
  if (open) act(() => mock.open());
  return mock;
}

/** 화면 ①을 그리고 등록 상태 표시를 기다린다(이 연결은 열지 않는다) */
async function renderBaseline(): Promise<RenderResult> {
  const view = renderRoute("/baseline", createMockConnect().connect);
  await waitForPlan();
  return view;
}

/** 화면 ①에서 사진을 골라 기준 사진 업로드를 누른다 */
async function uploadBaselineIn(user: UserEvent, view: RenderResult): Promise<void> {
  await pickPhoto(user, "tray.jpg", view.container);
  await user.click(within(view.container).getByRole("button", { name: "기준 사진 업로드" }));
}

/** 이 테스트 동안 버스에 나간 이벤트를 모은다 */
function captureEvents(): PhotoStatusChangedEvent[] {
  const events: PhotoStatusChangedEvent[] = [];
  const unsubscribe = eventBus.subscribe((event) => events.push(event));
  onTestFinished(unsubscribe);
  return events;
}

describe("화면 ①② 연동: 저녁(기준 사진 없음, 대기 사진 없음)", () => {
  useNodeFileForMultipart();
  useMealScreenEnv(() => localTime(18, 0));

  it("화면 ①에서 기준 사진을 등록하면 baseline 이벤트로 화면 ② 안내가 '기준 사진 등록됨'으로 바뀐다", async () => {
    const user = userEvent.setup();
    const events = captureEvents();
    await renderPostMeal(true);
    await waitFor(() => expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineMissing));
    const baseline = await renderBaseline();

    await uploadBaselineIn(user, baseline);

    await waitFor(() => expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineReady));
    expect(events).toEqual([
      expect.objectContaining({
        kind: "baseline",
        meal_plan_id: "2026-11-27_dinner_general",
        patient_id: null,
        meal_order_id: null,
      }),
    ]);
  });

  it("화면 ② 첫 조회 뒤 첫 open 전에 등록된 기준 사진은 첫 open 뒤 재조회로 반영된다", async () => {
    const user = userEvent.setup();
    const post = await renderPostMeal(false);
    const baseline = await renderBaseline();

    // 화면 ②의 연결이 아직 열리지 않아 이 등록의 이벤트는 화면 ②에 전달되지 않는다
    await uploadBaselineIn(user, baseline);
    await waitFor(() => expect(screen.getByTestId("baseline-status")).toHaveTextContent(/등록됨/));
    await flushApiRequest();
    expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineMissing);

    act(() => post.open());

    await waitFor(() => expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineReady));
  });
});

describe("화면 ①② 연동: 점심 기준 사진 교체", () => {
  useNodeFileForMultipart();
  useMealScreenEnv(() => localTime(12, 0));

  it("재촬영 필요 발주를 전량 거부로 기록한 뒤 기준 사진을 교체해도 '완료 · 전량 거부'로 남는다", async () => {
    const user = userEvent.setup();
    await renderPostMeal(true);
    await user.click(patientItem("NS05"));
    await user.click(staffZeroButton("refused"));
    await confirmStaffZero(user);
    await waitForBadge("NS05", "완료 · 전량 거부");
    const baseline = await renderBaseline();

    await uploadBaselineIn(user, baseline);
    await confirmResubmit(user);

    // 다른 완료 사진이 다시 처리되는 것으로 화면 ②가 교체 뒤 상태를 다시 읽었음을 확인한다
    await waitForBadge("NS02", "처리 중");
    expect(within(patientItem("NS05")).getByText("완료 · 전량 거부")).toBeInTheDocument();
  });

  it("기준 사진을 교체하면 완료·재촬영 필요 환자가 화면 ②에서 '처리 중'이 되고, 화면 ①의 안내와 같다", async () => {
    const user = userEvent.setup();
    await renderPostMeal(true);
    const baseline = await renderBaseline();

    await uploadBaselineIn(user, baseline);

    // 화면 ①의 교체 안내: 식후 사진을 모두 새 기준으로 다시 분석하고, 사진 없이 기록한 끼니는 그대로다
    const sheet = screen.getByRole("dialog");
    expect(sheet).toHaveAccessibleDescription(RESUBMIT_SHEET.message);
    expect(RESUBMIT_SHEET.message).toBe(
      "다시 올리면 이 끼니의 식후 사진을 모두 새 기준으로 다시 분석합니다(분석 중인 사진은 끝난 뒤 다시 분석). 사진 없이 기록한 끼니는 그대로입니다",
    );
    await confirmResubmit(user);

    // "식후 사진을 모두 새 기준으로 다시 분석": 완료(NS02·NS07·NS10)·재촬영 필요(NS05) → 처리 중
    for (const name of ["NS02", "NS07", "NS10", "NS05"]) await waitForBadge(name, "처리 중");
    // "분석 중인 사진은 끝난 뒤 다시 분석": 처리 중(NS04·NS09)은 처리 중 그대로
    for (const name of ["NS04", "NS09"]) await waitForBadge(name, "처리 중");
    // "사진 없이 기록한 끼니는 그대로": 전량 거부(NS06)는 바뀌지 않는다. 사진이 없는 미기록(NS03)도 그대로다
    await waitForBadge("NS06", "완료 · 전량 거부");
    await waitForBadge("NS03", "미기록");
  });
});
