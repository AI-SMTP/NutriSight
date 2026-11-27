/**
 * 화면 ① 상태 훅(스펙 3.5절 화면 ①, 공통 규칙).
 *
 * - 선택: 날짜 기본값은 시연일(`useDemoDate`), 끼니 기본값은 화면에 들어온 순간의 시각 규칙(`defaultMeal`)이다.
 *   시연일이 준비되기 전에는 끼니를 조회하지 않는다.
 * - 업로드: `prepareUpload()` → `uploadBaseline`을 `useSubmission`으로 보낸다. 대상(날짜·끼니)과 사진은
 *   요청 객체에 고정하고, 요청 중에는 선택·사진 입력·제출을 막는다. 성공하면 `markSubmitted`(대상 키는
 *   `meal_plan_id`) 뒤에 `refetch`를 부른다. 404면 그 끼니를 다시 읽는다.
 * - 요청이 없을 때 날짜·끼니를 바꾸면 고른 사진과 오류 메시지를 지운다.
 * - 성공 안내(`submitNotice`)는 지우지 않고, 안내를 남긴 끼니(`noticeKey`)를 보고 있을 때만 보인다.
 *   스펙은 안내를 조회 실패(가·나)에도 유지하라고 하는데, (가)는 끼니를 바꿨다가 돌아온 뒤에만 생긴다.
 *   그래서 끼니를 바꿔도 안내를 지우지 않되, 다른 끼니에서 "등록됨"으로 오해하지 않도록 숨긴다.
 *   새 업로드를 시작하면 이전 안내를 지운다.
 */
import { useState } from "react";

import { ApiError, mealPlanId, uploadBaseline, type Meal } from "../../api/provisional";
import { prepareUpload } from "../../lib/image";
import { defaultMeal } from "../shared/defaultMeal";
import { useDemoDate, type DemoDate } from "../shared/useDemoDate";
import { useMealQuery, type MealQuery } from "../shared/useMealQuery";
import { useSubmission, type Submission } from "../shared/useSubmission";
import { BASELINE_REGISTERED } from "./messages";

/** 업로드 요청 객체(요청 시점에 고정한다) */
interface BaselineRequest {
  date: string;
  meal: Meal;
  file: File;
}

/** 날짜·끼니 선택. 사용자가 날짜를 고르기 전에는 시연일을 쓴다 */
function useSelection() {
  const demo = useDemoDate();
  const [pickedDate, setPickedDate] = useState<string | null>(null);
  const [meal, setMeal] = useState<Meal>(() => defaultMeal(new Date()));
  const date = demo.status === "ready" ? (pickedDate ?? demo.date) : null;
  return { demo, date, meal, setPickedDate, setMeal };
}

/** 사진 업로드와 확인 시트 */
function useUpload(query: MealQuery, submission: Submission) {
  const [file, setFile] = useState<File | null>(null);
  const [noticeKey, setNoticeKey] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const upload = (target: BaselineRequest) => {
    setConfirming(false);
    query.clearSubmitNotice();
    submission.submit(
      target,
      async (request) => {
        const prepared = await prepareUpload(request.file);
        return uploadBaseline(request.date, request.meal, prepared.blob);
      },
      {
        onSuccess: (_photo, request) => {
          const key = mealPlanId(request.date, request.meal);
          setNoticeKey(key);
          query.markSubmitted(key, BASELINE_REGISTERED);
          query.refetch();
          setFile(null);
        },
        onError: (error) => {
          if (error instanceof ApiError && error.kind === "not_found") query.refetch();
        },
      },
    );
  };

  return { file, setFile, noticeKey, confirming, setConfirming, upload };
}

export interface BaselineScreen {
  demo: DemoDate;
  date: string | null;
  meal: Meal;
  query: MealQuery;
  file: File | null;
  /** 지금 보고 있는 끼니의 성공 안내 */
  notice: string | null;
  uploadError: Submission["error"];
  busy: boolean;
  confirming: boolean;
  /** 날짜·끼니 입력을 막는지 */
  selectionDisabled: boolean;
  /** 사진 입력을 막는지 */
  pickerDisabled: boolean;
  /** 업로드 버튼을 막는지 */
  submitDisabled: boolean;
  selectDate: (date: string) => void;
  selectMeal: (meal: Meal) => void;
  selectFile: (file: File) => void;
  /** 업로드 버튼. 이미 등록된 끼니면 확인 시트를 연다 */
  requestUpload: () => void;
  confirmUpload: () => void;
  cancelUpload: () => void;
}

export function useBaselineScreen(): BaselineScreen {
  const { demo, date, meal, setPickedDate, setMeal } = useSelection();
  const query = useMealQuery({ date, meal, enabled: demo.status === "ready" });
  const submission = useSubmission();
  const upload = useUpload(query, submission);
  const currentKey = date === null ? null : mealPlanId(date, meal);

  const selectionDisabled = demo.status !== "ready" || submission.busy;
  const pickerDisabled = selectionDisabled || query.view !== "ready";
  const locked = currentKey !== null && query.isLocked(currentKey);
  const target = date !== null && upload.file !== null ? { date, meal, file: upload.file } : null;
  const submitDisabled = pickerDisabled || target === null || locked;

  // 요청이 없을 때만 선택을 바꾸고, 고른 사진과 오류 메시지를 지운다
  const changeSelection = (apply: () => void) => {
    if (submission.busy) return;
    upload.setFile(null);
    submission.clearError();
    apply();
  };

  return {
    demo,
    date,
    meal,
    query,
    file: upload.file,
    notice: upload.noticeKey === currentKey ? query.submitNotice : null,
    uploadError: submission.error,
    busy: submission.busy,
    confirming: upload.confirming,
    selectionDisabled,
    pickerDisabled,
    submitDisabled,
    selectDate: (next) => {
      if (next !== "") changeSelection(() => setPickedDate(next));
    },
    selectMeal: (next) => changeSelection(() => setMeal(next)),
    selectFile: upload.setFile,
    requestUpload: () => {
      if (target === null) return;
      if (query.data?.baseline_photo) upload.setConfirming(true);
      else upload.upload(target);
    },
    // 시트가 열린 동안 조회 결과가 바뀌어(배식 계획 없음 등) 제출할 수 없게 됐으면 요청하지 않고 닫는다
    confirmUpload: () => {
      if (target !== null && !submitDisabled) upload.upload(target);
      else upload.setConfirming(false);
    },
    cancelUpload: () => upload.setConfirming(false),
  };
}
