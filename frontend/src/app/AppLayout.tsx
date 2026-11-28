import { Link, Outlet, useLocation } from "react-router";

import { SystemEventsProvider, type ConnectSystemEvents } from "../api/events";
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

export interface MealScreensLayoutProps {
  /** SSE 연결 함수. 기본은 `EventSource("/api/events")`, 테스트는 모의 연결을 넣는다 */
  connectEvents?: ConnectSystemEvents;
}

/**
 * 화면 ①② 공통 레이아웃 라우트. SSE 구독 Provider(api/events.tsx)를 두어 ①② 사이를 오가는 동안
 * 연결 하나를 유지한다. 역할 선택과 촬영 확인은 이 라우트 밖이라 구독하지 않는다(`docs/specs/frontend-shell-upload.md` 'SSE 구독').
 */
export function MealScreensLayout({ connectEvents }: MealScreensLayoutProps) {
  return (
    <SystemEventsProvider connect={connectEvents}>
      <Outlet />
    </SystemEventsProvider>
  );
}
