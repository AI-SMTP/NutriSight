import type { Slot } from "../../api/provisional";
import styles from "./TrayLayout.module.css";

/** 식판 배치(`docs/specs/frontend-shell-upload.md` '기준 사진 화면' 2번): 윗줄 칸 3~6, 아랫줄 칸 1~2 */
const ROWS: readonly { label: string; slotIds: readonly string[] }[] = [
  { label: "윗줄", slotIds: ["slot_3", "slot_4", "slot_5", "slot_6"] },
  { label: "아랫줄", slotIds: ["slot_1", "slot_2"] },
];

/** 미배식 칸(`menu_name = null`, `served_g = 0`) 표시. 배식량은 보이지 않는다. 오늘 끼니에는 없지만 계약상 올 수 있다 */
const NOT_SERVED = "미배식";

export type TrayLayoutProps = {
  slots: readonly Slot[];
};

/** 배식 계획 6칸을 식판 배치대로 메뉴명·배식량과 함께 보여 준다. 없는 칸은 건너뛴다 */
export function TrayLayout({ slots }: TrayLayoutProps) {
  const byId = new Map(slots.map((slot) => [slot.slot_id, slot]));
  return (
    <div className={styles.tray}>
      {ROWS.map(({ label, slotIds }) => (
        <ul key={label} className={styles.row} aria-label={label}>
          {slotIds
            .flatMap((id) => byId.get(id) ?? [])
            .map((slot) => (
              <li key={slot.slot_id} className={styles.cell}>
                <span className={styles.menu}>{slot.menu_name ?? NOT_SERVED}</span>
                {slot.menu_name !== null && <span className={styles.amount}>{slot.served_g}g</span>}
              </li>
            ))}
        </ul>
      ))}
    </div>
  );
}
