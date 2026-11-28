import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Button } from "./Button";

describe("Button", () => {
  it("기본은 type=button이고 누르면 onClick을 부른다", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>업로드</Button>);

    const button = screen.getByRole("button", { name: "업로드" });
    expect(button).toHaveAttribute("type", "button");
    await userEvent.click(button);

    expect(onClick).toHaveBeenCalledOnce();
  });

  it("비활성이면 누를 수 없고 onClick을 부르지 않는다", async () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled>
        업로드
      </Button>,
    );

    const button = screen.getByRole("button", { name: "업로드" });
    expect(button).toBeDisabled();
    await userEvent.click(button);

    expect(onClick).not.toHaveBeenCalled();
  });

  it.each(["primary", "secondary", "danger"] as const)(
    "variant %s를 data-variant로 남긴다",
    (variant) => {
      render(<Button variant={variant}>확인</Button>);

      expect(screen.getByRole("button", { name: "확인" })).toHaveAttribute("data-variant", variant);
    },
  );

  it("variant를 주지 않으면 primary다", () => {
    render(<Button>확인</Button>);

    expect(screen.getByRole("button", { name: "확인" })).toHaveAttribute("data-variant", "primary");
  });

  it("type=submit을 넘길 수 있다", () => {
    render(<Button type="submit">보내기</Button>);

    expect(screen.getByRole("button", { name: "보내기" })).toHaveAttribute("type", "submit");
  });
});
