// 글자·배경 색 조합의 WCAG 2 대비를 tokens.css 값으로 계산해 4.5:1 이상인지 확인한다(`docs/specs/frontend-shell-upload.md` '테스트와 E2E').
// 배지 조합은 Badge.module.css의 tone 규칙에서 읽어, 배지 색을 바꾸면 이 테스트가 함께 검사한다.
// Vitest는 CSS 처리를 끈 상태에서 `?raw` CSS import도 빈 프록시로 바꾸므로 node fs로 직접 읽는다.
/// <reference types="node" />
// jsdom 환경의 전역 URL은 node fs가 받지 않으므로 경로 문자열로 넘긴다.
import { readFileSync } from "node:fs";
import { join } from "node:path";

const tokensCss = readFileSync(join(import.meta.dirname, "tokens.css"), "utf8");
const badgeCss = readFileSync(join(import.meta.dirname, "../components/Badge.module.css"), "utf8");

const MIN_CONTRAST = 4.5;

function parseTokens(css: string): ReadonlyMap<string, string> {
  const entries = [...css.matchAll(/--(color-[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g)].map(
    (m) => [m[1] as string, (m[2] as string).toLowerCase()] as const,
  );
  return new Map(entries);
}

const tokens = parseTokens(tokensCss);

function hexOf(token: string): string {
  const hex = tokens.get(token);
  if (hex === undefined) throw new Error(`tokens.css에 --${token}이 없습니다`);
  return hex;
}

// sRGB 채널 → 선형값 (WCAG 2.x 상대 휘도 정의)
function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => channel(parseInt(hex.slice(i, i + 2), 16)));
  return 0.2126 * (r as number) + 0.7152 * (g as number) + 0.0722 * (b as number);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

// Badge.module.css에서 `.tone { background: var(--x); color: var(--y); }`를 읽는다.
function badgePairs(css: string): [string, string, string][] {
  return [...css.matchAll(/\.(\w+)\s*\{([^}]*)\}/g)].flatMap((m) => {
    const body = m[2] as string;
    const fg = /(?:^|[\s;])color:\s*var\(--([\w-]+)\)/.exec(body)?.[1];
    const bg = /background:\s*var\(--([\w-]+)\)/.exec(body)?.[1];
    return fg && bg ? [[`badge.${m[1]}`, fg, bg]] : [];
  });
}

const TEXT_ON_BACKGROUNDS: [string, string, string][] = [
  "color-text",
  "color-text-muted",
  "color-text-subtle",
].flatMap((fg) =>
  ["color-bg", "color-surface"].map((bg) => [`${fg} / ${bg}`, fg, bg] as [string, string, string]),
);

const PAIRS: [string, string, string][] = [
  ...TEXT_ON_BACKGROUNDS,
  ["흰 글자 / 주색 버튼", "color-surface", "color-primary"],
  ["주색 진하게 / 주색 옅게", "color-primary-strong", "color-primary-soft"],
  ["위험 글자 / 위험 배경", "color-danger", "color-danger-soft"],
  ["보조 글자 / 보조 배경", "color-accent", "color-accent-soft"],
  ...badgePairs(badgeCss),
];

describe("색 대비", () => {
  it("tokens.css에서 색 14개를 읽는다", () => {
    expect(tokens.size).toBe(14);
  });

  it("Badge.module.css에서 회색(neutral)을 포함한 tone 4개를 읽는다", () => {
    const names = badgePairs(badgeCss).map(([name]) => name);
    expect(names).toEqual(["badge.neutral", "badge.primary", "badge.danger", "badge.accent"]);
  });

  it("검증식이 흑백 21:1, 같은 색 1:1을 낸다", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#0f766e", "#0f766e")).toBeCloseTo(1, 5);
  });

  it.each(PAIRS)("%s 대비가 4.5:1 이상이다", (_name, fg, bg) => {
    expect(contrast(hexOf(fg), hexOf(bg))).toBeGreaterThanOrEqual(MIN_CONTRAST);
  });
});
