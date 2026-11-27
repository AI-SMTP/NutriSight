// 화면 ② 제출 중 이탈 테스트(스펙 3.5절 "요청이 끝나기 전에 화면을 떠나면 응답은 화면 상태에 반영하지 않는다").
//
// 관찰 방법은 화면 ①과 같다. 업로드 콜백은 성공(202)이면 그 끼니를 다시 읽고, 404·409 실패여도 다시 읽는다.
// 두 경우 모두 `getMeal` 호출로 이어지므로, `getMeal`을 실제 함수를 부르는 스파이로 감싸 "이탈 뒤 늦은 응답이
// 와도 `getMeal`이 더 불리지 않는다"를 단언한다. 요청 번호표의 단위 방어는 `useSubmission.test.tsx`가 맡는다.
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { getMeal } from "../../api/provisional";
import { errorResponse } from "../../mocks/errorHandlers";
import { server } from "../../mocks/server";
import { deferred } from "../../test/deferred";
import { PREVIEW, localTime, pickPhoto, useMealScreenEnv } from "../../test/mealScreen";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import {
  patientItem,
  postMealControls,
  submitNotice,
  waitForOrders,
} from "../../test/postMealScreen";
import { renderRoute } from "../../test/renderRoute";

vi.mock("../../api/provisional", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/provisional")>();
  return { ...actual, getMeal: vi.fn(actual.getMeal) };
});

describe("화면 ② 제출 중 이탈", () => {
  useNodeFileForMultipart();
  useMealScreenEnv(() => localTime(12, 0));

  let consoleError: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    vi.mocked(getMeal).mockClear();
    consoleError = vi.spyOn(console, "error");
  });
  afterEach(() => {
    consoleError.mockRestore();
  });

  /** 업로드 응답을 붙잡아 두는 핸들러. `arrived`는 요청이 도착했을 때, `gate`를 풀면 응답한다 */
  function holdUpload(late: "success" | "conflict") {
    const gate = deferred<void>();
    const arrived = deferred<void>();
    server.use(
      http.post("/api/photos", async () => {
        arrived.resolve();
        await gate.promise;
        return late === "success"
          ? HttpResponse.json(
              { photo_id: "late", meal_order_id: "NS03_2026-11-27_lunch", status: "uploaded" },
              { status: 202 },
            )
          : errorResponse("conflict");
      }),
    );
    return { gate, arrived };
  }

  it.each([
    ["성공(202)", "success"],
    ["실패(409)", "conflict"],
  ] as const)(
    "업로드 응답을 지연시킨 채 '/'로 이동하면 늦은 %s 응답을 반영하지 않는다",
    async (_l, late) => {
      const user = userEvent.setup();
      const { gate, arrived } = holdUpload(late);
      renderRoute("/post-meal");
      await waitForOrders();
      await user.click(patientItem("NS03"));
      await pickPhoto(user);
      await user.click(postMealControls().submit);
      await arrived.promise;

      await user.click(screen.getByRole("link", { name: "NutriSight" }));
      expect(screen.getByRole("heading", { name: "역할 선택" })).toBeInTheDocument();
      const callsBeforeLateResponse = vi.mocked(getMeal).mock.calls.length;
      await act(async () => {
        gate.resolve();
        await new Promise((resolve) => setTimeout(resolve, 20));
      });

      expect(vi.mocked(getMeal).mock.calls.length).toBe(callsBeforeLateResponse);
      expect(consoleError).not.toHaveBeenCalled();

      // 다시 들어와도 이전 요청의 안내·오류·사진·선택이 남지 않는다
      await user.click(screen.getByRole("link", { name: /요양보호사/ }));
      await waitForOrders();
      expect(submitNotice()).toBeEmptyDOMElement();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.queryByRole("img", PREVIEW)).not.toBeInTheDocument();
      expect(patientItem("NS03")).toHaveAttribute("aria-pressed", "false");
    },
  );

  it("업로드 중에는 끼니·환자·사진 입력·업로드를 막는다", async () => {
    const user = userEvent.setup();
    const { gate, arrived } = holdUpload("success");
    renderRoute("/post-meal");
    await waitForOrders();
    await user.click(patientItem("NS03"));
    await pickPhoto(user);

    await user.click(postMealControls().submit);
    await arrived.promise;

    const controls = postMealControls();
    expect(controls.meal("dinner")).toBeDisabled();
    expect(controls.album).toBeDisabled();
    expect(controls.submit).toBeDisabled();
    expect(patientItem("NS08")).toBeDisabled();
    expect(screen.getByRole("heading", { name: "사진 올리기" })).toHaveFocus();

    await act(async () => {
      gate.resolve();
      await arrived.promise;
    });
    expect(await screen.findByText("NS03 식후 사진을 올렸습니다")).toBeInTheDocument();
  });
});
