import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderRoute } from "../test/renderRoute";

describe("RoleSelect", () => {
  it("의사·처리 상태 항목은 비활성이고 '준비 중'을 보인다", () => {
    renderRoute("/");

    for (const name of [/의사/, /처리 상태/]) {
      const item = screen.getByRole("button", { name });
      expect(item).toBeDisabled();
      expect(item).toHaveTextContent("준비 중");
    }
  });

  it.each([
    [/영양사/, "/baseline", "기준 식전 사진"],
    [/요양보호사/, "/post-meal", "식후 사진"],
  ])("%s 링크는 %s로 이동한다", async (name, href, title) => {
    renderRoute("/");

    const link = screen.getByRole("link", { name });
    expect(link).toHaveAttribute("href", href);
    await userEvent.click(link);

    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
  });

  it("아래쪽 '촬영 확인' 링크는 /camera-check로 이동한다", async () => {
    renderRoute("/");

    await userEvent.click(screen.getByRole("link", { name: "촬영 확인" }));

    expect(screen.getByRole("heading", { level: 1, name: "촬영 확인" })).toBeInTheDocument();
  });
});
