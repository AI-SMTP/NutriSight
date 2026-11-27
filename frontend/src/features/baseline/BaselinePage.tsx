/**
 * 화면 ① 기준 식전 사진(/baseline, 스펙 3.5절 화면 ①).
 * 영양사가 날짜·끼니를 고르고 배식 계획 6칸과 등록 상태를 보며 기준 식전 사진을 올린다.
 * 상태와 업로드 규칙은 `useBaselineScreen`에 있고, 이 파일은 그리기만 한다.
 */
import { useEffect, useRef } from "react";

import type { Meal } from "../../api/provisional";
import { Button } from "../../components/Button";
import { ConfirmSheet } from "../../components/ConfirmSheet";
import { PhotoPicker } from "../../components/PhotoPicker";
import { SegmentedControl, type SegmentOption } from "../../components/SegmentedControl";
import { formatClock } from "../../lib/format";
import styles from "./BaselinePage.module.css";
import { RESUBMIT_SHEET, SHOOTING_GUIDE, VIEW_MESSAGES, uploadErrorMessage } from "./messages";
import { TrayLayout } from "./TrayLayout";
import { useBaselineScreen, type BaselineScreen } from "./useBaselineScreen";

const MEAL_OPTIONS: readonly SegmentOption<Meal>[] = [
  { value: "breakfast", label: "아침" },
  { value: "lunch", label: "점심" },
  { value: "dinner", label: "저녁" },
];

/** 안내 문구와 "다시 시도" 버튼 한 줄 */
function RetryMessage({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={styles.message}>
      <p className={styles.messageText}>{message}</p>
      <Button variant="secondary" onClick={onRetry}>
        {VIEW_MESSAGES.retry}
      </Button>
    </div>
  );
}

/** 끼니 데이터가 있을 때: 새로 고침 오류 안내, 6칸, 등록 상태 */
function PlanView({ screen }: { screen: BaselineScreen }) {
  const { data, refreshError, refetch } = screen.query;
  if (data === null) return null;
  const baseline = data.baseline_photo;
  return (
    <>
      {refreshError && <RetryMessage message={VIEW_MESSAGES.refreshFailed} onRetry={refetch} />}
      <TrayLayout slots={data.slots} />
      <p className={styles.status}>
        기준 사진{" "}
        <span className={styles.statusValue} data-testid="baseline-status">
          {baseline ? `등록됨 (${formatClock(baseline.uploaded_at)})` : "아직 없음"}
        </span>
      </p>
    </>
  );
}

/** 본문: 시연일·끼니 조회 상태에 따라 하나를 보인다(스펙 3.5절 공통 규칙) */
function MealBody({ screen }: { screen: BaselineScreen }) {
  const { demo, query } = screen;
  if (demo.status === "error") {
    return <RetryMessage message={VIEW_MESSAGES.demoDateFailed} onRetry={demo.retry} />;
  }
  if (demo.status === "loading" || query.view === "loading") {
    return <p className={styles.messageText}>{VIEW_MESSAGES.loading}</p>;
  }
  if (query.view === "no_plan") return <p className={styles.messageText}>{VIEW_MESSAGES.noPlan}</p>;
  if (query.view === "unreachable") {
    return <RetryMessage message={VIEW_MESSAGES.unreachable} onRetry={query.refetch} />;
  }
  return <PlanView screen={screen} />;
}

/** 날짜·끼니 선택 */
function SelectionControls({ screen }: { screen: BaselineScreen }) {
  return (
    <div className={styles.selection}>
      <label className={styles.dateLabel}>
        날짜
        <input
          className={styles.dateInput}
          type="date"
          value={screen.date ?? ""}
          disabled={screen.selectionDisabled}
          onChange={(event) => screen.selectDate(event.target.value)}
        />
      </label>
      <SegmentedControl
        legend="끼니"
        name="baseline-meal"
        options={MEAL_OPTIONS}
        value={screen.meal}
        disabled={screen.selectionDisabled}
        onChange={screen.selectMeal}
      />
    </div>
  );
}

/** 업로드가 시작되면 패널 제목으로 포커스를 옮긴다(버튼이 막히고 시트가 닫혀도 body로 빠지지 않게) */
function useFocusWhileBusy(busy: boolean) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  // 확인 시트가 닫히며 여는 버튼으로 포커스를 돌려주는 정리 함수보다 이 이펙트가 나중에 돈다
  useEffect(() => {
    if (busy) titleRef.current?.focus();
  }, [busy]);
  return titleRef;
}

/** 촬영 안내, 사진 입력, 업로드 오류, 업로드 버튼 */
function UploadPanel({ screen }: { screen: BaselineScreen }) {
  const titleRef = useFocusWhileBusy(screen.busy);
  return (
    <div className={styles.upload}>
      <h2 ref={titleRef} className={styles.panelTitle} tabIndex={-1}>
        사진 올리기
      </h2>
      <ul className={styles.guide}>
        {SHOOTING_GUIDE.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <PhotoPicker
        value={screen.file}
        onSelect={screen.selectFile}
        disabled={screen.pickerDisabled}
      />
      {screen.uploadError !== null && (
        <p className={styles.error} role="alert">
          {uploadErrorMessage(screen.uploadError)}
        </p>
      )}
      <Button
        onClick={screen.requestUpload}
        disabled={screen.submitDisabled}
        aria-busy={screen.busy}
      >
        기준 사진 업로드
      </Button>
    </div>
  );
}

export function BaselinePage() {
  const screen = useBaselineScreen();
  return (
    <section className={styles.screen}>
      <SelectionControls screen={screen} />
      {/* 안내 영역은 늘 두고 글자만 바꾼다(보조 기술이 바뀐 내용을 읽도록) */}
      <p className={screen.notice === null ? undefined : styles.notice} role="status">
        {screen.notice}
      </p>
      <MealBody screen={screen} />
      <UploadPanel screen={screen} />
      <ConfirmSheet
        open={screen.confirming}
        title={RESUBMIT_SHEET.title}
        message={RESUBMIT_SHEET.message}
        confirmLabel={RESUBMIT_SHEET.confirmLabel}
        onConfirm={screen.confirmUpload}
        onCancel={screen.cancelUpload}
      />
    </section>
  );
}
