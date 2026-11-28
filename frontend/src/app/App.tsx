import { BrowserRouter } from "react-router";

import { MockUnavailableBanner } from "./MockUnavailableBanner";
import { AppRoutes } from "./routes";

export interface AppProps {
  /** 모의 API 모드인데 MSW 워커를 시작하지 못했으면 참. 모든 화면 상단에 배너를 띄운다 */
  mockUnavailable?: boolean;
}

/** 앱 최상위 컴포넌트. 브라우저 주소로 라우팅한다. */
export function App({ mockUnavailable = false }: AppProps) {
  return (
    <BrowserRouter>
      {mockUnavailable && <MockUnavailableBanner />}
      <AppRoutes />
    </BrowserRouter>
  );
}
