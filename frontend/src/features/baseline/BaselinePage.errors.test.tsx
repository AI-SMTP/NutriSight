// 화면 ① 오류 테스트(`docs/specs/frontend-shell-upload.md` '끼니 조회 순서 규칙'·'제출과 잠금 규칙'·'시연일 초기화'·'테스트와 E2E'의
// 오류 주입·시연일 실패·조회 경합).
// 제출 중 이탈은 `BaselinePage.leave.test.tsx`에 있다.
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { http } from "msw";

import type { ApiErrorKind } from "../../api/provisional";
import { errorHandlers, errorResponse } from "../../mocks/errorHandlers";
import { server } from "../../mocks/server";
import {
  PREVIEW,
  baselineControls,
  baselinePath,
  confirmResubmit,
  expectAllInputsDisabled,
  mealPath,
  pickPhoto,
  postRequests,
  useBaselineScreenEnv,
  waitForBaselineStatus,
  waitForPlan,
} from "../../test/baselineScreen";
import { holdMealRequests, recordApiRequests } from "../../test/heldRequests";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import { renderRoute } from "../../test/renderRoute";

function mealGets(requests: readonly string[]): string[] {
  return requests.filter((r) => r.startsWith("GET /api/meals/"));
}

describe("화면 ① 시연일 조회 실패", () => {
  useBaselineScreenEnv();

  it.each([
    ["네트워크 오류", "network"],
    ["서버 오류(500)", "server"],
  ] as const)(
    "%s → 안내와 모든 입력 차단, 끼니 조회 0건 → 다시 시도 성공 → 배식 계획",
    async (_l, kind) => {
      const user = userEvent.setup();
      server.use(errorHandlers.meta(kind));
      const { requests } = recordApiRequests();
      renderRoute("/baseline");

      expect(await screen.findByText("시연일을 불러오지 못했습니다")).toBeInTheDocument();
      expectAllInputsDisabled();
      expect(mealGets(requests)).toEqual([]);

      server.resetHandlers();
      const after = recordApiRequests();
      await user.click(screen.getByRole("button", { name: "다시 시도" }));

      await waitForPlan();
      expect(mealGets(after.requests)).toEqual([`GET ${mealPath("dinner")}`]);
      expect(screen.getByRole("list", { name: "윗줄" })).toBeInTheDocument();
      expect(screen.queryByText("시연일을 불러오지 못했습니다")).not.toBeInTheDocument();
      expect(baselineControls().date).toBeEnabled();
    },
  );
});

describe("화면 ① 끼니 조회 실패", () => {
  useBaselineScreenEnv();

  /** 최초 조회에 주입하거나(initial), 최초 조회는 성공시킨 뒤 점심으로 바꾼 조회에 주입한다(switch) */
  async function injectMealError(
    user: UserEvent,
    timing: "initial" | "switch",
    kind: ApiErrorKind,
  ) {
    if (timing === "initial") {
      server.use(errorHandlers.meal(kind));
      renderRoute("/baseline");
      return;
    }
    renderRoute("/baseline");
    await waitForPlan();
    server.use(errorHandlers.meal(kind));
    await user.click(baselineControls().meal("lunch"));
  }

  it.each(["initial", "switch"] as const)(
    "404(%s) → '이 날짜·끼니의 배식 계획이 없습니다', 날짜·끼니는 고를 수 있고 사진 입력·제출은 막힌다",
    async (timing) => {
      const user = userEvent.setup();
      await injectMealError(user, timing, "not_found");

      expect(await screen.findByText("이 날짜·끼니의 배식 계획이 없습니다")).toBeInTheDocument();
      const controls = baselineControls();
      expect(controls.date).toBeEnabled();
      expect(controls.meal("breakfast")).toBeEnabled();
      expect(controls.camera).toBeDisabled();
      expect(controls.album).toBeDisabled();
      expect(controls.submit).toBeDisabled();
      expect(screen.queryByTestId("baseline-status")).not.toBeInTheDocument();
    },
  );

  it.each(["initial", "switch"] as const)(
    "네트워크 오류(%s) → '서버에 연결할 수 없습니다 · 다시 시도', 제출 차단 → 다시 시도 성공",
    async (timing) => {
      const user = userEvent.setup();
      await injectMealError(user, timing, "network");

      expect(await screen.findByText("서버에 연결할 수 없습니다")).toBeInTheDocument();
      expect(baselineControls().submit).toBeDisabled();
      expect(baselineControls().album).toBeDisabled();

      server.resetHandlers();
      await user.click(screen.getByRole("button", { name: "다시 시도" }));
      await waitForPlan();
      expect(screen.queryByText("서버에 연결할 수 없습니다")).not.toBeInTheDocument();
    },
  );

  it("끼니를 바꾼 직후 새 조회가 끝나기 전에는 사진 입력·제출이 막히고, 끝나면 풀린다", async () => {
    const user = userEvent.setup();
    const { held } = holdMealRequests();
    renderRoute("/baseline");
    await waitFor(() => expect(held).toHaveLength(1));
    held[0]?.pass();
    await waitForPlan();
    expect(baselineControls().album).toBeEnabled();

    await user.click(baselineControls().meal("lunch"));

    await waitFor(() => expect(held).toHaveLength(2));
    expect(screen.queryByTestId("baseline-status")).not.toBeInTheDocument();
    expect(baselineControls().album).toBeDisabled();
    expect(baselineControls().submit).toBeDisabled();

    held[1]?.pass();
    await waitForPlan();
    expect(baselineControls().album).toBeEnabled();
  });
});

describe("화면 ① 업로드 오류", () => {
  useNodeFileForMultipart();
  useBaselineScreenEnv();

  it.each([
    ["404", "not_found", "대상을 찾을 수 없습니다. 목록을 새로 고칩니다"],
    ["413", "too_large", "사진이 너무 큽니다"],
    ["422", "invalid", "사진을 확인할 수 없습니다. 다른 사진을 골라 주세요"],
    ["네트워크 오류", "network", "서버에 연결할 수 없습니다. 다시 시도해 주세요"],
    ["409(계약 밖)", "conflict", "기준 사진을 올리지 못했습니다. 다시 시도해 주세요"],
    ["500", "server", "기준 사진을 올리지 못했습니다. 다시 시도해 주세요"],
  ] as const)("%s → 한국어 안내, 고른 사진 유지", async (_label, kind, message) => {
    const user = userEvent.setup();
    server.use(errorHandlers.baselineUpload(kind));
    const { requests } = recordApiRequests();
    renderRoute("/baseline");
    await waitForPlan();
    await pickPhoto(user);

    await user.click(baselineControls().submit);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("img", PREVIEW)).toBeInTheDocument();
    expect(baselineControls().submit).toBeEnabled();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    // 404만 그 끼니를 다시 읽는다
    const expectedGets = kind === "not_found" ? 2 : 1;
    await waitFor(() => expect(mealGets(requests)).toHaveLength(expectedGets));
  });

  it("요청이 없을 때 날짜·끼니를 바꾸면 고른 사진과 오류 메시지를 지운다", async () => {
    const user = userEvent.setup();
    server.use(errorHandlers.baselineUpload("too_large"));
    renderRoute("/baseline");
    await waitForPlan();
    await pickPhoto(user);
    await user.click(baselineControls().submit);
    expect(await screen.findByRole("alert")).toHaveTextContent("사진이 너무 큽니다");

    await user.click(baselineControls().meal("lunch"));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("img", PREVIEW)).not.toBeInTheDocument();

    await waitForPlan();
    await pickPhoto(user);
    await user.click(baselineControls().submit);
    await confirmResubmit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("사진이 너무 큽니다");

    fireEvent.change(baselineControls().date, { target: { value: "2026-11-28" } });

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("img", PREVIEW)).not.toBeInTheDocument();
    expect(await screen.findByText("이 날짜·끼니의 배식 계획이 없습니다")).toBeInTheDocument();
  });
});

describe("화면 ① 제출 성공 뒤 재조회 실패", () => {
  useNodeFileForMultipart();
  useBaselineScreenEnv();

  /** `fail`을 켜는 동안 끼니 조회를 네트워크 오류로 끝낸다(끄면 기본 핸들러로 넘긴다) */
  function failableMeals(): { fail: boolean } {
    const meals = { fail: false };
    server.use(
      http.get("/api/meals/:date/:meal", () => (meals.fail ? errorResponse("network") : undefined)),
    );
    return meals;
  }

  it("201 뒤 재조회 네트워크 오류 → 성공 안내 유지, 재제출 불가, 새로 고침 안내 → 다시 시도 성공 뒤 재제출 가능", async () => {
    const user = userEvent.setup();
    const meals = failableMeals();
    const { requests } = recordApiRequests();
    renderRoute("/baseline");
    await waitForPlan();
    await pickPhoto(user);

    meals.fail = true;
    await user.click(baselineControls().submit);

    expect(await screen.findByText("목록을 새로 고치지 못했습니다")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("기준 사진 등록됨");
    expect(screen.getByTestId("baseline-status")).toHaveTextContent("아직 없음");
    await pickPhoto(user, "again.jpg");
    expect(baselineControls().submit).toBeDisabled();

    // 다시 시도는 조회만 보낸다
    meals.fail = false;
    const postsBefore = postRequests(requests).length;
    await user.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitForBaselineStatus("등록됨 (");
    expect(postRequests(requests)).toHaveLength(postsBefore);
    expect(screen.queryByText("목록을 새로 고치지 못했습니다")).not.toBeInTheDocument();

    // 잠금이 풀리면 확인 시트를 거쳐 다시 올릴 수 있다
    expect(baselineControls().submit).toBeEnabled();
    await user.click(baselineControls().submit);
    await confirmResubmit(user);
    await waitFor(() =>
      expect(postRequests(requests)).toEqual([
        `POST ${baselinePath("dinner")}`,
        `POST ${baselinePath("dinner")}`,
      ]),
    );
  });

  it("성공 안내는 다른 끼니를 보는 동안 숨고, 그 끼니로 돌아오면(조회 실패여도) 다시 보인다", async () => {
    const user = userEvent.setup();
    const meals = failableMeals();
    renderRoute("/baseline");
    await waitForPlan();
    await pickPhoto(user);
    await user.click(baselineControls().submit);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("기준 사진 등록됨"));

    await user.click(baselineControls().meal("lunch"));
    await waitForPlan();
    expect(screen.getByRole("status")).toBeEmptyDOMElement();

    meals.fail = true;
    await user.click(baselineControls().meal("dinner"));

    expect(await screen.findByText("서버에 연결할 수 없습니다")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("기준 사진 등록됨");
  });
});
