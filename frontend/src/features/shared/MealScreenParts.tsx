/**
 * 화면 ①② 공통 조각: "다시 시도" 안내, 조회 상태별 본문, 성공 안내 영역, 업로드 영역 틀, 요청 실패 안내.
 * 본문 규칙은 `docs/specs/frontend-shell-upload.md` '시연일 초기화'·'끼니 조회 순서 규칙'(시연일 실패 → 로딩 → 404 → (가) → 데이터)을 따른다.
 */
import type { ReactNode, RefObject } from "react";

import { Button } from "../../components/Button";
import styles from "./MealScreen.module.css";
import { VIEW_MESSAGES } from "./messages";
import type { DemoDate } from "./useDemoDate";
import { useFocusWhileBusy } from "./useFocusWhileBusy";
import type { MealQuery } from "./useMealQuery";

/** 안내 문구와 "다시 시도" 버튼 한 줄 */
export function RetryMessage({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={styles.message}>
      <p className={styles.messageText}>{message}</p>
      <Button variant="secondary" onClick={onRetry}>
        {VIEW_MESSAGES.retry}
      </Button>
    </div>
  );
}

/** 재조회 실패(참조 문서 '끼니 조회 순서 규칙'의 (나)) 안내. 보여 주던 데이터 위에 띄운다 */
export function RefreshErrorMessage({ query }: { query: MealQuery }) {
  if (!query.refreshError) return null;
  return <RetryMessage message={VIEW_MESSAGES.refreshFailed} onRetry={query.refetch} />;
}

export interface MealQueryBodyProps {
  demo: DemoDate;
  query: MealQuery;
  /** 끼니 데이터가 준비됐을 때 그린다 */
  children: ReactNode;
}

/** 본문: 시연일·끼니 조회 상태에 따라 하나를 보인다 */
export function MealQueryBody({ demo, query, children }: MealQueryBodyProps) {
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
  if (query.data === null) return null;
  return <>{children}</>;
}

/** 제출 성공 안내 영역. 늘 두고 글자만 바꾼다(보조 기술이 바뀐 내용을 읽도록) */
export function SubmitNotice({ notice }: { notice: string | null }) {
  return (
    <p className={notice === null ? undefined : styles.notice} role="status">
      {notice}
    </p>
  );
}

export interface UploadPanelFrameProps {
  busy: boolean;
  children: ReactNode;
  /** 제목 ref. 확인 시트가 요청 없이 닫힐 때 대신 포커스를 줄 곳으로 화면이 함께 쓴다 */
  titleRef: RefObject<HTMLHeadingElement | null>;
}

/** 업로드 영역 틀: 요청이 시작되면 포커스를 받는 "사진 올리기" 제목 아래에 화면별 내용을 둔다 */
export function UploadPanelFrame({ busy, children, titleRef }: UploadPanelFrameProps) {
  useFocusWhileBusy(busy, titleRef);
  return (
    <div className={styles.panel}>
      <h2 ref={titleRef} className={styles.panelTitle} tabIndex={-1}>
        사진 올리기
      </h2>
      {children}
    </div>
  );
}

/** 요청 실패 안내 */
export function ErrorAlert({ message }: { message: string | null }) {
  if (message === null) return null;
  return (
    <p className={styles.error} role="alert">
      {message}
    </p>
  );
}
