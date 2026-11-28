/**
 * 화면 ②의 환자 목록 겸 업로드 현황(`docs/specs/frontend-shell-upload.md` '식후 사진 화면' 3번).
 * 발주 요약 배열 하나로 그린다(참조 문서 '데이터 형식'의 `MealOrderSummary`). 항목은 "room · display_name"과 배지를 담은
 * 공용 `Button`이고, 금식·취소(`orderBadge(...).selectable === false`)는 회색 배지에 `disabled`다.
 * 머리글은 `summarizeOrders`의 "완료 x / y · 금식 n"이다.
 */
import { useId } from "react";

import type { MealOrderSummary } from "../../api/provisional";
import { Badge, type BadgeTone } from "../../components/Badge";
import { Button } from "../../components/Button";
import { orderBadge, summarizeOrders, type BadgeKind } from "../../lib/mealStatus";
import shared from "../shared/MealScreen.module.css";
import { ORDERS_TITLE } from "./messages";
import styles from "./PostMealPage.module.css";

/** 배지 색. 회색(neutral)은 고를 수 없는 금식·취소에만 쓴다 */
const BADGE_TONES: Readonly<Record<BadgeKind, BadgeTone>> = {
  npo: "neutral",
  cancelled: "neutral",
  done: "primary",
  retake: "danger",
  waiting_baseline: "accent",
  processing: "accent",
  not_recorded: "accent",
};

export interface OrderListProps {
  orders: readonly MealOrderSummary[];
  /** 고른 환자의 `patient_id` */
  selectedPatientId: string | null;
  disabled: boolean;
  onSelect: (patientId: string) => void;
}

function OrderItem({
  order,
  selected,
  disabled,
  onSelect,
}: {
  order: MealOrderSummary;
  selected: boolean;
  disabled: boolean;
  onSelect: (patientId: string) => void;
}) {
  const badge = orderBadge(order);
  return (
    <li>
      <Button
        variant="secondary"
        className={styles.patientButton}
        aria-pressed={selected}
        disabled={disabled || !badge.selectable}
        onClick={() => onSelect(order.patient_id)}
      >
        <span className={styles.patientName}>{`${order.room} · ${order.display_name}`}</span>{" "}
        <Badge tone={BADGE_TONES[badge.kind]}>{badge.label}</Badge>
      </Button>
    </li>
  );
}

export function OrderList({ orders, selectedPatientId, disabled, onSelect }: OrderListProps) {
  const titleId = useId();
  return (
    <div className={shared.panel}>
      <div className={styles.ordersHeader}>
        <h2 id={titleId} className={shared.panelTitle}>
          {ORDERS_TITLE}
        </h2>
        <p className={styles.summary} data-testid="order-summary">
          {summarizeOrders(orders)}
        </p>
      </div>
      <ul className={styles.list} aria-labelledby={titleId}>
        {orders.map((order) => (
          <OrderItem
            key={order.meal_order_id}
            order={order}
            selected={order.patient_id === selectedPatientId}
            disabled={disabled}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </div>
  );
}
