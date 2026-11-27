import path from "node:path";

import { expect, type Locator, type Page } from "@playwright/test";

/** 합성 식판 이미지(단색 도형, 실제 사진 아님) */
export const TRAY_IMAGE = path.join(import.meta.dirname, "fixtures", "tray.jpg");

/** 터치 최소 크기(스펙 3.7절 `--touch-min`) */
const TOUCH_MIN_PX = 44;

/** 요소의 실제 크기가 가로·세로 모두 44px 이상인지 확인한다 */
export async function expectTouchTarget(locator: Locator): Promise<void> {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, "요소의 크기를 잴 수 없습니다").not.toBeNull();
  if (box === null) return;
  expect.soft(box.height, "터치 영역 높이").toBeGreaterThanOrEqual(TOUCH_MIN_PX);
  expect.soft(box.width, "터치 영역 너비").toBeGreaterThanOrEqual(TOUCH_MIN_PX);
}

/** 화면에 들어간 뒤 모의 전역이 생기기를 기다려 모의 상태를 초기값으로 되돌린다 */
export async function openWithFreshMock(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await page.waitForFunction(() => window.__nutrisightMock !== undefined);
  await page.evaluate(() => window.__nutrisightMock?.reset());
}
