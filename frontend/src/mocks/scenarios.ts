// 끼니별 픽스처 상태 분포(팀 제안안). fixtures.ts가 이 표로 발주·사진 초기값을 만든다.
// 표에 없는 환자는 미기록(`not_recorded`, 사진 없음)이다. 금식 여부는 fixtures.ts의 NPO_PATIENT_ID가 정한다.
import type { MockOrder, MockPhoto } from "./types";

/** 사진 행에서 끼니·발주에 따라 정해지는 필드를 뺀 값 */
type PhotoSeed = Omit<MockPhoto, "kind" | "meal_plan_id" | "meal_order_id">;

/** 환자 한 명의 발주 초기값 */
export interface OrderSeed {
  record_status?: MockOrder["record_status"];
  staff_zero_reason?: MockOrder["staff_zero_reason"];
  /** 발주에 연결된 식후 사진 */
  photo?: PhotoSeed;
}

export interface MealScenario {
  baseline: PhotoSeed | null;
  orders: Readonly<Record<string, OrderSeed>>;
}

/** 처리가 끝나 기록된 식후 사진 */
function donePhoto(photoId: string, uploadedAt: string): OrderSeed {
  return {
    record_status: "recorded",
    photo: { photo_id: photoId, status: "done", stage: "alert", uploaded_at: uploadedAt },
  };
}

/** 아침: 기준 사진 등록, NS03 미기록, 나머지(금식 제외)는 완료 */
export const breakfastScenario: MealScenario = {
  baseline: {
    photo_id: "fx_breakfast_baseline",
    status: "uploaded",
    stage: null,
    uploaded_at: "2026-11-27T07:40:00+09:00",
  },
  orders: {
    NS02: donePhoto("fx_breakfast_NS02", "2026-11-27T08:31:00+09:00"),
    NS04: donePhoto("fx_breakfast_NS04", "2026-11-27T08:33:00+09:00"),
    NS05: donePhoto("fx_breakfast_NS05", "2026-11-27T08:34:00+09:00"),
    NS06: donePhoto("fx_breakfast_NS06", "2026-11-27T08:35:00+09:00"),
    NS07: donePhoto("fx_breakfast_NS07", "2026-11-27T08:36:00+09:00"),
    NS08: donePhoto("fx_breakfast_NS08", "2026-11-27T08:37:00+09:00"),
    NS09: donePhoto("fx_breakfast_NS09", "2026-11-27T08:38:00+09:00"),
    NS10: donePhoto("fx_breakfast_NS10", "2026-11-27T08:39:00+09:00"),
  },
};

/**
 * 점심: 기준 사진 등록, NS03 미기록. 미기록(NS03·NS08)·처리 중(NS04 분석 중·NS09 대기열)·
 * 완료(NS02·NS07·NS10)·재촬영 필요(NS05)·완료 · 전량 거부(NS06)가 섞인다.
 */
export const lunchScenario: MealScenario = {
  baseline: {
    photo_id: "fx_lunch_baseline",
    status: "uploaded",
    stage: null,
    uploaded_at: "2026-11-27T11:50:00+09:00",
  },
  orders: {
    NS02: donePhoto("fx_lunch_NS02", "2026-11-27T12:41:00+09:00"),
    NS04: {
      record_status: "pending",
      photo: {
        photo_id: "fx_lunch_NS04",
        status: "analyzing",
        stage: "intake",
        uploaded_at: "2026-11-27T12:44:00+09:00",
      },
    },
    NS05: {
      record_status: "not_determinable",
      photo: {
        photo_id: "fx_lunch_NS05",
        status: "not_determinable",
        stage: "intake",
        uploaded_at: "2026-11-27T12:45:00+09:00",
      },
    },
    NS06: { record_status: "recorded", staff_zero_reason: "refused" },
    NS07: donePhoto("fx_lunch_NS07", "2026-11-27T12:47:00+09:00"),
    NS09: {
      record_status: "pending",
      photo: {
        photo_id: "fx_lunch_NS09",
        status: "queued",
        stage: null,
        uploaded_at: "2026-11-27T12:49:00+09:00",
      },
    },
    NS10: donePhoto("fx_lunch_NS10", "2026-11-27T12:50:00+09:00"),
  },
};

/** 저녁: 기준 사진 없음, 모두 미기록 */
export const dinnerScenario: MealScenario = { baseline: null, orders: {} };
