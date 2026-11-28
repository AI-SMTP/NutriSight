// 끼니 선택지(화면 ①② 공통). 화면 ②는 시연일 세 끼만 고르므로 "오늘 " 접두어를 붙인다
// (`docs/specs/frontend-shell-upload.md` '식후 사진 화면').
import type { Meal } from "../../api/provisional";
import type { SegmentOption } from "../../components/SegmentedControl";

/** 끼니 이름 */
export const MEAL_LABELS: Readonly<Record<Meal, string>> = {
  breakfast: "아침",
  lunch: "점심",
  dinner: "저녁",
};

const MEALS: readonly Meal[] = ["breakfast", "lunch", "dinner"];

/** 분할 버튼 선택지. `prefix`는 라벨 앞에 붙는다(예: "오늘 ") */
export function mealOptions(prefix = ""): readonly SegmentOption<Meal>[] {
  return MEALS.map((value) => ({ value, label: `${prefix}${MEAL_LABELS[value]}` }));
}
