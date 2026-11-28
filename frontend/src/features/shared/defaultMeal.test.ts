// 기본 끼니 시각 규칙(`docs/specs/frontend-shell-upload.md` '시연일 초기화': 10:30 전 아침, 15:30 전 점심, 그 뒤 저녁) 테스트.
import { BREAKFAST_END, LUNCH_END, defaultMeal } from "./defaultMeal";

/** 시연일의 로컬 시각 */
function at(hours: number, minutes: number): Date {
  return new Date(2026, 10, 27, hours, minutes);
}

describe("defaultMeal", () => {
  it("경계 시각 상수는 10:30과 15:30이다", () => {
    expect(BREAKFAST_END).toBe("10:30");
    expect(LUNCH_END).toBe("15:30");
  });

  it.each([
    ["00:00", at(0, 0), "breakfast"],
    ["10:29", at(10, 29), "breakfast"],
    ["10:30", at(10, 30), "lunch"],
    ["15:29", at(15, 29), "lunch"],
    ["15:30", at(15, 30), "dinner"],
    ["23:59", at(23, 59), "dinner"],
  ] as const)("%s → %s", (_label, now, expected) => {
    expect(defaultMeal(now)).toBe(expected);
  });

  it("초 단위는 경계 판정에 영향을 주지 않는다(10:29:59는 아침)", () => {
    expect(defaultMeal(new Date(2026, 10, 27, 10, 29, 59))).toBe("breakfast");
  });
});
