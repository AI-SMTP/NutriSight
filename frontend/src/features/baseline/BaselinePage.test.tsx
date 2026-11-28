// 화면 ① 기준 식전 사진 테스트(`docs/specs/frontend-shell-upload.md` '기준 사진 화면' 1~6번, '테스트와 E2E' 화면 ① 흐름).
// 기본 MSW 핸들러와 픽스처(점심 기준 사진 있음, 저녁 없음)를 쓴다. 시계는 Date만 고정한다.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { errorHandlers } from "../../mocks/errorHandlers";
import { DEMO_DATE } from "../../mocks/fixtures";
import { server } from "../../mocks/server";
import { mockState } from "../../mocks/state";
import {
  PREVIEW,
  baselineControls,
  baselinePath,
  confirmResubmit,
  expectAllInputsDisabled,
  localTime,
  mealPath,
  pickPhoto,
  postRequests,
  useBaselineScreenEnv,
  waitForBaselineStatus,
  waitForPlan,
} from "../../test/baselineScreen";
import { deferred } from "../../test/deferred";
import { recordApiRequests } from "../../test/heldRequests";
import { createMockConnect } from "../../test/mockConnect";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import { renderRoute } from "../../test/renderRoute";

const RESUBMIT_MESSAGE =
  "다시 올리면 이 끼니의 식후 사진을 모두 새 기준으로 다시 분석합니다(분석 중인 사진은 끝난 뒤 다시 분석). 사진 없이 기록한 끼니는 그대로입니다";

/** 칸 하나의 표시 문구(메뉴명·배식량) */
function cellTexts(rowName: string): string[] {
  const row = screen.getByRole("list", { name: rowName });
  return within(row)
    .getAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

describe("화면 ① 기본 선택", () => {
  describe.each([
    [localTime(9, 0), "breakfast"],
    [localTime(12, 0), "lunch"],
    [localTime(18, 0), "dinner"],
  ] as const)("%s", (at, meal) => {
    useBaselineScreenEnv(() => at);

    it(`날짜는 시연일, 끼니는 시각 규칙(${meal})으로 고른다`, async () => {
      renderRoute("/baseline");

      await waitForPlan();
      const controls = baselineControls();
      expect(controls.date).toHaveValue(DEMO_DATE);
      expect(controls.meal(meal)).toBeChecked();
    });
  });
});

describe("화면 ① 배식 계획과 등록 상태", () => {
  useBaselineScreenEnv(() => localTime(12, 0));

  it("6칸을 식판 배치(윗줄 칸 3~6, 아랫줄 칸 1~2)대로 메뉴명·배식량과 함께 보여 준다", async () => {
    renderRoute("/baseline");

    await waitForPlan();
    expect(cellTexts("윗줄")).toEqual([
      "소불고기90g",
      "애호박볶음60g",
      "어묵볶음50g",
      "배추김치40g",
    ]);
    expect(cellTexts("아랫줄")).toEqual(["잡곡밥210g", "근대된장국250g"]);
  });

  it("기준 사진이 있으면 등록 상태가 '등록됨 (HH:MM)'이다", async () => {
    mockState.reset({
      photos: { fx_lunch_baseline: { uploaded_at: localTime(11, 50).toISOString() } },
    });
    renderRoute("/baseline");

    expect(await waitForPlan()).toHaveTextContent(/^등록됨 \(11:50\)$/);
  });

  it("기준 사진이 없는 끼니로 바꾸면 등록 상태가 '아직 없음'이다", async () => {
    const user = userEvent.setup();
    renderRoute("/baseline");
    await waitForPlan();

    await user.click(baselineControls().meal("dinner"));

    await waitForBaselineStatus("아직 없음");
    expect(cellTexts("아랫줄")).toEqual(["쌀밥210g", "맑은두부국250g"]);
  });

  it("촬영 안내 두 줄과 사진 입력 두 개를 둔다(촬영 입력만 후면 카메라 힌트)", async () => {
    renderRoute("/baseline");
    await waitForPlan();

    expect(screen.getByText("식판 바로 위에서 수직으로 찍어 주세요")).toBeInTheDocument();
    expect(screen.getByText("수저나 손이 칸을 가리지 않게 해 주세요")).toBeInTheDocument();
    const { camera, album } = baselineControls();
    expect(camera).toHaveAttribute("capture", "environment");
    expect(album).not.toHaveAttribute("capture");
  });
});

describe("화면 ① 업로드", () => {
  useNodeFileForMultipart();
  useBaselineScreenEnv(() => localTime(17, 20));

  it("사진을 고르기 전에는 업로드 버튼이 막혀 있다", async () => {
    renderRoute("/baseline");
    await waitForPlan();

    expect(baselineControls().submit).toBeDisabled();
  });

  it("저녁 업로드 성공 → 일시 안내 '기준 사진 등록됨', 재조회 뒤 등록 상태 '등록됨 (시각)'", async () => {
    const user = userEvent.setup();
    const { requests } = recordApiRequests();
    renderRoute("/baseline");
    expect(await waitForPlan()).toHaveTextContent("아직 없음");
    // 안내 영역은 처음부터 있고(보조 기술이 바뀐 내용을 읽도록) 비어 있다
    expect(screen.getByRole("status")).toBeEmptyDOMElement();

    await pickPhoto(user);
    await user.click(baselineControls().submit);

    // 처음 등록이므로 확인 시트 없이 바로 요청한다
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const notice = screen.getByRole("status");
    await waitFor(() => expect(notice).toHaveTextContent("기준 사진 등록됨"));
    await waitForBaselineStatus(/^등록됨 \(17:20\)$/);
    // 일시 안내와 등록 상태는 서로 다른 요소다
    expect(notice).not.toBe(screen.getByTestId("baseline-status"));
    expect(notice).not.toContainElement(screen.getByTestId("baseline-status"));
    expect(requests).toEqual([
      "GET /api/meta",
      `GET ${mealPath("dinner")}`,
      `POST ${baselinePath("dinner")}`,
      `GET ${mealPath("dinner")}`,
    ]);
    // 등록이 끝나면 고른 사진을 비운다
    expect(screen.queryByRole("img", PREVIEW)).not.toBeInTheDocument();
  });

  it("이미 등록된 끼니에서 업로드하면 재분석 확인 시트를 보이고, 확인해야 요청한다", async () => {
    const user = userEvent.setup();
    const { requests } = recordApiRequests();
    renderRoute("/baseline");
    await waitForPlan();
    await user.click(baselineControls().meal("lunch"));
    await waitForBaselineStatus("등록됨");

    await pickPhoto(user);
    await user.click(baselineControls().submit);
    const sheet = screen.getByRole("dialog");
    expect(sheet).toHaveTextContent(RESUBMIT_MESSAGE);

    await user.click(within(sheet).getByRole("button", { name: "취소" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(postRequests(requests)).toEqual([]);

    await user.click(baselineControls().submit);
    await confirmResubmit(user);

    // 시트가 닫히고 업로드 버튼이 막혀도 포커스가 body로 빠지지 않는다
    expect(screen.getByRole("heading", { name: "사진 올리기" })).toHaveFocus();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("기준 사진 등록됨"));
    expect(postRequests(requests)).toEqual([`POST ${baselinePath("lunch")}`]);
  });

  it("업로드 중에는 날짜·끼니·사진 입력·제출을 막고, 요청 대상(저녁)과 사진을 고정한다", async () => {
    const user = userEvent.setup();
    const gate = deferred<void>();
    const received: { path: string; file: FormDataEntryValue | null }[] = [];
    server.use(
      http.post("/api/meals/:date/:meal/baseline", async ({ request }) => {
        const form = await request.formData();
        received.push({ path: new URL(request.url).pathname, file: form.get("file") });
        await gate.promise;
        return HttpResponse.json(
          { photo_id: "mock_photo_1", uploaded_at: new Date().toISOString() },
          { status: 201 },
        );
      }),
    );
    renderRoute("/baseline");
    await waitForPlan();
    await pickPhoto(user, "dinner.jpg");

    await user.click(baselineControls().submit);

    await waitFor(() => expect(received).toHaveLength(1));
    expectAllInputsDisabled();
    expect(screen.getByRole("heading", { name: "사진 올리기" })).toHaveFocus();
    expect(received[0]?.path).toBe(baselinePath("dinner"));
    // 고른 사진(2048바이트 JPEG, jsdom에서는 변환하지 못해 원본 그대로)을 보낸다
    expect(received[0]?.file).toMatchObject({ size: 2048, type: "image/jpeg" });

    gate.resolve();
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("기준 사진 등록됨"));
    await waitFor(() => expect(baselineControls().meal("lunch")).toBeEnabled());
  });

  it("확인 시트가 열린 동안 그 끼니가 '배식 계획 없음'으로 바뀌면 확인해도 요청하지 않고, 포커스는 업로드 영역 제목으로 간다", async () => {
    const user = userEvent.setup();
    const mock = createMockConnect();
    renderRoute("/baseline", mock.connect);
    await waitForPlan();
    await user.click(baselineControls().meal("lunch"));
    await waitForBaselineStatus("등록됨");
    await pickPhoto(user);
    await user.click(baselineControls().submit);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    // 시트가 열린 채로 SSE open → 재조회가 404를 받는다
    server.use(errorHandlers.meal("not_found"));
    const { requests } = recordApiRequests();
    act(() => mock.open());
    expect(await screen.findByText("이 날짜·끼니의 배식 계획이 없습니다")).toBeInTheDocument();

    await confirmResubmit(user);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(postRequests(requests)).toEqual([]);
    // 시트를 연 업로드 버튼이 막혔으므로 포커스는 body가 아니라 업로드 영역 제목으로 간다
    expect(screen.getByRole("heading", { name: "사진 올리기" })).toHaveFocus();
  });
});
