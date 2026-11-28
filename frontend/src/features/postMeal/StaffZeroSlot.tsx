/**
 * "사진 없이 기록"(전량 거부·전량 미섭취) 영역(`docs/specs/frontend-shell-upload.md` '식후 사진 화면' 6번).
 * 버튼 → 확인 시트("NS03 점심을 전량 거부로 기록합니다") → 기록 순서다. 상태와 요청 규칙은
 * `useStaffZero`·`usePostMealScreen`에 있고, 이 파일은 그리기만 한다.
 * 실패 안내는 업로드 실패와 따로 이 영역에 보인다(같은 `submission`을 쓰지만 문구가 다르다).
 */
import { useId, type RefObject } from "react";

import type { StaffZeroReason } from "../../api/provisional";
import { Button } from "../../components/Button";
import { ConfirmSheet } from "../../components/ConfirmSheet";
import { ErrorAlert } from "../shared/MealScreenParts";
import {
  STAFF_ZERO_LABELS,
  STAFF_ZERO_SHEET,
  STAFF_ZERO_TITLE,
  staffZeroConfirmMessage,
  staffZeroErrorMessage,
} from "./messages";
import styles from "./PostMealPage.module.css";
import type { PostMealScreen } from "./usePostMealScreen";

const REASONS: readonly StaffZeroReason[] = ["refused", "not_eaten"];

export interface StaffZeroSlotProps {
  screen: PostMealScreen;
  /** 버튼이 막힌 이유(임시 규칙 안내) 요소의 id. 막혀 있지 않으면 없다 */
  blockedId?: string;
  /** 확인 시트가 닫힐 때 버튼이 막혀 있으면 대신 포커스를 받을 요소(업로드 영역 제목) */
  fallbackFocusRef?: RefObject<HTMLElement | null>;
}

export function StaffZeroSlot({ screen, blockedId, fallbackFocusRef }: StaffZeroSlotProps) {
  const titleId = useId();
  const { staffZero, staffZeroError } = screen;
  const pending = staffZero.pending;
  return (
    <div className={styles.staffZero} role="group" aria-labelledby={titleId}>
      <h3 id={titleId} className={styles.staffZeroTitle}>
        {STAFF_ZERO_TITLE}
      </h3>
      <ErrorAlert
        message={staffZeroError === null ? null : staffZeroErrorMessage(staffZeroError)}
      />
      <div className={styles.staffZeroActions}>
        {REASONS.map((reason) => (
          <Button
            key={reason}
            variant="secondary"
            onClick={() => staffZero.open(reason)}
            disabled={screen.staffZeroDisabled}
            aria-busy={screen.busy}
            aria-describedby={blockedId}
          >
            {STAFF_ZERO_LABELS[reason]}
          </Button>
        ))}
      </div>
      <ConfirmSheet
        open={pending !== null}
        title={STAFF_ZERO_SHEET.title}
        message={pending === null ? "" : staffZeroConfirmMessage(pending)}
        confirmLabel={STAFF_ZERO_SHEET.confirmLabel}
        onConfirm={staffZero.confirm}
        onCancel={staffZero.cancel}
        fallbackFocusRef={fallbackFocusRef}
      />
    </div>
  );
}
