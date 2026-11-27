// 화면 ① 기준 식전 사진 테스트 공용 도우미.
// - 시계: Date만 가짜로 바꿔 기본 끼니와 모의 등록 시각을 고정한다(타이머는 진짜라 waitFor·MSW가 그대로 돈다).
// - 사진 입력: PhotoPicker의 미리보기용 object URL 대역을 붙인다.
// - multipart: 업로드를 보내는 묶음은 `useNodeFileForMultipart()`로 전역 `File`을 Node 것으로 바꾼다.
//   그런데 화면의 `FormData.append`(jsdom)는 jsdom `Blob`만 받으므로, 사진 자체는 바꾸기 전의 jsdom `File`로
//   만들어야 한다. 그래서 이 모듈을 불러올 때(각 테스트의 beforeEach보다 먼저) jsdom `File`을 잡아 둔다.
//   이 조합이면 `<input type="file">`·user-event `upload`(jsdom `File`)와 multipart 전송이 함께 동작한다.
import { screen, waitFor, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

import type { Meal } from "../api/provisional";
import { DEMO_DATE } from "../mocks/fixtures";
import { stubObjectUrl } from "./objectUrl";

/** 모듈을 불러온 시점의 전역 `File`(jsdom). `useNodeFileForMultipart()`가 바꾸기 전 값이다 */
const JsdomFile = globalThis.File;

/** 고른 사진 미리보기 이미지의 이름 조건 */
export const PREVIEW = { name: "선택한 사진 미리보기" } as const;

/** 끼니 선택지 라벨 */
export const MEAL_LABELS: Readonly<Record<Meal, string>> = {
  breakfast: "아침",
  lunch: "점심",
  dinner: "저녁",
};

/** 끼니 조회 경로 */
export function mealPath(meal: Meal, date = DEMO_DATE): string {
  return `/api/meals/${date}/${meal}`;
}

/** 기준 사진 업로드 경로 */
export function baselinePath(meal: Meal, date = DEMO_DATE): string {
  return `${mealPath(meal, date)}/baseline`;
}

/** 로컬 시각(시연일 2026-11-27의 HH:MM) */
export function localTime(hours: number, minutes: number): Date {
  return new Date(2026, 10, 27, hours, minutes);
}

/**
 * 각 테스트 동안 Date를 `at`(로컬 시각)으로 고정하고 object URL 대역을 붙인다.
 * 기본값 17:20은 기본 끼니가 저녁(기준 사진 없음)이 되는 시각이다.
 */
export function useBaselineScreenEnv(at: () => Date = () => localTime(17, 20)): void {
  let urls: ReturnType<typeof stubObjectUrl> | null = null;
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(at());
    urls = stubObjectUrl();
  });
  afterEach(() => {
    urls?.restore();
    vi.useRealTimers();
  });
}

/** 끼니 조회가 반영돼 등록 상태 표시가 보일 때까지 기다린다 */
export async function waitForPlan(): Promise<HTMLElement> {
  return screen.findByTestId("baseline-status");
}

/** 등록 상태 표시가 `expected`가 될 때까지 기다린다 */
export async function waitForBaselineStatus(expected: string | RegExp): Promise<void> {
  await waitFor(() => expect(screen.getByTestId("baseline-status")).toHaveTextContent(expected));
}

/** "앨범에서 선택"으로 jsdom `File` 사진 하나를 고른다(전역 `File`이 Node 것으로 바뀐 묶음에서도) */
export async function pickPhoto(user: UserEvent, name = "tray.jpg"): Promise<File> {
  const photo = new JsdomFile([new Uint8Array(2048)], name, { type: "image/jpeg" });
  await user.upload(screen.getByLabelText("앨범에서 선택"), photo);
  return photo;
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
  for (const meal of Object.keys(MEAL_LABELS) as Meal[]) {
    expect(controls.meal(meal)).toBeDisabled();
  }
  expect(controls.camera).toBeDisabled();
  expect(controls.album).toBeDisabled();
  expect(controls.submit).toBeDisabled();
}

/** 열린 재업로드 확인 시트에서 "다시 올리기"를 누른다 */
export async function confirmResubmit(user: UserEvent): Promise<void> {
  await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "다시 올리기" }));
}

/** 기록된 요청 중 POST만 */
export function postRequests(requests: readonly string[]): string[] {
  return requests.filter((r) => r.startsWith("POST"));
}
