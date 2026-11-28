/**
 * 화면 ①② 공통 문구.
 * - 조회 상태 안내(`VIEW_MESSAGES`): 설계 단계에서 정한 문구다(`docs/specs/frontend-shell-upload.md` '끼니 조회 순서 규칙'·'시연일 초기화').
 *   "불러오는 중…"만 구현 중 추가한 제안이다.
 * - 업로드 공통 오류(`COMMON_UPLOAD_ERRORS`): 404·413은 설계 단계에서, 422·네트워크는 구현 중 제안한 문구다
 *   (참조 문서 '오류 안내 문구'). 409·500 등 화면마다 다른 실패는 각 화면의 `messages.ts`가 `uploadErrorMessages`로 채운다.
 */
import type { ApiErrorKind } from "../../api/provisional";

/** 조회 상태 안내(참조 문서 '오류 안내 문구'의 조회 상태 안내) */
export const VIEW_MESSAGES = {
  demoDateFailed: "시연일을 불러오지 못했습니다",
  noPlan: "이 날짜·끼니의 배식 계획이 없습니다",
  unreachable: "서버에 연결할 수 없습니다",
  refreshFailed: "목록을 새로 고치지 못했습니다",
  loading: "불러오는 중…",
  retry: "다시 시도",
} as const;

/** 두 화면의 업로드가 같은 문구를 쓰는 실패 분류 */
const COMMON_UPLOAD_ERRORS = {
  not_found: "대상을 찾을 수 없습니다. 목록을 새로 고칩니다",
  too_large: "사진이 너무 큽니다",
  invalid: "사진을 확인할 수 없습니다. 다른 사진을 골라 주세요",
  network: "서버에 연결할 수 없습니다. 다시 시도해 주세요",
} as const satisfies Partial<Record<ApiErrorKind, string>>;

/** 화면마다 다른 실패 분류 */
type ScreenUploadErrorKind = Exclude<ApiErrorKind, keyof typeof COMMON_UPLOAD_ERRORS>;

/**
 * 공통 문구에 화면별 문구를 더해 업로드 실패 분류별 안내 함수를 만든다.
 * 상태 코드 분류만 보고 서버 본문(`detail`)은 보지 않는다.
 */
export function uploadErrorMessages(
  screenErrors: Readonly<Record<ScreenUploadErrorKind, string>>,
): (kind: ApiErrorKind) => string {
  const table: Readonly<Record<ApiErrorKind, string>> = {
    ...COMMON_UPLOAD_ERRORS,
    ...screenErrors,
  };
  return (kind) => table[kind];
}
