import { expect, test } from "@playwright/test";

import { expectTouchTarget, openWithFreshMock, TRAY_IMAGE } from "./helpers";

// 화면 ② 식후 사진: 시연일 점심 미기록 환자(NS03)에 식후 사진을 올리고 처리 완료까지 확인한다.
test("화면 ②: 점심 NS03 식후 사진을 올리면 처리 중을 거쳐 완료가 된다", async ({ page }) => {
  await openWithFreshMock(page, "/post-meal");

  // 끼니 시각 규칙에 기대지 않고 명시적으로 고른다
  const mealOptions = ["오늘 아침", "오늘 점심", "오늘 저녁"].map((label) =>
    page.getByRole("radio", { name: label, exact: true }),
  );
  await page.getByRole("radio", { name: "오늘 점심", exact: true }).check();

  const orders = page.getByRole("list", { name: "업로드 현황" });
  const ns03 = orders.getByRole("button", { name: /NS03/ });
  await expect(ns03).toContainText("미기록");

  // 터치 영역(업로드 전): 끼니 3개, 고를 수 있는 환자 항목 전부, 사진 입력 라벨 2개, 업로드 버튼, 전량 기록 버튼 2개
  for (const option of mealOptions) await expectTouchTarget(option);
  const selectable = orders.getByRole("button").and(page.locator(":enabled"));
  const selectableCount = await selectable.count();
  expect(selectableCount).toBeGreaterThan(0);
  for (let index = 0; index < selectableCount; index += 1) {
    await expectTouchTarget(selectable.nth(index));
  }
  await expectTouchTarget(page.locator("label", { hasText: "촬영하기" }));
  await expectTouchTarget(page.locator("label", { hasText: "앨범에서 선택" }));
  await expectTouchTarget(page.getByRole("button", { name: /식후 사진 업로드$/ }));
  const refuseButton = page.getByRole("button", { name: "전량 거부", exact: true });
  await expectTouchTarget(refuseButton);
  await expectTouchTarget(page.getByRole("button", { name: "전량 미섭취", exact: true }));

  // 터치 영역(확인 시트): 미기록 환자를 고르고 시트를 연 뒤 취소로 닫는다. 기록되지 않아야 한다
  await ns03.click();
  await expect(ns03).toHaveAttribute("aria-pressed", "true");
  await refuseButton.click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toContainText("NS03 점심을 전량 거부로 기록합니다");
  const cancelButton = sheet.getByRole("button", { name: "취소", exact: true });
  await expectTouchTarget(cancelButton);
  await expectTouchTarget(sheet.getByRole("button", { name: "기록하기", exact: true }));
  await cancelButton.click();
  await expect(sheet).toBeHidden();
  await expect(ns03).toContainText("미기록");

  // 업로드 → 처리 중(수동 단계에서 멈춤) → finishAll() → 완료
  await page.getByLabel("앨범에서 선택").setInputFiles(TRAY_IMAGE);
  const uploadButton = page.getByRole("button", { name: "NS03 식후 사진 업로드" });
  await expect(uploadButton).toBeEnabled();
  await uploadButton.click();
  await expect(
    page.getByRole("status").filter({ hasText: "NS03 식후 사진을 올렸습니다" }),
  ).toBeVisible();
  await expect(ns03).toContainText("처리 중");

  // finishAll()은 uploaded·queued·analyzing 어느 시점에 불러도 남은 단계를 끝낸다(계획 Story 10 계약)
  await page.evaluate(() => window.__nutrisightMock?.finishAll());
  await expect(ns03).toContainText("완료");
});
