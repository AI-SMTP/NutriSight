// 화면 ① 제출 중 이탈 테스트(스펙 3.5절 "요청이 끝나기 전에 화면을 떠나면 응답은 화면 상태에 반영하지 않는다").
//
// 이탈 뒤 늦은 응답의 처리를 관찰하는 방법: 화면의 업로드 콜백은 성공(`onSuccess`)이면 그 끼니를 다시 읽고,
// 404 실패(`onError`)여도 다시 읽는다. 두 경우 모두 `getMeal` 호출로 이어지므로, `getMeal`을 실제 함수를
// 부르는 스파이로 감싸 "이탈 뒤 늦은 응답이 와도 `getMeal`이 더 불리지 않는다"를 단언한다.
// (취소 신호가 걸린 조회는 네트워크로 나가지 않아 MSW 요청 기록으로는 볼 수 없다.)
// 요청 번호표의 단위 방어는 `features/shared/useSubmission.test.tsx`가 맡는다.
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { getMeal } from "../../api/provisional";
import { errorResponse } from "../../mocks/errorHandlers";
import { server } from "../../mocks/server";
import {
  PREVIEW,
  baselineControls,
  pickPhoto,
  useBaselineScreenEnv,
  waitForPlan,
} from "../../test/baselineScreen";
import { deferred } from "../../test/deferred";
import { useNodeFileForMultipart } from "../../test/nodeFile";
import { renderRoute } from "../../test/renderRoute";

vi.mock("../../api/provisional", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/provisional")>();
  return { ...actual, getMeal: vi.fn(actual.getMeal) };
});

describe("화면 ① 제출 중 이탈", () => {
  useNodeFileForMultipart();
  useBaselineScreenEnv();

  let consoleError: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    vi.mocked(getMeal).mockClear();
    consoleError = vi.spyOn(console, "error");
  });
  afterEach(() => {
    consoleError.mockRestore();
  });

  /** 업로드 응답을 붙잡아 두는 핸들러. `arrived`는 요청이 도착했을 때, `gate`를 풀면 응답한다 */
  function holdUpload(late: "success" | "not_found") {
    const gate = deferred<void>();
    const arrived = deferred<void>();
    server.use(
      http.post("/api/meals/:date/:meal/baseline", async () => {
        arrived.resolve();
        await gate.promise;
        return late === "success"
          ? HttpResponse.json(
              { photo_id: "late", uploaded_at: new Date().toISOString() },
              { status: 201 },
            )
          : errorResponse("not_found");
      }),
    );
    return { gate, arrived };
  }

  it.each([
    ["성공(201)", "success"],
    ["실패(404)", "not_found"],
  ] as const)(
    "업로드 응답을 지연시킨 채 '/'로 이동하면 늦은 %s 응답을 반영하지 않는다",
    async (_l, late) => {
      const user = userEvent.setup();
      const { gate, arrived } = holdUpload(late);
      renderRoute("/baseline");
      await waitForPlan();
      await pickPhoto(user);
      await user.click(baselineControls().submit);
      await arrived.promise;

      await user.click(screen.getByRole("link", { name: "NutriSight" }));
      expect(screen.getByRole("heading", { name: "역할 선택" })).toBeInTheDocument();
      const callsBeforeLateResponse = vi.mocked(getMeal).mock.calls.length;
      await act(async () => {
        gate.resolve();
        await new Promise((resolve) => setTimeout(resolve, 20));
      });

      // 늦은 응답의 성공·실패 콜백(둘 다 재조회를 부른다)이 불리지 않았다
      expect(vi.mocked(getMeal).mock.calls.length).toBe(callsBeforeLateResponse);
      expect(consoleError).not.toHaveBeenCalled();

      // 다시 들어와도 이전 요청의 안내·오류·사진이 남지 않는다
      await user.click(screen.getByRole("link", { name: /영양사/ }));
      await waitForPlan();
      expect(screen.getByRole("status")).toBeEmptyDOMElement();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.queryByRole("img", PREVIEW)).not.toBeInTheDocument();
    },
  );
});
