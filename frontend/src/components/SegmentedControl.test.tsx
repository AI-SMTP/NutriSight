import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SegmentedControl } from "./SegmentedControl";

const MEALS = [
  { value: "breakfast", label: "아침" },
  { value: "lunch", label: "점심" },
  { value: "dinner", label: "저녁" },
] as const;

type Meal = (typeof MEALS)[number]["value"];

function renderMeals(props: { value?: Meal; disabled?: boolean; onChange?: (v: Meal) => void }) {
  const onChange = props.onChange ?? vi.fn();
  render(
    <SegmentedControl
      legend="끼니"
      name="meal"
      options={MEALS}
      value={props.value ?? "lunch"}
      onChange={onChange}
      disabled={props.disabled}
    />,
  );
  return onChange;
}

describe("SegmentedControl", () => {
  it("묶음 이름과 모든 선택지를 라벨로 찾을 수 있다", () => {
    renderMeals({});

    expect(screen.getByRole("group", { name: "끼니" })).toBeInTheDocument();
    for (const { label } of MEALS) {
      expect(screen.getByLabelText(label)).toHaveAttribute("type", "radio");
    }
  });

  it("현재 값을 선택 상태로 보여 준다", () => {
    renderMeals({ value: "dinner" });

    expect(screen.getByLabelText("저녁")).toBeChecked();
    expect(screen.getByLabelText("아침")).not.toBeChecked();
  });

  it("다른 선택지를 누르면 그 값으로 onChange를 부른다", async () => {
    const onChange = renderMeals({ value: "lunch" });

    await userEvent.click(screen.getByLabelText("아침"));

    expect(onChange).toHaveBeenCalledWith("breakfast");
  });

  it("비활성이면 모든 선택지가 막히고 onChange를 부르지 않는다", async () => {
    const onChange = renderMeals({ disabled: true });

    for (const { label } of MEALS) {
      expect(screen.getByLabelText(label)).toBeDisabled();
    }
    await userEvent.click(screen.getByLabelText("아침"));

    expect(onChange).not.toHaveBeenCalled();
  });
});
