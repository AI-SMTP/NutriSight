// 경로별 상단 표시(화면 제목·역할 배지). 역할은 화면 구분일 뿐 권한이 아니다(스펙 3.5절).
import { matchPath } from "react-router";

export type ScreenMeta = {
  title: string;
  /** 역할 배지 문구. 역할이 없는 화면(역할 선택·촬영 확인)은 null */
  role: string | null;
};

export const PATHS = {
  home: "/",
  baseline: "/baseline",
  postMeal: "/post-meal",
  cameraCheck: "/camera-check",
} as const;

const HOME: ScreenMeta = { title: "역할 선택", role: null };

const SCREENS: ReadonlyMap<string, ScreenMeta> = new Map([
  [PATHS.home, HOME],
  [PATHS.baseline, { title: "기준 식전 사진", role: "영양사" }],
  [PATHS.postMeal, { title: "식후 사진", role: "요양보호사" }],
  [PATHS.cameraCheck, { title: "촬영 확인", role: null }],
]);

/**
 * 경로에 맞는 상단 표시. 라우터와 같은 matchPath 규칙(끝 `/`·대소문자 무시)으로 찾는다.
 * 모르는 경로(역할 선택으로 보내기 직전)는 역할 선택으로 본다.
 */
export function screenMeta(pathname: string): ScreenMeta {
  for (const [path, meta] of SCREENS) {
    if (matchPath({ path, end: true, caseSensitive: false }, pathname)) return meta;
  }
  return HOME;
}
