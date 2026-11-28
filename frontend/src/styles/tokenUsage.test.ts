// 모든 CSS 모듈이 색·모서리·글꼴을 토큰 변수로만 쓰고, 누를 수 있는 요소가 --touch-min을 지키는지 확인한다.
// jsdom은 레이아웃을 계산하지 않으므로 44px 실측은 Playwright E2E에서 한다.

// Vitest는 CSS 처리를 끈 상태에서 `?raw` CSS import(import.meta.glob 포함)도 빈 프록시로 바꾸므로
// node fs로 src 아래 모든 *.module.css를 직접 읽는다.
/// <reference types="node" />
// jsdom 환경의 전역 URL은 node fs가 받지 않으므로 경로 문자열로 넘긴다.
import { globSync, readFileSync } from "node:fs";
import { join } from "node:path";

const SRC_DIR = join(import.meta.dirname, "..");

const files: [string, string][] = globSync("**/*.module.css", { cwd: SRC_DIR })
  .sort()
  .map((file) => [file, readFileSync(join(SRC_DIR, file), "utf8")]);

type Rule = { file: string; selector: string; body: string };

// 주석을 지우고 `선택자 { 선언 }` 블록을 평평하게 읽는다(중첩·@규칙은 쓰지 않는다는 전제).
function parseRules(file: string, css: string): Rule[] {
  const plain = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...plain.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    file,
    selector: (m[1] as string).trim(),
    body: m[2] as string,
  }));
}

const rules = files.flatMap(([file, css]) => parseRules(file, css));

function declarations(property: string): { rule: Rule; value: string }[] {
  const pattern = new RegExp(`(?:^|[\\s;{])${property}\\s*:\\s*([^;]+)`, "g");
  return rules.flatMap((rule) =>
    [...rule.body.matchAll(pattern)].map((m) => ({ rule, value: (m[1] as string).trim() })),
  );
}

// 누를 수 있는 요소 클래스: 이름이 button·label·option·link로 끝나는 클래스(대소문자 무관).
// 상태 변형(:disabled, [data-disabled] 등)이 아닌 기본 규칙에 터치 크기가 있어야 한다.
const TOUCH_CLASS = /\.([A-Za-z]*(?:button|label|option|link))$/i;

function touchRules(): Rule[] {
  return rules.filter((rule) => rule.selector.split(",").some((s) => TOUCH_CLASS.test(s.trim())));
}

// 색을 받는 속성. 값에서 var(--…)를 지운 뒤 남은 낱말이 아래 허용 키워드가 아니면 이름 색(white 등)으로 본다.
const COLOR_PROPERTY =
  /(?:^|[\s;{])((?:background|border|outline|box-shadow|text-shadow|fill|stroke|caret-color|accent-color|text-decoration-color|color)[\w-]*)\s*:\s*([^;]+)/g;

const NON_COLOR_KEYWORDS: ReadonlySet<string> = new Set([
  "transparent",
  "currentcolor",
  "inherit",
  "initial",
  "unset",
  "none",
  "solid",
  "dashed",
  "dotted",
  "double",
  "inset",
  "auto",
  "color-mix",
  "in",
  "srgb",
]);

function namedColorOffenders(): string[] {
  return rules.flatMap((rule) =>
    [...rule.body.matchAll(COLOR_PROPERTY)].flatMap((m) => {
      const words = (m[2] as string)
        .replace(/var\(--[\w-]+\)/g, " ")
        .split(/[\s,()/]+/)
        .filter((word) => /^[a-z-]+$/i.test(word));
      return words
        .filter((word) => !NON_COLOR_KEYWORDS.has(word.toLowerCase()))
        .map((word) => `${rule.file} ${rule.selector} ${m[1]}: ${word}`);
    }),
  );
}

describe("CSS 모듈 토큰 사용", () => {
  it("CSS 모듈을 읽는다(공용 컴포넌트 5종 이상)", () => {
    expect(files.length).toBeGreaterThanOrEqual(5);
    expect(rules.length).toBeGreaterThan(0);
  });

  it("16진 색 리터럴과 rgb()·hsl() 색 함수를 쓰지 않는다", () => {
    const offenders = files
      .filter(([, css]) => /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/.test(css))
      .map(([file]) => file);
    expect(offenders).toEqual([]);
  });

  it("white·black 같은 이름 색을 쓰지 않는다(transparent·currentcolor 등 키워드는 허용)", () => {
    expect(namedColorOffenders()).toEqual([]);
  });

  it.each(["border-radius", "font-family"])("%s 값은 var(--…)만 쓴다", (property) => {
    const offenders = declarations(property)
      .filter(({ value }) => !/^var\(--[\w-]+\)(\s+var\(--[\w-]+\)|\s+0)*$/.test(value))
      .map(({ rule, value }) => `${rule.file} ${rule.selector}: ${value}`);
    expect(offenders).toEqual([]);
  });

  it("누를 수 있는 요소 클래스에 min-height·min-width var(--touch-min)이 있다", () => {
    const targets = touchRules();
    const missing = targets
      .filter(
        ({ body }) =>
          !/min-height:\s*var\(--touch-min\)/.test(body) ||
          !/min-width:\s*var\(--touch-min\)/.test(body),
      )
      .map(({ file, selector }) => `${file} ${selector}`);

    expect(targets.map(({ selector }) => selector)).toEqual(
      expect.arrayContaining([".button", ".option", ".pickerLabel"]),
    );
    expect(missing).toEqual([]);
  });
});
