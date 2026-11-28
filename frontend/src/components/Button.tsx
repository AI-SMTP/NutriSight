import type { ComponentPropsWithRef } from "react";

import styles from "./Button.module.css";

export type ButtonVariant = "primary" | "secondary" | "danger";

export type ButtonProps = ComponentPropsWithRef<"button"> & {
  variant?: ButtonVariant;
};

/** 공용 버튼. 기본 type은 form 제출을 막기 위해 "button"이다. 터치 영역은 --touch-min 이상. */
export function Button({ variant = "primary", type = "button", className, ...rest }: ButtonProps) {
  const classes = [styles.button, styles[variant], className].filter(Boolean).join(" ");
  return <button {...rest} type={type} className={classes} data-variant={variant} />;
}
