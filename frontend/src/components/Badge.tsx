import type { ReactNode } from "react";

import styles from "./Badge.module.css";

/** neutral은 회색(금식·취소 등 선택 불가 상태)이다. */
export type BadgeTone = "neutral" | "primary" | "danger" | "accent";

export type BadgeProps = {
  tone?: BadgeTone;
  children: ReactNode;
};

/** 상태·역할을 보여 주는 작은 배지. 누를 수 없다. */
export function Badge({ tone = "primary", children }: BadgeProps) {
  return (
    <span className={`${styles.badge} ${styles[tone]}`} data-tone={tone}>
      {children}
    </span>
  );
}
