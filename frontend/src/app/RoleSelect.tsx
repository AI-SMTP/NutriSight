import { Link } from "react-router";

import styles from "./RoleSelect.module.css";
import { PATHS } from "./screens";

type ReadyRole = { name: string; screen: string; to: string };

const READY_ROLES: readonly ReadyRole[] = [
  { name: "영양사", screen: "① 기준 식전 사진", to: PATHS.baseline },
  { name: "요양보호사", screen: "② 식후 사진", to: PATHS.postMeal },
];

// 화면 ③(의사)·④(처리 상태)는 후속 토픽 T7에서 만들므로 지금은 누를 수 없게 둔다.
const PENDING_ROLES: readonly string[] = ["의사", "처리 상태"];

/** 역할 선택(/). 고른 역할은 저장하지 않는다(URL이 곧 화면). */
export function RoleSelect() {
  return (
    <div className={styles.screen}>
      <ul className={styles.list}>
        {READY_ROLES.map((role) => (
          <li key={role.to}>
            <Link to={role.to} className={styles.roleLink}>
              <span className={styles.name}>{role.name}</span>
              <span className={styles.detail}>{role.screen}</span>
            </Link>
          </li>
        ))}
        {PENDING_ROLES.map((name) => (
          <li key={name}>
            <button type="button" className={styles.roleLink} disabled>
              <span className={styles.name}>{name}</span>
              <span className={styles.detail}>준비 중</span>
            </button>
          </li>
        ))}
      </ul>
      <Link to={PATHS.cameraCheck} className={styles.cameraLink}>
        촬영 확인
      </Link>
    </div>
  );
}
