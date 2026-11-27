import { Link } from "react-router";

import styles from "./MockUnavailableBanner.module.css";
import { PATHS } from "./screens";

/** MSW 워커를 시작하지 못했을 때의 배너 문구(스펙 3.2절) */
export const MOCK_UNAVAILABLE_MESSAGE = "모의 API를 쓸 수 없습니다(보안 컨텍스트 아님)";

/**
 * 모의 API 사용 불가 배너. 모든 화면 상단에 두고, 실기기 확인을 위해 촬영 확인 화면 링크를 단다
 * (스펙 3.2절 실기기 접속, 3.5절 `/camera-check`).
 */
export function MockUnavailableBanner() {
  return (
    <div role="alert" className={styles.banner}>
      <p className={styles.message}>{MOCK_UNAVAILABLE_MESSAGE}</p>
      <Link to={PATHS.cameraCheck} className={styles.link}>
        촬영 확인
      </Link>
    </div>
  );
}
