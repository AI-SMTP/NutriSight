// 화면 ② 식후 사진 테스트 도우미. 공통 부분(시계·사진 입력·경로)은 `mealScreen.ts`에 있다.
// 환자 항목은 "업로드 현황" 목록 안의 버튼이고, 이름은 "<room> · <display_name> <배지>"다.
import { screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

import type { Meal, StaffZeroReason } from "../api/provisional";
import { MEAL_LABELS, expectMealControlsDisabled } from "./mealScreen";

/** 환자 목록(업로드 현황)을 찾는 조건 */
const PATIENT_LIST = ["list", { name: "업로드 현황" }] as const;

/** 끼니 선택지 라벨("오늘 점심" 등) */
function postMealLabel(meal: Meal): string {
  return `오늘 ${MEAL_LABELS[meal]}`;
}

/** 환자 목록(업로드 현황) */
export function patientList(): HTMLElement {
  return screen.getByRole(...PATIENT_LIST);
}

/** 환자 목록이 반영될 때까지 기다린다 */
export async function waitForOrders(): Promise<HTMLElement> {
  return screen.findByRole(...PATIENT_LIST);
}

/** 화면에 보이는 환자 항목(목록이 없으면 빈 배열) */
function patientItems(): HTMLElement[] {
  const list = screen.queryByRole(...PATIENT_LIST);
  return list === null ? [] : within(list).queryAllByRole("button");
}

/** 환자 항목(버튼). `name`은 `display_name` */
export function patientItem(name: string): HTMLElement {
  return within(patientList()).getByRole("button", { name: new RegExp(` · ${name} `) });
}

/** 화면에 보이는 환자 항목 수(목록이 없으면 0) */
export function patientItemCount(): number {
  return patientItems().length;
}

/** 환자 항목의 배지 요소 */
export function badgeOf(name: string): HTMLElement {
  const badge = patientItem(name).querySelector<HTMLElement>("[data-tone]");
  if (badge === null) throw new Error(`${name} 항목에 배지가 없다`);
  return badge;
}

/** 환자 항목의 배지가 `expected`가 될 때까지 기다린다 */
export async function waitForBadge(name: string, expected: string): Promise<void> {
  await waitFor(() => expect(badgeOf(name)).toHaveTextContent(new RegExp(`^${expected}$`)));
}

/** 현황 머리글 */
export function orderSummary(): HTMLElement {
  return screen.getByTestId("order-summary");
}

/** 화면의 `role="status"` 영역 중 `testId`가 맞는(또는 `testId`가 없는) 것 */
function statusRegion(match: (testId: string | undefined) => boolean): HTMLElement {
  const found = screen.getAllByRole("status").find((el) => match(el.dataset.testid));
  if (found === undefined) throw new Error("맞는 status 영역이 없다");
  return found;
}

/** 기준 사진 안내(갱신되면 읽히도록 `role="status"` 영역이다) */
export function baselineGuide(): HTMLElement {
  return statusRegion((id) => id === "baseline-guide");
}

/** 제출 성공 안내 영역 */
export function submitNotice(): HTMLElement {
  return statusRegion((id) => id !== "baseline-guide");
}

/** 업로드 버튼(환자를 고르면 "<display_name> 식후 사진 업로드") */
function uploadButton(): HTMLElement {
  return screen.getByRole("button", { name: /식후 사진 업로드$/ });
}

/** 화면 ②의 입력 요소들 */
export function postMealControls() {
  return {
    meal: (meal: Meal) => screen.getByLabelText<HTMLInputElement>(postMealLabel(meal)),
    camera: screen.getByLabelText<HTMLInputElement>("촬영하기"),
    album: screen.getByLabelText<HTMLInputElement>("앨범에서 선택"),
    submit: uploadButton(),
  };
}

/** 끼니·사진 입력·업로드가 모두 막혀 있고 고를 수 있는 환자 항목이 없다 */
export function expectAllPostMealInputsDisabled(): void {
  expectMealControlsDisabled(postMealControls());
  expect(patientItems().filter((b) => !b.hasAttribute("disabled"))).toEqual([]);
}

/** 기본 안내 문구 */
export const POST_MEAL_TEXT = {
  notRecordable: "이미 기록 중이거나 기록된 끼니입니다",
  conflict:
    "이 끼니는 지금 기록할 수 없습니다(식사가 나가지 않거나 이미 기록 중·기록됨). 목록을 확인하세요",
  baselineReady: "기준 사진 등록됨",
  baselineMissing: "기준 사진이 아직 없어요. 지금 올려도 기준 사진이 등록되면 자동으로 분석해요.",
} as const;

/** 전량 기록 버튼 이름 */
export const STAFF_ZERO_LABELS: Readonly<Record<StaffZeroReason, string>> = {
  refused: "전량 거부",
  not_eaten: "전량 미섭취",
};

/** "사진 없이 기록" 묶음(전량 기록 버튼과 그 실패 안내가 있다) */
export function staffZeroGroup(): HTMLElement {
  return screen.getByRole("group", { name: "사진 없이 기록" });
}

/** 전량 기록 버튼("사진 없이 기록" 묶음 안) */
export function staffZeroButton(reason: StaffZeroReason): HTMLElement {
  return within(staffZeroGroup()).getByRole("button", { name: STAFF_ZERO_LABELS[reason] });
}

/** 두 전량 기록 버튼이 모두 막혔는지 */
export function expectStaffZeroDisabled(): void {
  expect(staffZeroButton("refused")).toBeDisabled();
  expect(staffZeroButton("not_eaten")).toBeDisabled();
}

/** 두 전량 기록 버튼이 모두 열렸는지 */
export function expectStaffZeroEnabled(): void {
  expect(staffZeroButton("refused")).toBeEnabled();
  expect(staffZeroButton("not_eaten")).toBeEnabled();
}

/** 열린 확인 시트 */
export function confirmSheet(): HTMLElement {
  return screen.getByRole("dialog");
}

/** 열린 확인 시트에서 "기록하기"를 누른다 */
export async function confirmStaffZero(user: UserEvent): Promise<void> {
  await user.click(within(confirmSheet()).getByRole("button", { name: "기록하기" }));
}

/** 전량 기록 문구 */
export const STAFF_ZERO_TEXT = {
  sheetTitle: "사진 없이 기록할까요?",
  failed: "전량 기록을 하지 못했습니다. 다시 시도해 주세요",
} as const;
