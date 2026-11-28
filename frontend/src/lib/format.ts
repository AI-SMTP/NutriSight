// 화면 표기용 형식 함수.

const UNIT_STEP = 1024;
const UNKNOWN = "알 수 없음";

/** 바이트 수를 B·KB·MB로 표기한다. KB·MB는 소수 첫째 자리까지, 반올림 뒤 1024가 되면 다음 단위로 올린다. */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return UNKNOWN;
  if (bytes < UNIT_STEP) return `${Math.round(bytes)} B`;
  const kb = Math.round((bytes / UNIT_STEP) * 10) / 10;
  if (kb < UNIT_STEP) return `${kb.toFixed(1)} KB`;
  return `${(bytes / UNIT_STEP / UNIT_STEP).toFixed(1)} MB`;
}

const UNKNOWN_CLOCK = "--:--";

/** ISO 시각을 기기 로컬 시각 `HH:MM`으로 표기한다. 해석할 수 없으면 `--:--`다. */
export function formatClock(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return UNKNOWN_CLOCK;
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
