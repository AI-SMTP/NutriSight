/**
 * 화면 ① 기준 식전 사진(/baseline, `docs/specs/frontend-shell-upload.md` '기준 사진 화면').
 * 영양사가 날짜·끼니를 고르고 배식 계획 6칸과 등록 상태를 보며 기준 식전 사진을 올린다.
 * 상태와 업로드 규칙은 `useBaselineScreen`에 있고, 이 파일은 그리기만 한다.
 * 조회 상태별 본문·안내 조각은 화면 ②와 함께 `features/shared`에서 가져온다.
 */
import { useRef, type RefObject } from "react";

import { Button } from "../../components/Button";
import { ConfirmSheet } from "../../components/ConfirmSheet";
import { PhotoPicker } from "../../components/PhotoPicker";
import { SegmentedControl } from "../../components/SegmentedControl";
import { formatClock } from "../../lib/format";
import shared from "../shared/MealScreen.module.css";
import {
  ErrorAlert,
  MealQueryBody,
  RefreshErrorMessage,
  SubmitNotice,
  UploadPanelFrame,
} from "../shared/MealScreenParts";
import { mealOptions } from "../shared/meals";
import styles from "./BaselinePage.module.css";
import { RESUBMIT_SHEET, SHOOTING_GUIDE, uploadErrorMessage } from "./messages";
import { TrayLayout } from "./TrayLayout";
import { useBaselineScreen, type BaselineScreen } from "./useBaselineScreen";

const MEAL_OPTIONS = mealOptions();

/** 끼니 데이터가 있을 때: 새로 고침 오류 안내, 6칸, 등록 상태 */
function PlanView({ screen }: { screen: BaselineScreen }) {
  const { data } = screen.query;
  if (data === null) return null;
  const baseline = data.baseline_photo;
  return (
    <>
      <RefreshErrorMessage query={screen.query} />
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

interface UploadPanelProps {
  screen: BaselineScreen;
  titleRef: RefObject<HTMLHeadingElement | null>;
}

/** 촬영 안내, 사진 입력, 업로드 오류, 업로드 버튼 */
function UploadPanel({ screen, titleRef }: UploadPanelProps) {
  return (
    <UploadPanelFrame busy={screen.busy} titleRef={titleRef}>
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
      <ErrorAlert
        message={screen.uploadError === null ? null : uploadErrorMessage(screen.uploadError)}
      />
      <Button
        onClick={screen.requestUpload}
        disabled={screen.submitDisabled}
        aria-busy={screen.busy}
      >
        기준 사진 업로드
      </Button>
    </UploadPanelFrame>
  );
}

export function BaselinePage() {
  const screen = useBaselineScreen();
  // 시트가 요청 없이 닫혀 업로드 버튼이 막혀 있으면(배식 계획 없음 등) 포커스를 업로드 영역 제목으로 옮긴다
  const panelTitleRef = useRef<HTMLHeadingElement>(null);
  return (
    <section className={shared.screen}>
      <SelectionControls screen={screen} />
      <SubmitNotice notice={screen.notice} />
      <MealQueryBody demo={screen.demo} query={screen.query}>
        <PlanView screen={screen} />
      </MealQueryBody>
      <UploadPanel screen={screen} titleRef={panelTitleRef} />
      <ConfirmSheet
        open={screen.confirming}
        title={RESUBMIT_SHEET.title}
        message={RESUBMIT_SHEET.message}
        confirmLabel={RESUBMIT_SHEET.confirmLabel}
        onConfirm={screen.confirmUpload}
        onCancel={screen.cancelUpload}
        fallbackFocusRef={panelTitleRef}
      />
    </section>
  );
}
