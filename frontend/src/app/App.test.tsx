import { render, screen } from "@testing-library/react";

import { renderRoute } from "../test/renderRoute";
import { App } from "./App";

describe("App", () => {
  it("브라우저 주소 /에서 서비스 이름과 역할 선택 화면을 보여 준다", () => {
    render(<App />);

    expect(screen.getByRole("link", { name: "NutriSight" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("heading", { level: 1, name: "역할 선택" })).toBeInTheDocument();
  });
});

describe("AppRoutes", () => {
  it.each([
    ["/", "역할 선택", null],
    ["/baseline", "기준 식전 사진", "영양사"],
    ["/post-meal", "식후 사진", "요양보호사"],
    ["/camera-check", "촬영 확인", null],
    // 라우터는 끝 `/`와 대소문자를 무시하므로 상단 표시도 같은 화면으로 찾는다.
    ["/baseline/", "기준 식전 사진", "영양사"],
    ["/Post-Meal", "식후 사진", "요양보호사"],
    ["/camera-check/", "촬영 확인", null],
  ])("%s는 제목 %s와 역할 배지 %s를 상단에 보여 준다", (path, title, role) => {
    renderRoute(path);

    const header = screen.getByRole("banner");
    expect(header).toHaveTextContent("NutriSight");
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
    const badge = header.querySelector("[data-tone]");
    if (role === null) {
      expect(badge).toBeNull();
    } else {
      expect(badge).toHaveTextContent(role);
    }
  });

  it("/post-meal은 식후 사진 화면이다", async () => {
    renderRoute("/post-meal");

    expect(screen.getByRole("button", { name: /식후 사진 업로드$/ })).toBeInTheDocument();
    expect(await screen.findByRole("list", { name: "업로드 현황" })).toBeInTheDocument();
    expect(screen.queryByText("화면을 준비하고 있습니다")).not.toBeInTheDocument();
  });

  it("/baseline은 기준 식전 사진 화면이다", async () => {
    renderRoute("/baseline");

    expect(screen.getByRole("button", { name: "기준 사진 업로드" })).toBeInTheDocument();
    expect(await screen.findByTestId("baseline-status")).toBeInTheDocument();
  });

  it("모르는 경로는 역할 선택으로 보낸다", () => {
    renderRoute("/nowhere");

    expect(screen.getByRole("heading", { level: 1, name: "역할 선택" })).toBeInTheDocument();
  });
});
