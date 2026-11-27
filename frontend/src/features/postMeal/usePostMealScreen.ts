/**
 * 화면 ② 상태 훅(스펙 3.5절 화면 ②, 공통 규칙).
 *
 * - 선택: 날짜는 늘 시연일(`useDemoDate`)이고 끼니만 고른다(기본값은 화면에 들어온 순간의 시각 규칙).
 *   시연일이 준비되기 전에는 끼니를 조회하지 않는다. 환자는 `patient_id`로 기억하고, 지금 끼니 데이터에서
 *   고를 수 있는(금식·취소가 아닌) 발주가 있을 때만 선택된 것으로 본다. 끼니를 바꾸면 환자 선택을 지운다.
 * - 배지·허용 여부는 `orderBadge`·`canRecord`에 `MealOrderSummary`를 그대로 넘겨 정한다. 로컬 제출 완료
 *   잠금(대상 키 `meal_order_id`)이 걸린 발주도 기록할 수 없다.
 * - 업로드: `prepareUpload()` → `uploadPostPhoto`를 `useSubmission`으로 보낸다. 대상(날짜·끼니·환자·
 *   `meal_order_id`)과 사진을 요청 객체에 고정하고, 요청 중에는 끼니·환자·사진 입력·업로드를 막는다.
 *   성공하면 `markSubmitted` 뒤에 `refetch`를 부른다. 404·409면 그 끼니를 다시 읽는다(스펙 3.3절).
 * - 사진 보관, 선택 변경 때 사진·오류 지우기, 성공 처리, 안내 필터(안내를 남긴 끼니를 볼 때만)는
 *   화면 ①과 같은 공용 `useUploadFlow`가 맡는다.
 * - `submission`은 화면에 하나다. Story 17의 전량 기록도 같은 것을 써서 두 요청이 함께 막히게 한다.
 */
import { useState } from "react";

import {
  uploadPostPhoto,
  type ApiErrorKind,
  type Meal,
  type MealDetail,
  type MealOrderSummary,
} from "../../api/provisional";
import { prepareUpload } from "../../lib/image";
import { canRecord, orderBadge } from "../../lib/mealStatus";
import { defaultMeal } from "../shared/defaultMeal";
import { useDemoDate, type DemoDate } from "../shared/useDemoDate";
import { useMealQuery, type MealQuery } from "../shared/useMealQuery";
import { useSubmission, type Submission } from "../shared/useSubmission";
import { useUploadFlow, type UploadFlow, type UploadOptions } from "../shared/useUploadFlow";
import { uploadedNotice } from "./messages";

/** 업로드 요청 객체(요청 시점에 고정한다) */
interface PostPhotoRequest {
  date: string;
  meal: Meal;
  patientId: string;
  mealOrderId: string;
  displayName: string;
  file: File;
}

/** 성공하면 그 발주(`meal_order_id`)를 잠그고, 404·409면 다시 읽는다(스펙 3.3절) */
const POST_PHOTO_UPLOAD: UploadOptions<PostPhotoRequest> = {
  lockKey: (request) => request.mealOrderId,
  notice: (request) => uploadedNotice(request.displayName),
  refetchOn: new Set<ApiErrorKind>(["not_found", "conflict"]),
};

async function sendPostPhoto(request: Readonly<PostPhotoRequest>) {
  const prepared = await prepareUpload(request.file);
  const { patientId, date, meal } = request;
  return uploadPostPhoto({ patientId, date, meal, blob: prepared.blob });
}

/** 고른 환자의 발주. 지금 끼니 데이터에 없거나 금식·취소로 바뀌었으면 선택이 없는 것으로 본다 */
function findSelectedOrder(
  data: MealDetail | null,
  patientId: string | null,
): MealOrderSummary | null {
  if (data === null || patientId === null) return null;
  const order = data.orders.find((o) => o.patient_id === patientId);
  return order !== undefined && orderBadge(order).selectable ? order : null;
}

/** 고른 발주에 지금 기록할 수 있는지(배지가 미기록·재촬영 필요이고 로컬 제출 완료가 아님) */
function isRecordable(order: MealOrderSummary | null, query: MealQuery): boolean {
  return order !== null && canRecord(orderBadge(order)) && !query.isLocked(order.meal_order_id);
}

/** 지금 선택으로 만든 업로드 요청. 보낼 수 없으면 `null` */
function buildRequest(
  date: string | null,
  meal: Meal,
  order: MealOrderSummary | null,
  file: File | null,
): PostPhotoRequest | null {
  if (date === null || order === null || file === null) return null;
  return {
    date,
    meal,
    patientId: order.patient_id,
    mealOrderId: order.meal_order_id,
    displayName: order.display_name,
    file,
  };
}

/** 끼니·환자 선택. 날짜는 늘 시연일이다 */
function useSelection() {
  const demo = useDemoDate();
  const [meal, setMeal] = useState<Meal>(() => defaultMeal(new Date()));
  const [patientId, setPatientId] = useState<string | null>(null);
  const date = demo.status === "ready" ? demo.date : null;
  return { demo, date, meal, setMeal, patientId, setPatientId };
}

export interface PostMealScreen {
  demo: DemoDate;
  /** 시연일. 아직 모르면 `null` */
  date: string | null;
  meal: Meal;
  query: MealQuery;
  /** 업로드·전량 기록이 함께 쓰는 요청 순번 훅 */
  submission: Submission;
  /** 고른 환자의 발주(고를 수 있는 것만) */
  selectedOrder: MealOrderSummary | null;
  /** 고른 발주에 지금 기록할 수 있는지(배지가 미기록·재촬영 필요이고 로컬 제출 완료가 아님) */
  recordable: boolean;
  file: File | null;
  /** 지금 보고 있는 끼니의 성공 안내 */
  notice: string | null;
  uploadError: ApiErrorKind | null;
  busy: boolean;
  /** 끼니 입력을 막는지 */
  mealDisabled: boolean;
  /** 환자 항목을 막는지 */
  patientDisabled: boolean;
  /** 사진 입력을 막는지 */
  pickerDisabled: boolean;
  /** 업로드 버튼을 막는지 */
  submitDisabled: boolean;
  selectMeal: (meal: Meal) => void;
  selectPatient: (patientId: string) => void;
  selectFile: (file: File) => void;
  requestUpload: () => void;
}

type PostMealActions = Pick<PostMealScreen, "selectMeal" | "selectPatient" | "requestUpload">;

interface ActionContext {
  flow: UploadFlow;
  patientId: string | null;
  request: PostPhotoRequest | null;
  submitDisabled: boolean;
  setMeal: (meal: Meal) => void;
  setPatientId: (patientId: string | null) => void;
}

/** 끼니·환자 선택과 업로드 핸들러. 끼니를 바꾸면 환자 선택도 지운다 */
function postMealActions(ctx: ActionContext): PostMealActions {
  const { flow, request } = ctx;
  return {
    selectMeal: (next) =>
      flow.changeSelection(() => {
        ctx.setMeal(next);
        ctx.setPatientId(null);
      }),
    selectPatient: (next) => {
      if (next !== ctx.patientId) flow.changeSelection(() => ctx.setPatientId(next));
    },
    requestUpload: () => {
      if (request !== null && !ctx.submitDisabled) {
        flow.start(request, sendPostPhoto, POST_PHOTO_UPLOAD);
      }
    },
  };
}

export function usePostMealScreen(): PostMealScreen {
  const { demo, date, meal, setMeal, patientId, setPatientId } = useSelection();
  const query = useMealQuery({ date, meal, enabled: demo.status === "ready" });
  const submission = useSubmission();
  const flow = useUploadFlow({ query, submission, date, meal });

  const selectedOrder = findSelectedOrder(query.data, patientId);
  const recordable = isRecordable(selectedOrder, query);
  const mealDisabled = demo.status !== "ready" || submission.busy;
  const patientDisabled = mealDisabled || query.view !== "ready";
  const pickerDisabled = patientDisabled || !recordable;
  const request = buildRequest(date, meal, selectedOrder, flow.file);
  const submitDisabled = pickerDisabled || request === null;
  const actions = postMealActions({
    flow,
    patientId,
    request,
    submitDisabled,
    setMeal,
    setPatientId,
  });

  return {
    demo,
    date,
    meal,
    query,
    submission,
    selectedOrder,
    recordable,
    file: flow.file,
    notice: flow.notice,
    uploadError: submission.error,
    busy: submission.busy,
    mealDisabled,
    patientDisabled,
    pickerDisabled,
    submitDisabled,
    selectFile: flow.selectFile,
    ...actions,
  };
}
