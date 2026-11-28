import { Navigate, Route, Routes } from "react-router";

import type { ConnectSystemEvents } from "../api/events";
import { BaselinePage } from "../features/baseline/BaselinePage";
import { CameraCheck } from "../features/cameraCheck/CameraCheck";
import { PostMealPage } from "../features/postMeal/PostMealPage";
import { AppLayout, MealScreensLayout } from "./AppLayout";
import { RoleSelect } from "./RoleSelect";
import { PATHS } from "./screens";

export interface AppRoutesProps {
  /** 화면 ①② 레이아웃의 SSE 연결 함수(테스트 주입용). 주지 않으면 `EventSource`를 쓴다 */
  connectEvents?: ConnectSystemEvents;
}

/** 경로 4개(`docs/specs/frontend-shell-upload.md` '라우트'). 화면 ①②는 공통 레이아웃 라우트 아래에 둔다. */
export function AppRoutes({ connectEvents }: AppRoutesProps = {}) {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<RoleSelect />} />
        <Route element={<MealScreensLayout connectEvents={connectEvents} />}>
          <Route path={PATHS.baseline} element={<BaselinePage />} />
          <Route path={PATHS.postMeal} element={<PostMealPage />} />
        </Route>
        <Route path={PATHS.cameraCheck} element={<CameraCheck />} />
        <Route path="*" element={<Navigate to={PATHS.home} replace />} />
      </Route>
    </Routes>
  );
}
