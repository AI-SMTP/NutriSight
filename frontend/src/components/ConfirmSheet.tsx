import { useEffect, useId, useRef } from "react";

import { Button } from "./Button";
import styles from "./ConfirmSheet.module.css";

export type ConfirmSheetProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** 요청 진행 중이면 두 버튼과 Escape를 막는다 */
  busy?: boolean;
};

// Tab·Shift+Tab을 시트 안의 누를 수 있는 버튼 사이에서만 돌린다. 버튼이 모두 막혀 있으면 시트에 둔다.
// jsdom에 HTMLDialogElement.showModal이 없어 네이티브 <dialog> 대신 직접 가둔다.
function trapTab(event: KeyboardEvent, sheet: HTMLElement): void {
  const buttons = [...sheet.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
  const first = buttons[0];
  const last = buttons.at(-1);
  const active = document.activeElement;
  const outside = !sheet.contains(active) || active === sheet;
  if (!first || !last) {
    event.preventDefault();
    sheet.focus();
  } else if (event.shiftKey && (active === first || outside)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (active === last || outside)) {
    event.preventDefault();
    first.focus();
  }
}

/**
 * 화면 아래에서 올라오는 확인 시트(모달).
 * 열리면 취소 버튼에 포커스를 두고, 닫히면 시트를 연 요소로 포커스를 돌려준다.
 * 처리 중에는 버튼이 막히므로 시트 자체(tabIndex=-1)에 포커스를 둔다.
 */
export function ConfirmSheet({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel = "취소",
  onConfirm,
  onCancel,
  busy = false,
}: ConfirmSheetProps) {
  const titleId = useId();
  const messageId = useId();
  const sheetRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  // 열릴 때 포커스를 가진 요소를 기억했다가 닫히면(또는 언마운트되면) 돌려준다.
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => {
      if (opener?.isConnected) opener.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    (busy ? sheetRef.current : cancelRef.current)?.focus();
  }, [open, busy]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const sheet = sheetRef.current;
      if (event.key === "Tab" && sheet) trapTab(event, sheet);
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, busy, onCancel]);

  if (!open) return null;
  return (
    <div className={styles.backdrop}>
      <div
        ref={sheetRef}
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={messageId}
        tabIndex={-1}
      >
        <h2 id={titleId} className={styles.title}>
          {title}
        </h2>
        <p id={messageId} className={styles.message}>
          {message}
        </p>
        <div className={styles.actions}>
          <Button ref={cancelRef} variant="secondary" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
