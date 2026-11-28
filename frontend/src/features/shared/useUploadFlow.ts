/**
 * 화면 ①② 공통 업로드 흐름(`docs/specs/frontend-shell-upload.md` '제출과 잠금 규칙'의 요청 대상 고정·성공 처리·잠금 해제).
 *
 * - 고른 사진(`file`)을 들고, 요청이 없을 때 선택을 바꾸면(`changeSelection`) 사진과 오류 메시지를 지운다.
 * - `start(target, run, options)`는 이전 성공 안내를 지우고 `useSubmission`으로 요청한다. 사진 업로드뿐 아니라
 *   사진 없는 제출(화면 ②의 전량 기록)도 이 함수를 쓴다. 성공하면
 *   대상(`options.lockKey`)을 로컬 제출 완료로 표시하고(`markSubmitted`) 다시 읽은 뒤(`refetch`) 사진을 비운다.
 *   실패 분류가 `options.refetchOn`에 있으면 그 끼니를 다시 읽는다.
 * - 성공 안내는 지우지 않고, 안내를 남긴 끼니(`meal_plan_id`)를 보고 있을 때만 `notice`로 내보낸다.
 *   설계상 안내를 조회 실패(가·나)에도 유지하라고 하는데, (가)는 끼니를 바꿨다가 돌아온 뒤에만 생긴다.
 *   그래서 끼니를 바꿔도 안내를 지우지 않되, 다른 끼니에서 잘못 읽히지 않도록 숨긴다.
 */
import { useState } from "react";

import { ApiError, mealPlanId, type ApiErrorKind, type Meal } from "../../api/provisional";
import type { MealQuery } from "./useMealQuery";
import type { Submission } from "./useSubmission";

/** 제출 요청 객체가 반드시 담는 값(성공 안내를 남길 끼니) */
export interface SubmitTarget {
  date: string;
  meal: Meal;
}

/** 업로드 요청 객체가 반드시 담는 값 */
export interface UploadTarget extends SubmitTarget {
  file: File;
}

export interface UploadOptions<T extends SubmitTarget> {
  /** 로컬 제출 완료 대상 키(①은 `meal_plan_id`, ②는 `meal_order_id`) */
  lockKey: (request: Readonly<T>) => string;
  /** 성공 안내 문구 */
  notice: (request: Readonly<T>) => string;
  /** 실패해도 그 끼니를 다시 읽는 분류 */
  refetchOn: ReadonlySet<ApiErrorKind>;
}

export interface UploadFlowArgs {
  query: MealQuery;
  submission: Submission;
  date: string | null;
  meal: Meal;
}

export interface UploadFlow {
  file: File | null;
  selectFile: (file: File) => void;
  /** 지금 보고 있는 끼니의 성공 안내 */
  notice: string | null;
  /** 요청이 없을 때만 `apply`를 부르고, 고른 사진과 오류 메시지를 지운다 */
  changeSelection: (apply: () => void) => void;
  /** 제출한다. 사진이 없는 요청(화면 ②의 전량 기록)도 같은 성공·실패 처리를 쓴다 */
  start: <T extends SubmitTarget, R>(
    target: T,
    run: (request: Readonly<T>) => Promise<R>,
    options: UploadOptions<T>,
  ) => void;
}

export function useUploadFlow({ query, submission, date, meal }: UploadFlowArgs): UploadFlow {
  const [file, setFile] = useState<File | null>(null);
  const [noticeKey, setNoticeKey] = useState<string | null>(null);
  const currentKey = date === null ? null : mealPlanId(date, meal);

  const start: UploadFlow["start"] = (target, run, options) => {
    query.clearSubmitNotice();
    submission.submit(target, run, {
      onSuccess: (_result, request) => {
        setNoticeKey(mealPlanId(request.date, request.meal));
        query.markSubmitted(options.lockKey(request), options.notice(request));
        query.refetch();
        setFile(null);
      },
      onError: (error) => {
        if (error instanceof ApiError && options.refetchOn.has(error.kind)) query.refetch();
      },
    });
  };

  return {
    file,
    selectFile: setFile,
    notice: noticeKey === currentKey ? query.submitNotice : null,
    changeSelection: (apply) => {
      if (submission.busy) return;
      setFile(null);
      submission.clearError();
      apply();
    },
    start,
  };
}
