import { render, screen } from "@testing-library/react";

import { Badge } from "./Badge";

describe("Badge", () => {
  it("문구와 tone을 보여 준다", () => {
    render(<Badge tone="neutral">금식</Badge>);

    expect(screen.getByText("금식")).toHaveAttribute("data-tone", "neutral");
  });

  it.each(["neutral", "primary", "danger", "accent"] as const)("tone %s를 받는다", (tone) => {
    render(<Badge tone={tone}>상태</Badge>);

    expect(screen.getByText("상태")).toHaveAttribute("data-tone", tone);
  });

  it("tone을 주지 않으면 primary다", () => {
    render(<Badge>영양사</Badge>);

    expect(screen.getByText("영양사")).toHaveAttribute("data-tone", "primary");
  });
});
