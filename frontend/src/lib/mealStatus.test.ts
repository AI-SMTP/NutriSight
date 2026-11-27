// 화면 ② 배지·현황 규칙 테스트. 정본은 스펙 3.5절 화면 ② 배지 표(위에서부터 처음 맞는 행).
import {
  canRecord,
  orderBadge,
  summarizeOrders,
  type BadgeKind,
  type OrderStatusInput,
} from "./mealStatus";

function order(overrides: Partial<OrderStatusInput> = {}): OrderStatusInput {
  return {
    order_status: "ordered",
    record_status: "not_recorded",
    staff_zero_reason: null,
    post_photo: null,
    ...overrides,
  };
}

function photo(status: string): OrderStatusInput["post_photo"] {
  return { status };
}

describe("orderBadge — 배지 표 6행", () => {
  it.each<[string, OrderStatusInput, BadgeKind, string, boolean]>([
    ["1행 금식", order({ order_status: "npo" }), "npo", "금식", false],
    ["1행 취소", order({ order_status: "cancelled" }), "cancelled", "취소", false],
    [
      "2행 완료(사진 분석)",
      order({ record_status: "recorded", post_photo: photo("done") }),
      "done",
      "완료",
      true,
    ],
    [
      "2행 완료 · 전량 거부",
      order({ record_status: "recorded", staff_zero_reason: "refused" }),
      "done",
      "완료 · 전량 거부",
      true,
    ],
    [
      "3행 재촬영 필요",
      order({ record_status: "not_determinable", post_photo: photo("not_determinable") }),
      "retake",
      "재촬영 필요",
      true,
    ],
    [
      "4행 기준 사진 대기",
      order({ record_status: "pending", post_photo: photo("waiting_baseline") }),
      "waiting_baseline",
      "처리 중 · 기준 사진 대기",
      true,
    ],
    [
      "5행 처리 중(analyzing)",
      order({ record_status: "pending", post_photo: photo("analyzing") }),
      "processing",
      "처리 중",
      true,
    ],
    ["6행 미기록", order(), "not_recorded", "미기록", true],
  ])("%s", (_name, input, kind, label, selectable) => {
    expect(orderBadge(input)).toEqual({ kind, label, selectable });
  });
});

describe("orderBadge — 겹치는 경우는 위 행이 이긴다", () => {
  it.each<[string, OrderStatusInput, BadgeKind, string]>([
    [
      "npo + recorded → 금식",
      order({ order_status: "npo", record_status: "recorded" }),
      "npo",
      "금식",
    ],
    [
      "cancelled + 사진 analyzing → 취소",
      order({
        order_status: "cancelled",
        record_status: "pending",
        post_photo: photo("analyzing"),
      }),
      "cancelled",
      "취소",
    ],
    [
      "recorded + not_eaten → 완료 · 전량 미섭취",
      order({ record_status: "recorded", staff_zero_reason: "not_eaten" }),
      "done",
      "완료 · 전량 미섭취",
    ],
    [
      "recorded + 사진 not_determinable(이전 사진) → 완료",
      order({
        record_status: "recorded",
        staff_zero_reason: "refused",
        post_photo: photo("not_determinable"),
      }),
      "done",
      "완료 · 전량 거부",
    ],
    [
      "사진만 not_determinable → 재촬영 필요",
      order({ record_status: "not_recorded", post_photo: photo("not_determinable") }),
      "retake",
      "재촬영 필요",
    ],
    [
      "사진 failed → 처리 중",
      order({ record_status: "failed", post_photo: photo("failed") }),
      "processing",
      "처리 중",
    ],
    [
      "record_status failed, 사진 연결 없음 → 처리 중",
      order({ record_status: "failed" }),
      "processing",
      "처리 중",
    ],
    [
      "record_status pending, 사진 연결 없음 → 처리 중",
      order({ record_status: "pending" }),
      "processing",
      "처리 중",
    ],
    [
      "record_status not_determinable, 사진 연결 없음 → 재촬영 필요",
      order({ record_status: "not_determinable" }),
      "retake",
      "재촬영 필요",
    ],
    [
      "record_status not_determinable + 사진 queued → 재촬영 필요",
      order({ record_status: "not_determinable", post_photo: photo("queued") }),
      "retake",
      "재촬영 필요",
    ],
    [
      "record_status not_determinable + 사진 waiting_baseline → 재촬영 필요",
      order({ record_status: "not_determinable", post_photo: photo("waiting_baseline") }),
      "retake",
      "재촬영 필요",
    ],
    [
      "사진 done + record_status pending → 처리 중",
      order({ record_status: "pending", post_photo: photo("done") }),
      "processing",
      "처리 중",
    ],
    [
      "사진 uploaded + record_status not_recorded → 처리 중",
      order({ record_status: "not_recorded", post_photo: photo("uploaded") }),
      "processing",
      "처리 중",
    ],
    [
      "사진 queued + record_status not_recorded → 처리 중",
      order({ record_status: "not_recorded", post_photo: photo("queued") }),
      "processing",
      "처리 중",
    ],
  ])("%s", (_name, input, kind, label) => {
    const badge = orderBadge(input);
    expect(badge.kind).toBe(kind);
    expect(badge.label).toBe(label);
  });

  it("recorded + 알 수 없는 staff_zero_reason → 완료", () => {
    expect(orderBadge(order({ record_status: "recorded", staff_zero_reason: "other" })).label).toBe(
      "완료",
    );
  });

  it.each(["constructor", "toString", "__proto__", "hasOwnProperty"])(
    "recorded + 프로토타입 속성 이름 staff_zero_reason %s → 완료",
    (reason) => {
      expect(
        orderBadge(order({ record_status: "recorded", staff_zero_reason: reason })).label,
      ).toBe("완료");
    },
  );

  it.each(["uploaded", "queued", "analyzing", "failed"])("사진 %s → 처리 중", (status) => {
    expect(orderBadge(order({ record_status: "pending", post_photo: photo(status) })).kind).toBe(
      "processing",
    );
  });

  it("입력 객체를 바꾸지 않는다", () => {
    const input = Object.freeze(order({ post_photo: Object.freeze(photo("queued")) }));
    expect(() => orderBadge(input)).not.toThrow();
  });
});

describe("canRecord", () => {
  it.each<[BadgeKind, boolean]>([
    ["not_recorded", true],
    ["retake", true],
    ["npo", false],
    ["cancelled", false],
    ["done", false],
    ["waiting_baseline", false],
    ["processing", false],
  ])("%s → %s", (kind, expected) => {
    expect(canRecord({ kind, label: "", selectable: true })).toBe(expected);
  });

  it("orderBadge 결과와 함께 쓴다", () => {
    expect(canRecord(orderBadge(order()))).toBe(true);
    expect(canRecord(orderBadge(order({ record_status: "recorded" })))).toBe(false);
  });
});

describe("summarizeOrders — 현황 머리글", () => {
  function orders(counts: {
    npo: number;
    cancelled: number;
    recorded: number;
    total: number;
  }): OrderStatusInput[] {
    const nonOrdered = [
      ...Array.from({ length: counts.npo }, () => order({ order_status: "npo" })),
      ...Array.from({ length: counts.cancelled }, () => order({ order_status: "cancelled" })),
    ];
    const recorded = Array.from({ length: counts.recorded }, () =>
      order({ record_status: "recorded" }),
    );
    const rest = Array.from({ length: counts.total - nonOrdered.length - recorded.length }, () =>
      order(),
    );
    return [...nonOrdered, ...recorded, ...rest];
  }

  it("발주 10건(npo 1, 기록 완료 3) → 완료 3 / 9 · 금식 1", () => {
    expect(summarizeOrders(orders({ npo: 1, cancelled: 0, recorded: 3, total: 10 }))).toBe(
      "완료 3 / 9 · 금식 1",
    );
  });

  it("발주 10건(npo 1, cancelled 1, 기록 완료 3) → 완료 3 / 8 · 금식 1 (취소는 분모에서 빠짐)", () => {
    expect(summarizeOrders(orders({ npo: 1, cancelled: 1, recorded: 3, total: 10 }))).toBe(
      "완료 3 / 8 · 금식 1",
    );
  });

  it("금식 끼니의 record_status가 recorded여도 완료로 세지 않는다", () => {
    const input = [order({ order_status: "npo", record_status: "recorded" }), order()];
    expect(summarizeOrders(input)).toBe("완료 0 / 1 · 금식 1");
  });

  it("빈 목록 → 완료 0 / 0 · 금식 0", () => {
    expect(summarizeOrders([])).toBe("완료 0 / 0 · 금식 0");
  });

  it("고정(freeze)한 배열도 바꾸지 않고 요약한다", () => {
    const input = Object.freeze([
      Object.freeze(order({ order_status: "npo" })),
      Object.freeze(order({ order_status: "cancelled" })),
      Object.freeze(order({ record_status: "recorded" })),
      Object.freeze(order()),
    ]);
    expect(summarizeOrders(input)).toBe("완료 1 / 2 · 금식 1");
    expect(input).toHaveLength(4);
  });
});
