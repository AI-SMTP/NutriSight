import { Navigate, Route, Routes } from "react-router";

import { CameraCheck } from "../features/cameraCheck/CameraCheck";
import { AppLayout, MealScreensLayout, PlaceholderScreen } from "./AppLayout";
import { RoleSelect } from "./RoleSelect";
import { PATHS } from "./screens";

/** 경로 4개(스펙 3.5절). 화면 ①②는 공통 레이아웃 라우트 아래에 둔다. */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<RoleSelect />} />
        <Route element={<MealScreensLayout />}>
          <Route path={PATHS.baseline} element={<PlaceholderScreen />} />
          <Route path={PATHS.postMeal} element={<PlaceholderScreen />} />
        </Route>
        <Route path={PATHS.cameraCheck} element={<CameraCheck />} />
        <Route path="*" element={<Navigate to={PATHS.home} replace />} />
      </Route>
    </Routes>
  );
}
