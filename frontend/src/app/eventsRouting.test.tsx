// 라우트 전환에 따른 SSE 연결 수명 테스트. 실제 라우트(AppRoutes)를 MemoryRouter로 그리고,
// 연결 함수는 모의 버스를 발행기로 쓰는 주입식 연결로 바꾼다(스펙 3.4절, 계획 T13.4).
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate, type NavigateFunction } from "react-router";

import { createMockConnect } from "../test/mockConnect";
import { AppRoutes } from "./routes";

function renderWithNavigator(path: string) {
  const mock = createMockConnect();
  let navigate: NavigateFunction | null = null;
  function Navigator() {
    navigate = useNavigate();
    return null;
  }
  render(
    <MemoryRouter initialEntries={[path]}>
      <Navigator />
      <AppRoutes connectEvents={mock.connect} />
    </MemoryRouter>,
  );
  const go = async (to: string) => {
    await act(async () => {
      await navigate?.(to);
    });
  };
  return { mock, go };
}

describe("화면 ①② 레이아웃의 SSE 연결", () => {
  it.each(["/baseline", "/post-meal"])("%s에 들어가면 연결을 한 번 연다", (path) => {
    const { mock } = renderWithNavigator(path);

    expect(mock.connect).toHaveBeenCalledTimes(1);
  });

  it.each(["/", "/camera-check"])("%s에 직접 들어가면 연결하지 않는다", (path) => {
    const { mock } = renderWithNavigator(path);

    expect(mock.connect).not.toHaveBeenCalled();
  });

  it("/baseline에서 /post-meal로 이동해도 연결을 유지한다", async () => {
    const { mock, go } = renderWithNavigator("/baseline");

    await go("/post-meal");

    expect(screen.getByRole("heading", { level: 1, name: "식후 사진" })).toBeInTheDocument();
    expect(mock.connect).toHaveBeenCalledTimes(1);
    expect(mock.closeCount()).toBe(0);
  });

  it("/post-meal에서 상단 링크로 /에 가면 연결을 한 번 닫고 새로 열지 않는다", async () => {
    const { mock } = renderWithNavigator("/post-meal");

    await userEvent.click(screen.getByRole("link", { name: "NutriSight" }));

    expect(screen.getByRole("link", { name: /요양보호사/ })).toBeInTheDocument();
    expect(mock.connections[0]?.close).toHaveBeenCalledTimes(1);
    expect(mock.connect).toHaveBeenCalledTimes(1);
  });

  it("/baseline에서 /camera-check로 가면 연결을 한 번 닫고 새로 열지 않는다", async () => {
    const { mock, go } = renderWithNavigator("/baseline");

    await go("/camera-check");

    expect(screen.getByRole("heading", { level: 1, name: "촬영 확인" })).toBeInTheDocument();
    expect(mock.connections[0]?.close).toHaveBeenCalledTimes(1);
    expect(mock.connect).toHaveBeenCalledTimes(1);
  });
});
