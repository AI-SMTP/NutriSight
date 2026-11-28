// 식판 배치 표 테스트: 미배식 칸(`menu_name = null`)과 응답에 없는 칸 처리.
import { render, screen, within } from "@testing-library/react";

import type { Slot } from "../../api/provisional";
import { TrayLayout } from "./TrayLayout";

function slot(n: number, menu_name: string | null, served_g: number): Slot {
  return {
    slot_id: `slot_${n}`,
    position: `칸 ${n}`,
    dish_type: "side",
    menu_name,
    served_g,
    energy_kcal: 0,
    protein_g: 0,
  };
}

function rowTexts(name: string): string[] {
  return within(screen.getByRole("list", { name }))
    .queryAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

describe("TrayLayout", () => {
  it("미배식 칸은 배식량 없이 '미배식'만 보인다", () => {
    render(<TrayLayout slots={[slot(1, "쌀밥", 210), slot(2, null, 0)]} />);

    expect(rowTexts("아랫줄")).toEqual(["쌀밥210g", "미배식"]);
  });

  it("응답에 없는 칸은 건너뛰고, 받은 칸은 식판 배치 순서로 놓는다", () => {
    render(<TrayLayout slots={[slot(6, "김치", 40), slot(3, "불고기", 90)]} />);

    expect(rowTexts("윗줄")).toEqual(["불고기90g", "김치40g"]);
    expect(rowTexts("아랫줄")).toEqual([]);
  });
});
