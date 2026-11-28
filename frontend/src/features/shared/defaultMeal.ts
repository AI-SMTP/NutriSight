/**
 * 기본 끼니 시각 규칙(`docs/specs/frontend-shell-upload.md` '시연일 초기화', 화면 ①②가 같다).
 * 10:30 전은 아침, 15:30 전은 점심, 그 뒤는 저녁이다. 시각은 기기의 로컬 시각으로 본다.
 */
import type { Meal } from "../../api/provisional";

/** 아침이 끝나는 시각(이 시각부터 점심) */
export const BREAKFAST_END = "10:30";
/** 점심이 끝나는 시각(이 시각부터 저녁) */
export const LUNCH_END = "15:30";

/** `HH:MM`을 자정부터의 분으로 바꾼다 */
function toMinutes(hhmm: string): number {
  const [hours = 0, minutes = 0] = hhmm.split(":").map(Number);
  return hours * 60 + minutes;
}

const BREAKFAST_END_MINUTES = toMinutes(BREAKFAST_END);
const LUNCH_END_MINUTES = toMinutes(LUNCH_END);

/** 지금 시각의 기본 끼니 */
export function defaultMeal(now: Date): Meal {
  const minutes = now.getHours() * 60 + now.getMinutes();
  if (minutes < BREAKFAST_END_MINUTES) return "breakfast";
  if (minutes < LUNCH_END_MINUTES) return "lunch";
  return "dinner";
}
