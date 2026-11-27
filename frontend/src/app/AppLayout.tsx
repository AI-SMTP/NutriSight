import { Link, Outlet, useLocation } from "react-router";

import { Badge } from "../components/Badge";
import styles from "./AppLayout.module.css";
import { PATHS, screenMeta } from "./screens";

/** 모든 화면 공통 레이아웃: 상단(서비스 이름·화면 제목·역할 배지)과 본문. */
export function AppLayout() {
  const { pathname } = useLocation();
  const { title, role } = screenMeta(pathname);
  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <Link to={PATHS.home} className={styles.homeLink}>
          NutriSight
        </Link>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{title}</h1>
          {role !== null && <Badge tone="accent">{role}</Badge>}
        </div>
      </header>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}

/**
 * 화면 ①② 공통 레이아웃 라우트. SSE 구독 Provider(api/events.tsx)를 이 자리에 둔다.
 * 역할 선택과 촬영 확인은 이 라우트 밖이라 구독하지 않는다(스펙 3.3절).
 */
export function MealScreensLayout() {
  return <Outlet />;
}

/** 아직 만들지 않은 화면의 자리표시 */
export function PlaceholderScreen() {
  return <p className={styles.placeholder}>화면을 준비하고 있습니다</p>;
}
