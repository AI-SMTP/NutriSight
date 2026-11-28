// 주소 하나에서 앱 라우트 전체를 그린다(브라우저 주소 대신 MemoryRouter).
// jsdom에는 EventSource가 없으므로 화면 ①② 레이아웃의 SSE 연결은 모의 버스 연결로 바꾼다.
// SSE `open` 시점을 테스트가 정해야 하면 `createMockConnect()`의 연결 함수를 넘긴다.
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import type { ConnectSystemEvents } from "../api/events";
import { AppRoutes } from "../app/routes";
import { createMockConnect } from "./mockConnect";

export function renderRoute(
  path: string,
  connectEvents: ConnectSystemEvents = createMockConnect().connect,
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes connectEvents={connectEvents} />
    </MemoryRouter>,
  );
}
