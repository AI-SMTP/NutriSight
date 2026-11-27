// 주소 하나에서 앱 라우트 전체를 그린다(브라우저 주소 대신 MemoryRouter).
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { AppRoutes } from "../app/routes";

export function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}
