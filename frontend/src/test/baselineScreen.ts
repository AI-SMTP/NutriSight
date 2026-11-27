// 화면 ① 기준 식전 사진 테스트 도우미. 화면 ①② 공통 부분(시계·사진 입력·경로)은 `mealScreen.ts`에 있고,
// 기존 테스트가 그대로 쓰도록 여기서 다시 내보낸다.
import { screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

import type { Meal } from "../api/provisional";
import { DEMO_DATE } from "../mocks/fixtures";
import { MEAL_LABELS, expectMealControlsDisabled, mealPath, useMealScreenEnv } from "./mealScreen";

export {
  MEAL_LABELS,
  PREVIEW,
  localTime,
  mealGets,
  mealPath,
  pickPhoto,
  postRequests,
} from "./mealScreen";

/** 화면 ① 테스트 환경(시계 고정·object URL 대역). 공용 `useMealScreenEnv`와 같다 */
export const useBaselineScreenEnv = useMealScreenEnv;

/** 기준 사진 업로드 경로 */
export function baselinePath(meal: Meal, date = DEMO_DATE): string {
  return `${mealPath(meal, date)}/baseline`;
}

/** 끼니 조회가 반영돼 등록 상태 표시가 보일 때까지 기다린다 */
export async function waitForPlan(): Promise<HTMLElement> {
  return screen.findByTestId("baseline-status");
}

/** 등록 상태 표시가 `expected`가 될 때까지 기다린다 */
export async function waitForBaselineStatus(expected: string | RegExp): Promise<void> {
  await waitFor(() => expect(screen.getByTestId("baseline-status")).toHaveTextContent(expected));
}

/** 화면 ①의 입력 요소들 */
export function baselineControls() {
  return {
    date: screen.getByLabelText<HTMLInputElement>("날짜"),
    meal: (meal: Meal) => screen.getByLabelText<HTMLInputElement>(MEAL_LABELS[meal]),
    camera: screen.getByLabelText<HTMLInputElement>("촬영하기"),
    album: screen.getByLabelText<HTMLInputElement>("앨범에서 선택"),
    submit: screen.getByRole("button", { name: "기준 사진 업로드" }),
  };
}

/** 날짜·끼니·사진 입력·제출이 모두 막혀 있다 */
export function expectAllInputsDisabled(): void {
  const controls = baselineControls();
  expect(controls.date).toBeDisabled();
  expectMealControlsDisabled(controls);
}

/** 열린 재업로드 확인 시트에서 "다시 올리기"를 누른다 */
export async function confirmResubmit(user: UserEvent): Promise<void> {
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "다시 올리기" }));
}
