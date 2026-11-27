/**
 * 시스템 이벤트(SSE) 구독 Provider와 `useSystemEvents` 훅.
 *
 * - 정본: 스펙 3.3절(SSE 구독)·3.4절(Vitest의 주입식 구독)·3.5절(SSE를 받으면 재조회).
 * - 화면 ①②의 공통 레이아웃에 Provider 하나를 두고, 그 Provider가 마운트된 동안 연결 하나를 연다.
 *   레이아웃 안에서 화면을 오가도 연결은 그대로이고, 레이아웃을 벗어나면 `close()`한다.
 * - 구독 화면에는 `photo.status_changed` 데이터와 연결 `open`(첫 연결·재연결 모두)을 알린다.
 *   거르기(`meal_plan_id`)와 재조회는 화면이 한다. `kind`가 있든 없든 그대로 넘긴다.
 * - 재연결은 브라우저 `EventSource`의 자동 재연결에 맡기고, 재연결 때 오는 `open`을 그대로 알린다.
 *   `Last-Event-ID` 재전송은 쓰지 않는다.
 * - 한계: 서버가 200이 아니거나 `text/event-stream`이 아닌 응답을 주면 브라우저가 연결을 CLOSED로
 *   만들고 다시 연결하지 않는다. 파일럿에서는 이를 받아들인다(수동 재연결을 두지 않는다).
 * - 연결 함수는 주입할 수 있다. 기본값은 `new EventSource("/api/events")`이고,
 *   Vitest는 모의 이벤트 버스를 발행기로 쓰는 연결(`src/test/mockConnect.ts`)을 넣는다.
 */
import {
  createContext,
  useContext,
  useEffect,
  useEffectEvent,
  useState,
  type ReactNode,
} from "react";

import {
  EVENTS_PATH,
  PHOTO_STATUS_CHANGED_EVENT,
  type PhotoStatusChangedEvent,
} from "./provisional";

/** Provider가 쓰는 연결의 최소 형태. 브라우저 `EventSource`가 그대로 맞는다 */
export interface SystemEventSource {
  addEventListener(type: string, listener: (event: Event) => void): void;
  close(): void;
}

/** 연결을 새로 여는 함수 */
export type ConnectSystemEvents = () => SystemEventSource;

export interface SystemEventsHandlers {
  /** `photo.status_changed`를 받을 때마다 부른다 */
  onPhotoStatusChanged?: (event: PhotoStatusChangedEvent) => void;
  /** 연결이 열릴 때마다(첫 연결·재연결) 부른다 */
  onOpen?: () => void;
}

/** 기본 연결: 같은 출처의 `/api/events` */
export const connectEventSource: ConnectSystemEvents = () => new EventSource(EVENTS_PATH);

interface Registry {
  subscribe(handlers: SystemEventsHandlers): () => void;
  notifyOpen(): void;
  notifyPhotoStatusChanged(event: PhotoStatusChangedEvent): void;
}

function createRegistry(): Registry {
  let subscribers: ReadonlySet<SystemEventsHandlers> = new Set();
  return {
    subscribe(handlers) {
      subscribers = new Set([...subscribers, handlers]);
      return () => {
        subscribers = new Set([...subscribers].filter((h) => h !== handlers));
      };
    },
    notifyOpen() {
      for (const handlers of subscribers) handlers.onOpen?.();
    },
    notifyPhotoStatusChanged(event) {
      for (const handlers of subscribers) handlers.onPhotoStatusChanged?.(event);
    },
  };
}

/**
 * 메시지 데이터를 이벤트로 읽는다. 화면이 쓰는 `meal_plan_id`·`photo_id`가 문자열이 아니면
 * (JSON 오류 포함) 버린다. 나머지 필드는 계약(`PhotoStatusChangedEvent`)을 믿는다.
 */
export function parsePhotoStatusChanged(event: Event): PhotoStatusChangedEvent | null {
  if (!("data" in event) || typeof event.data !== "string") return null;
  let value: unknown;
  try {
    value = JSON.parse(event.data);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null) return null;
  const { meal_plan_id: mealPlanId, photo_id: photoId } = value as Record<string, unknown>;
  if (typeof mealPlanId !== "string" || typeof photoId !== "string") return null;
  return value as PhotoStatusChangedEvent;
}

const SystemEventsContext = createContext<Registry | null>(null);

export interface SystemEventsProviderProps {
  /** 연결 함수. 마운트할 때 한 번만 부르며, 마운트 뒤 바뀌어도 다시 연결하지 않는다 */
  connect?: ConnectSystemEvents;
  children?: ReactNode;
}

export function SystemEventsProvider({
  connect = connectEventSource,
  children,
}: SystemEventsProviderProps) {
  const [registry] = useState(createRegistry);
  // 연결 함수가 다시 렌더할 때 새 함수로 와도 연결을 다시 만들지 않도록 이펙트 의존성에서 뺀다.
  // StrictMode 개발 모드에서는 이펙트가 두 번 실행되어 connect가 두 번 불리고 첫 연결은 바로 닫힌다.
  const openConnection = useEffectEvent(() => connect());

  useEffect(() => {
    const source = openConnection();
    source.addEventListener("open", () => registry.notifyOpen());
    source.addEventListener(PHOTO_STATUS_CHANGED_EVENT, (event) => {
      const parsed = parsePhotoStatusChanged(event);
      if (parsed !== null) registry.notifyPhotoStatusChanged(parsed);
    });
    return () => source.close();
  }, [registry]);

  return <SystemEventsContext value={registry}>{children}</SystemEventsContext>;
}

/**
 * 시스템 이벤트를 구독한다. 콜백은 항상 마지막 렌더의 것을 부르므로 매 렌더 새 함수를 넘겨도 된다.
 * `SystemEventsProvider` 안에서만 쓴다.
 */
export function useSystemEvents({ onPhotoStatusChanged, onOpen }: SystemEventsHandlers): void {
  const registry = useContext(SystemEventsContext);
  if (registry === null) {
    throw new Error("useSystemEvents는 SystemEventsProvider 안에서만 쓸 수 있습니다");
  }
  const handlePhoto = useEffectEvent((event: PhotoStatusChangedEvent) => {
    onPhotoStatusChanged?.(event);
  });
  const handleOpen = useEffectEvent(() => {
    onOpen?.();
  });

  useEffect(
    () =>
      registry.subscribe({
        onPhotoStatusChanged: (event) => handlePhoto(event),
        onOpen: () => handleOpen(),
      }),
    [registry],
  );
}
