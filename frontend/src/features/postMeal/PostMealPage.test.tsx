// 화면 ② 식후 사진 테스트(`docs/specs/frontend-shell-upload.md` '식후 사진 화면' 1~5·7번, '테스트와 E2E' 화면 ② 흐름).
// 기본 MSW 핸들러와 픽스처를 쓴다. 점심: 기준 사진 있음, NS01 금식, NS03·NS08 미기록, NS04·NS09 처리 중,
// NS02·NS07·NS10 완료, NS05 재촬영 필요, NS06 완료 · 전량 거부. 저녁: 기준 사진 없음, 모두 미기록.
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";

import { DEMO_DATE, mealOrderId } from "../../mocks/fixtures";
import { installMockRuntime } from "../../mocks/runtime";
import { server } from "../../mocks/server";
import { mockState } from "../../mocks/state";
import { recordApiRequests } from "../../test/heldRequests";
import {
  PREVIEW,
  localTime,
  pickPhoto,
  postRequests,
  useMealScreenEnv,
} from "../../test/mealScreen";
import { createMockConnect } from "../../test/mockConnect";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import {
  POST_MEAL_TEXT,
  badgeOf,
  baselineGuide,
  orderSummary,
  patientItem,
  patientList,
  postMealControls,
  waitForBadge,
  waitForOrders,
  submitNotice,
} from "../../test/postMealScreen";
import { renderRoute } from "../../test/renderRoute";

const CANCELLED_NS08 = {
  orders: { [mealOrderId("NS08", DEMO_DATE, "lunch")]: { order_status: "cancelled" as const } },
};

describe("화면 ② 끼니 선택", () => {
  describe.each([
    [localTime(9, 0), "breakfast"],
    [localTime(12, 0), "lunch"],
    [localTime(18, 0), "dinner"],
  ] as const)("%s", (at, meal) => {
    useMealScreenEnv(() => at);

    it(`'오늘' 세 끼만 고르고(날짜 입력 없음) 기본 끼니는 시각 규칙(${meal})이다`, async () => {
      renderRoute("/post-meal");

      await waitForOrders();
      expect(screen.queryByLabelText("날짜")).not.toBeInTheDocument();
      expect(postMealControls().meal(meal)).toBeChecked();
      for (const label of ["오늘 아침", "오늘 점심", "오늘 저녁"]) {
        expect(screen.getByLabelText(label)).toBeInTheDocument();
      }
    });
  });
});

describe("화면 ② 환자 목록과 업로드 현황", () => {
  useMealScreenEnv(() => localTime(12, 0));

  it("환자 목록을 'room · display_name'과 발주별 배지로 보여 준다", async () => {
    renderRoute("/post-meal");
    await waitForOrders();

    expect(patientItem("NS03")).toHaveTextContent(/^302호 · NS03/);
    expect(badgeOf("NS01")).toHaveTextContent("금식");
    expect(badgeOf("NS02")).toHaveTextContent(/^완료$/);
    expect(badgeOf("NS03")).toHaveTextContent("미기록");
    expect(badgeOf("NS04")).toHaveTextContent(/^처리 중$/);
    expect(badgeOf("NS05")).toHaveTextContent("재촬영 필요");
    expect(badgeOf("NS06")).toHaveTextContent("완료 · 전량 거부");
    expect(badgeOf("NS09")).toHaveTextContent(/^처리 중$/);
    expect(orderSummary()).toHaveTextContent(/^완료 4 \/ 9 · 금식 1$/);
  });

  it("환자 항목·사진 입력 라벨·업로드 버튼은 공용 컴포넌트(터치 크기 적용)로 그린다", async () => {
    renderRoute("/post-meal");
    await waitForOrders();

    // 공용 Button은 data-variant를 단다(Button.module.css의 min-height·min-width var(--touch-min))
    expect(patientItem("NS03")).toHaveAttribute("data-variant");
    expect(postMealControls().submit).toHaveAttribute("data-variant");
    // 사진 입력 라벨은 공용 PhotoPicker의 라벨이다
    expect(postMealControls().album.closest("label")).toHaveTextContent("앨범에서 선택");
    expect(postMealControls().camera).toHaveAttribute("capture", "environment");
  });

  it("금식·취소 환자는 회색 배지로 보이고 고를 수 없으며, 현황 분모에서 빠진다", async () => {
    const user = userEvent.setup();
    mockState.reset(CANCELLED_NS08);
    renderRoute("/post-meal");
    await waitForOrders();

    for (const [name, label] of [
      ["NS01", "금식"],
      ["NS08", "취소"],
    ] as const) {
      const item = patientItem(name);
      expect(badgeOf(name)).toHaveTextContent(label);
      expect(badgeOf(name)).toHaveAttribute("data-tone", "neutral");
      expect(item).toBeDisabled();
      await user.click(item);
      expect(item).toHaveAttribute("aria-pressed", "false");
    }
    expect(postMealControls().submit).toHaveAccessibleName("식후 사진 업로드");
    expect(postMealControls().album).toBeDisabled();
    expect(orderSummary()).toHaveTextContent(/^완료 4 \/ 8 · 금식 1$/);
  });

  it("미기록 환자를 고르면 선택 표시와 '<환자> 식후 사진 업로드' 버튼, 사진 입력이 열린다", async () => {
    const user = userEvent.setup();
    renderRoute("/post-meal");
    await waitForOrders();
    expect(postMealControls().album).toBeDisabled();

    await user.click(patientItem("NS03"));

    expect(patientItem("NS03")).toHaveAttribute("aria-pressed", "true");
    expect(postMealControls().submit).toHaveAccessibleName("NS03 식후 사진 업로드");
    expect(postMealControls().album).toBeEnabled();
    // 사진을 고르기 전에는 업로드할 수 없다
    expect(postMealControls().submit).toBeDisabled();
    expect(screen.queryByText(POST_MEAL_TEXT.notRecordable)).not.toBeInTheDocument();
  });

  it.each([
    ["처리 중", "NS04"],
    ["완료", "NS02"],
    ["완료 · 전량 거부", "NS06"],
  ])("%s 환자(%s)를 고르면 사진 입력과 업로드가 막히고 안내를 보인다", async (_l, name) => {
    const user = userEvent.setup();
    renderRoute("/post-meal");
    await waitForOrders();

    await user.click(patientItem(name));

    expect(patientItem(name)).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(POST_MEAL_TEXT.notRecordable)).toBeInTheDocument();
    const { camera, album, submit } = postMealControls();
    expect(camera).toBeDisabled();
    expect(album).toBeDisabled();
    expect(submit).toBeDisabled();
    // 막힌 이유를 업로드 버튼의 설명으로 읽는다
    expect(submit).toHaveAccessibleDescription(POST_MEAL_TEXT.notRecordable);
  });

  it("재촬영 필요 환자는 다시 올릴 수 있다", async () => {
    const user = userEvent.setup();
    renderRoute("/post-meal");
    await waitForOrders();

    await user.click(patientItem("NS05"));

    expect(postMealControls().album).toBeEnabled();
    expect(screen.queryByText(POST_MEAL_TEXT.notRecordable)).not.toBeInTheDocument();
    expect(postMealControls().submit).toHaveAccessibleDescription("");
  });

  it("기준 사진 안내가 끼니의 기준 사진 유무로 바뀐다", async () => {
    const user = userEvent.setup();
    renderRoute("/post-meal");
    await waitForOrders();
    expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineReady);

    await user.click(postMealControls().meal("dinner"));

    await waitFor(() => expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineMissing));
    expect(orderSummary()).toHaveTextContent(/^완료 0 \/ 9 · 금식 1$/);
  });
});

describe("화면 ② 식후 사진 업로드", () => {
  useNodeFileForMultipart();
  useMealScreenEnv(() => localTime(12, 0));

  it("점심 NS03 업로드 → 202 → 재조회 '처리 중' → 처리 단계 이벤트 → '완료'", async () => {
    const user = userEvent.setup();
    const runtime = installMockRuntime({ stepDelayMs: 0, manualSteps: true });
    const mock = createMockConnect();
    const { requests } = recordApiRequests();
    renderRoute("/post-meal", mock.connect);
    await waitForOrders();
    act(() => mock.open());

    await user.click(patientItem("NS03"));
    await pickPhoto(user);
    await user.click(postMealControls().submit);

    await waitForBadge("NS03", "처리 중");
    expect(submitNotice()).toHaveTextContent("NS03 식후 사진을 올렸습니다");
    expect(postRequests(requests)).toEqual(["POST /api/photos"]);
    // 올린 뒤에는 고른 사진을 비우고, 같은 발주는 다시 올릴 수 없다
    expect(screen.queryByRole("img", PREVIEW)).not.toBeInTheDocument();
    expect(postMealControls().submit).toBeDisabled();

    act(() => runtime.finishAll());

    await waitForBadge("NS03", "완료");
    expect(orderSummary()).toHaveTextContent(/^완료 5 \/ 9 · 금식 1$/);
  });

  it("요청 본문(multipart)에 고른 환자·끼니·날짜·사진을 담는다", async () => {
    const user = userEvent.setup();
    const received: Record<string, FormDataEntryValue | null>[] = [];
    server.use(
      http.post("/api/photos", async ({ request }) => {
        const form = await request.clone().formData();
        received.push({
          patient_id: form.get("patient_id"),
          date: form.get("date"),
          meal: form.get("meal"),
          file: form.get("file"),
        });
        return undefined;
      }),
    );
    renderRoute("/post-meal");
    await waitForOrders();

    await user.click(patientItem("NS08"));
    await pickPhoto(user);
    await user.click(postMealControls().submit);

    await waitForBadge("NS08", "처리 중");
    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({ patient_id: "NS08", date: DEMO_DATE, meal: "lunch" });
    // 고른 사진(2048바이트 JPEG, jsdom에서는 변환하지 못해 원본 그대로)을 보낸다
    expect(received[0]?.file).toMatchObject({ size: 2048, type: "image/jpeg" });
  });

  it("성공 안내는 다른 끼니를 보는 동안 숨고, 그 끼니로 돌아오면 다시 보인다", async () => {
    const user = userEvent.setup();
    renderRoute("/post-meal");
    await waitForOrders();
    await user.click(patientItem("NS03"));
    await pickPhoto(user);
    await user.click(postMealControls().submit);
    await waitFor(() => expect(submitNotice()).toHaveTextContent("NS03 식후 사진을 올렸습니다"));

    await user.click(postMealControls().meal("dinner"));
    await waitFor(() => expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineMissing));
    expect(submitNotice()).toBeEmptyDOMElement();

    await user.click(postMealControls().meal("lunch"));
    await waitFor(() => expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineReady));
    expect(submitNotice()).toHaveTextContent("NS03 식후 사진을 올렸습니다");
  });

  it("사진을 고른 뒤 갱신으로 그 발주가 '처리 중'이 되면 선택은 남고 사진 입력·업로드가 막힌다", async () => {
    const user = userEvent.setup();
    const mock = createMockConnect();
    renderRoute("/post-meal", mock.connect);
    await waitForOrders();
    await user.click(patientItem("NS03"));
    await pickPhoto(user);
    expect(postMealControls().submit).toBeEnabled();

    // 다른 기기가 먼저 올린 것처럼 모의 상태만 바꾸고, SSE open으로 다시 읽게 한다
    mockState.update((state) => ({
      ...state,
      orders: state.orders.map((o) =>
        o.meal_order_id === mealOrderId("NS03", DEMO_DATE, "lunch")
          ? { ...o, record_status: "pending" }
          : o,
      ),
    }));
    act(() => mock.open());

    await waitForBadge("NS03", "처리 중");
    expect(patientItem("NS03")).toHaveAttribute("aria-pressed", "true");
    const { album, camera, submit } = postMealControls();
    expect(album).toBeDisabled();
    expect(camera).toBeDisabled();
    expect(submit).toBeDisabled();
    expect(submit).toHaveAccessibleName("NS03 식후 사진 업로드");
    expect(submit).toHaveAccessibleDescription(POST_MEAL_TEXT.notRecordable);
  });

  it("저녁(기준 사진 없음) 업로드 → '처리 중 · 기준 사진 대기'", async () => {
    const user = userEvent.setup();
    renderRoute("/post-meal");
    await waitForOrders();
    await user.click(postMealControls().meal("dinner"));
    await waitFor(() => expect(baselineGuide()).toHaveTextContent(POST_MEAL_TEXT.baselineMissing));

    await user.click(patientItem("NS03"));
    await pickPhoto(user);
    await user.click(postMealControls().submit);

    await waitForBadge("NS03", "처리 중 · 기준 사진 대기");
    expect(patientList()).toBeInTheDocument();
  });
});
