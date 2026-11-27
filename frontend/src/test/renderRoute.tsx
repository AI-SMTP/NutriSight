// 주소 하나에서 앱 라우트 전체를 그린다(브라우저 주소 대신 MemoryRouter).
// jsdom에는 EventSource가 없으므로 화면 ①② 레이아웃의 SSE 연결은 모의 버스 연결로 바꾼다.
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { AppRoutes } from "../app/routes";
import { createMockConnect } from "./mockConnect";

export function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes connectEvents={createMockConnect().connect} />
    </MemoryRouter>,
  );
}
