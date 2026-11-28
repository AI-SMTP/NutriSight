import { expect, test } from "@playwright/test";

import { expectTouchTarget, openWithFreshMock, TRAY_IMAGE } from "./helpers";

// 화면 ① 기준 식전 사진: 시연일 저녁(기준 사진 없음)에 기준 사진을 올리고 등록 상태를 확인한다.
test("화면 ①: 날짜·끼니를 고르고 기준 사진을 올리면 등록됨으로 바뀐다", async ({ page }) => {
  await openWithFreshMock(page, "/baseline");

  // 시연일 기본값과 끼니 시각 규칙에 기대지 않고 명시적으로 고른다
  const dateInput = page.getByLabel("날짜");
  await dateInput.fill("2026-11-27");
  const mealOptions = ["아침", "점심", "저녁"].map((label) =>
    page.getByRole("radio", { name: label, exact: true }),
  );
  await page.getByRole("radio", { name: "저녁", exact: true }).check();

  // 배식 계획 6칸(윗줄 4 + 아랫줄 2)과 등록 상태
  const topRow = page.getByRole("list", { name: "윗줄" }).getByRole("listitem");
  const bottomRow = page.getByRole("list", { name: "아랫줄" }).getByRole("listitem");
  await expect(topRow).toHaveCount(4);
  await expect(bottomRow).toHaveCount(2);
  const baselineStatus = page.getByTestId("baseline-status");
  await expect(baselineStatus).toHaveText("아직 없음");

  // 터치 영역: 날짜, 끼니 3개, 사진 입력 라벨 2개, 업로드 버튼
  const uploadButton = page.getByRole("button", { name: "기준 사진 업로드" });
  await expectTouchTarget(dateInput);
  for (const option of mealOptions) await expectTouchTarget(option);
  await expectTouchTarget(page.locator("label", { hasText: "촬영하기" }));
  await expectTouchTarget(page.locator("label", { hasText: "앨범에서 선택" }));
  await expectTouchTarget(uploadButton);

  await page.getByLabel("앨범에서 선택").setInputFiles(TRAY_IMAGE);
  await expect(uploadButton).toBeEnabled();
  await uploadButton.click();

  await expect(page.getByRole("status")).toContainText("기준 사진 등록됨");
  await expect(baselineStatus).toHaveText(/^등록됨 \(/);
});
