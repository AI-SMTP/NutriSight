/**
 * 화면 ① 상태 훅(`docs/specs/frontend-shell-upload.md` '기준 사진 화면', '끼니 조회 순서 규칙'·'제출과 잠금 규칙').
 *
 * - 선택: 날짜 기본값은 시연일(`useDemoDate`), 끼니 기본값은 화면에 들어온 순간의 시각 규칙(`defaultMeal`)이다.
 *   시연일이 준비되기 전에는 끼니를 조회하지 않는다.
 * - 업로드: `prepareUpload()` → `uploadBaseline`을 `useSubmission`으로 보낸다. 대상(날짜·끼니)과 사진은
 *   요청 객체에 고정하고, 요청 중에는 선택·사진 입력·제출을 막는다. 성공하면 `markSubmitted`(대상 키는
 *   `meal_plan_id`) 뒤에 `refetch`를 부른다. 404면 그 끼니를 다시 읽는다.
 * - 사진 보관, 선택 변경 때 사진·오류 지우기, 성공 처리, 안내 필터는 공용 `useUploadFlow`가 맡는다.
 */
import { useState } from "react";

import { mealPlanId, uploadBaseline, type ApiErrorKind, type Meal } from "../../api/provisional";
import { prepareUpload } from "../../lib/image";
import { defaultMeal } from "../shared/defaultMeal";
import { useDemoDate, type DemoDate } from "../shared/useDemoDate";
import { useMealQuery, type MealQuery } from "../shared/useMealQuery";
import { useSubmission, type Submission } from "../shared/useSubmission";
import {
  useUploadFlow,
  type UploadFlow,
  type UploadOptions,
  type UploadTarget,
} from "../shared/useUploadFlow";
import { BASELINE_REGISTERED } from "./messages";

/** 업로드 요청 객체(요청 시점에 고정한다). 공용 업로드 대상(날짜·끼니·사진) 그대로다 */
type BaselineRequest = UploadTarget;

/** 성공하면 그 끼니(`meal_plan_id`)를 잠그고, 404면 다시 읽는다 */
const BASELINE_UPLOAD: UploadOptions<BaselineRequest> = {
  lockKey: (request) => mealPlanId(request.date, request.meal),
  notice: () => BASELINE_REGISTERED,
  refetchOn: new Set<ApiErrorKind>(["not_found"]),
};

async function sendBaseline(request: Readonly<BaselineRequest>) {
  const prepared = await prepareUpload(request.file);
  return uploadBaseline(request.date, request.meal, prepared.blob);
}

/** 날짜·끼니 선택. 사용자가 날짜를 고르기 전에는 시연일을 쓴다 */
function useSelection() {
  const demo = useDemoDate();
  const [pickedDate, setPickedDate] = useState<string | null>(null);
  const [meal, setMeal] = useState<Meal>(() => defaultMeal(new Date()));
  const date = demo.status === "ready" ? (pickedDate ?? demo.date) : null;
  return { demo, date, meal, setPickedDate, setMeal };
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

type BaselineActions = Pick<
  BaselineScreen,
  "selectDate" | "selectMeal" | "requestUpload" | "confirmUpload" | "cancelUpload"
>;

interface ActionContext {
  flow: UploadFlow;
  query: MealQuery;
  target: BaselineRequest | null;
  submitDisabled: boolean;
  setConfirming: (open: boolean) => void;
  setPickedDate: (date: string) => void;
  setMeal: (meal: Meal) => void;
}

/** 버튼·선택 핸들러 */
function baselineActions(ctx: ActionContext): BaselineActions {
  const { flow, target, setConfirming } = ctx;
  const upload = (request: BaselineRequest) => {
    setConfirming(false);
    flow.start(request, sendBaseline, BASELINE_UPLOAD);
  };
  return {
    selectDate: (next) => {
      if (next !== "") flow.changeSelection(() => ctx.setPickedDate(next));
    },
    selectMeal: (next) => flow.changeSelection(() => ctx.setMeal(next)),
    requestUpload: () => {
      if (target === null) return;
      if (ctx.query.data?.baseline_photo) setConfirming(true);
      else upload(target);
    },
    // 시트가 열린 동안 조회 결과가 바뀌어(배식 계획 없음 등) 제출할 수 없게 됐으면 요청하지 않고 닫는다
    confirmUpload: () => {
      if (target !== null && !ctx.submitDisabled) upload(target);
      else setConfirming(false);
    },
    cancelUpload: () => setConfirming(false),
  };
}

export function useBaselineScreen(): BaselineScreen {
  const { demo, date, meal, setPickedDate, setMeal } = useSelection();
  const query = useMealQuery({ date, meal, enabled: demo.status === "ready" });
  const submission = useSubmission();
  const flow = useUploadFlow({ query, submission, date, meal });
  const [confirming, setConfirming] = useState(false);

  const selectionDisabled = demo.status !== "ready" || submission.busy;
  const pickerDisabled = selectionDisabled || query.view !== "ready";
  const locked = date !== null && query.isLocked(mealPlanId(date, meal));
  const target = date !== null && flow.file !== null ? { date, meal, file: flow.file } : null;
  const submitDisabled = pickerDisabled || target === null || locked;
  const actions = baselineActions({
    flow,
    query,
    target,
    submitDisabled,
    setConfirming,
    setPickedDate,
    setMeal,
  });

  return {
    demo,
    date,
    meal,
    query,
    file: flow.file,
    notice: flow.notice,
    uploadError: submission.error,
    busy: submission.busy,
    confirming,
    selectionDisabled,
    pickerDisabled,
    submitDisabled,
    selectFile: flow.selectFile,
    ...actions,
  };
}
