/**
 * 화면 ② 식후 사진(/post-meal, `docs/specs/frontend-shell-upload.md` '식후 사진 화면').
 * 요양보호사가 오늘 세 끼 중 하나와 환자를 고르고 식후 사진을 올리며, 그 끼니의 업로드 현황을 본다.
 * 상태와 업로드 규칙은 `usePostMealScreen`에 있고, 이 파일은 그리기만 한다.
 * 전량 기록(전량 거부·전량 미섭취) 버튼과 확인 시트는 `StaffZeroSlot`이 그린다.
 */
import { useId, useRef } from "react";

import { Button } from "../../components/Button";
import { PhotoPicker } from "../../components/PhotoPicker";
import { SegmentedControl } from "../../components/SegmentedControl";
import shared from "../shared/MealScreen.module.css";
import {
  ErrorAlert,
  MealQueryBody,
  RefreshErrorMessage,
  SubmitNotice,
  UploadPanelFrame,
} from "../shared/MealScreenParts";
import { mealOptions } from "../shared/meals";
import {
  BASELINE_GUIDE,
  NOT_RECORDABLE,
  PICK_PATIENT,
  uploadErrorMessage,
  uploadLabel,
} from "./messages";
import { OrderList } from "./OrderList";
import styles from "./PostMealPage.module.css";
import { StaffZeroSlot } from "./StaffZeroSlot";
import { usePostMealScreen, type PostMealScreen } from "./usePostMealScreen";

const MEAL_OPTIONS = mealOptions("오늘 ");

/**
 * 기준 사진 안내. 끼니가 바뀌거나 기준 사진이 등록되면 읽히도록 `role="status"` 영역을 늘 두고
 * 글자만 바꾼다(성공 안내 영역과 같은 방식). 끼니 데이터가 없으면 비운다.
 */
function BaselineGuide({ screen }: { screen: PostMealScreen }) {
  const { data } = screen.query;
  const text =
    data === null ? null : data.baseline_photo ? BASELINE_GUIDE.ready : BASELINE_GUIDE.missing;
  return (
    <p
      className={text === null ? undefined : styles.guide}
      role="status"
      data-testid="baseline-guide"
    >
      {text}
    </p>
  );
}

/** 끼니 데이터가 있을 때: 새로 고침 오류 안내, 환자 목록 겸 현황 */
function OrdersView({ screen }: { screen: PostMealScreen }) {
  const { data } = screen.query;
  if (data === null) return null;
  return (
    <>
      <RefreshErrorMessage query={screen.query} />
      <OrderList
        orders={data.orders}
        selectedPatientId={screen.selectedOrder?.patient_id ?? null}
        disabled={screen.patientDisabled}
        onSelect={screen.selectPatient}
      />
    </>
  );
}

/** 막힌 이유를 보일지: 끼니 데이터가 있고, 고른 환자가 있는데 기록할 수 없을 때 */
function isBlocked(screen: PostMealScreen): boolean {
  return screen.query.view === "ready" && screen.selectedOrder !== null && !screen.recordable;
}

/** 고른 환자 상태 안내: 고르기 전이면 고르라는 안내, 기록할 수 없으면 임시 규칙 안내(막힌 이유) */
function SelectionHint({ screen, blockedId }: { screen: PostMealScreen; blockedId: string }) {
  if (screen.query.view !== "ready") return null;
  if (screen.selectedOrder === null) return <p className={styles.hint}>{PICK_PATIENT}</p>;
  if (!isBlocked(screen)) return null;
  return (
    <p id={blockedId} className={shared.messageText}>
      {NOT_RECORDABLE}
    </p>
  );
}

/** 사진 입력, 업로드 오류, 업로드 버튼, 전량 기록 */
function UploadPanel({ screen }: { screen: PostMealScreen }) {
  const blockedId = useId();
  const describedBy = isBlocked(screen) ? blockedId : undefined;
  // 전량 기록 시트가 요청 없이 닫혀 버튼이 막혀 있으면 포커스를 이 제목으로 옮긴다(바로 아래가 막힌 이유 안내)
  const titleRef = useRef<HTMLHeadingElement>(null);
  return (
    <UploadPanelFrame busy={screen.busy} titleRef={titleRef}>
      <SelectionHint screen={screen} blockedId={blockedId} />
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
        aria-describedby={describedBy}
      >
        {uploadLabel(screen.selectedOrder?.display_name ?? null)}
      </Button>
      <StaffZeroSlot screen={screen} blockedId={describedBy} fallbackFocusRef={titleRef} />
    </UploadPanelFrame>
  );
}

export function PostMealPage() {
  const screen = usePostMealScreen();
  return (
    <section className={shared.screen}>
      <SegmentedControl
        legend="끼니"
        name="post-meal-meal"
        options={MEAL_OPTIONS}
        value={screen.meal}
        disabled={screen.mealDisabled}
        onChange={screen.selectMeal}
      />
      <SubmitNotice notice={screen.notice} />
      <BaselineGuide screen={screen} />
      <MealQueryBody demo={screen.demo} query={screen.query}>
        <OrdersView screen={screen} />
      </MealQueryBody>
      <UploadPanel screen={screen} />
    </section>
  );
}
