// 모의 API 메모리 상태의 레코드 타입. 필드 이름·값은 data-model.md의 테이블을 따른다.
import type {
  Meal,
  OrderStatus,
  PhotoKind,
  PhotoStage,
  PhotoStatus,
  RecordStatus,
  Slot,
  StaffZeroReason,
} from "../api/provisional";

/** `patients` 중 화면 ①②가 쓰는 필드 */
export interface MockPatient {
  readonly patient_id: string;
  readonly display_name: string;
  readonly room: string;
}

/** `meal_plans` + `meal_plan_slots` */
export interface MockPlan {
  readonly meal_plan_id: string;
  readonly date: string;
  readonly meal: Meal;
  readonly slots: readonly Slot[];
  readonly baseline_photo_id: string | null;
}

/** `meal_orders` 중 화면 ①②가 쓰는 필드 */
export interface MockOrder {
  readonly meal_order_id: string;
  readonly patient_id: string;
  readonly meal_plan_id: string;
  readonly order_status: OrderStatus;
  readonly record_status: RecordStatus;
  readonly staff_zero_reason: StaffZeroReason | null;
  readonly post_photo_id: string | null;
}

/** `photos` 중 화면 ①②가 쓰는 필드 */
export interface MockPhoto {
  readonly photo_id: string;
  readonly kind: PhotoKind;
  readonly meal_plan_id: string;
  /** 식후 사진만 */
  readonly meal_order_id: string | null;
  readonly status: PhotoStatus;
  readonly stage: PhotoStage | null;
  readonly uploaded_at: string;
}

/** 모의 API 전체 상태. 갱신은 항상 새 객체로 한다 */
export interface MockState {
  readonly demoDate: string;
  readonly patients: readonly MockPatient[];
  readonly plans: readonly MockPlan[];
  readonly orders: readonly MockOrder[];
  readonly photos: readonly MockPhoto[];
  /** 다음에 만들 사진 ID 번호 */
  readonly nextPhotoSeq: number;
}
