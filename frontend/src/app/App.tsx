import { BrowserRouter } from "react-router";

import { AppRoutes } from "./routes";

/** 앱 최상위 컴포넌트. 브라우저 주소로 라우팅한다. */
export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
