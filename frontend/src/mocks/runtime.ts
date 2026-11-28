/**
 * 모의 처리 단계 런타임. 식후 사진 작업을 단계 타이머로 진행하고, 단계마다 `mockState`를 바꾸며
 * 모의 이벤트 버스에 `photo.status_changed`를 발행한다. 기준 사진 등록·교체 때 재처리 규칙을 적용한다.
 *
 * - 정본: `docs/specs/frontend-shell-upload.md` 'MSW 처리 단계'·'기준 사진 교체와 재분석 예약'(처리 단계·기준 사진 규칙·이벤트),
 *   'finishAll과 reset'(E2E 단계 제어와 `finishAll()` 계약).
 * - 작업(job)은 단계 진행 중인 식후 사진 하나다. `waiting_baseline` 사진은 작업이 아니다(기준 사진 등록 때 시작).
 * - 수동 모드(`manualSteps`)는 매 처리의 첫 `analyzing(intake)`에서 멈춘다. `finishAll()`은 정지 여부와
 *   무관하게 호출 시점의 작업 전부를 재분석 예약까지 끝낸다.
 * - `mockState.reset()` 때 타이머를 모두 취소한다(사진 번호가 다시 쓰여도 이전 타이머가 새 사진을 건드리지 않게).
 * - 브라우저 API(`window`, `msw/browser`)를 쓰지 않는다. 전역 노출은 브라우저 부트스트랩이 맡는다.
 */
import { eventBus } from "./eventBus";
import { findPhoto } from "./operations";
import {
  applyStep,
  baselineEvent,
  isManualStop,
  isTerminal,
  nextStep,
  postPhotoEvent,
  QUEUED,
  reprocessTargets,
  type MockResult,
  type Step,
} from "./pipeline";
import { mockState } from "./state";
import type { MockPhoto } from "./types";

export type { MockResult } from "./pipeline";

/** 기본 단계 간격(ms). 화면에서 "처리 중"을 볼 수 있을 만큼 둔다 */
export const DEFAULT_STEP_DELAY_MS = 800;

/**
 * 단계를 사실상 진행하지 않는 간격(ms). `setTimeout`이 받는 최댓값(2^31 - 1, 약 24.8일)이다.
 * 이보다 크면 타이머 구현이 1ms로 바꿔 곧바로 실행되므로 `Infinity`를 쓰지 않는다.
 */
export const HOLD_STEP_DELAY_MS = 2_147_483_647;

export interface MockRuntimeOptions {
  /** 단계 간격(ms). 테스트는 0 */
  stepDelayMs?: number;
  /** 참이면 처리마다 첫 `analyzing(intake)`에서 멈춘다(`finishAll()`로 마저 진행) */
  manualSteps?: boolean;
  /** 사진별 처리 결과 주입 지점(테스트용). 기본은 모두 `done` */
  resolveResult?: (photo: MockPhoto) => MockResult;
  /** 이벤트 `at` 시각 */
  now?: () => string;
}

export interface MockRuntime {
  /** 식후 사진 접수 직후. 지금 상태로 이벤트를 내고 `uploaded`면 처리를 시작한다 */
  photoAccepted(photoId: string): void;
  /** 기준 사진 저장 직후. `replaced`는 이미 기준 사진이 있던 끼니에 다시 등록했는지 */
  baselineRegistered(args: { photoId: string; replaced: boolean }): void;
  /** 호출 시점의 작업 전부를 종료 상태까지(재분석 예약 포함) 진행한다 */
  finishAll(): void;
  /** 타이머를 취소하고 reset 정리 콜백을 해제한다 */
  dispose(): void;
}

interface Job {
  readonly timer: ReturnType<typeof setTimeout> | null;
  /** 지금 처리가 끝나면 `queued`부터 한 번 더 처리한다(기준 사진 교체) */
  readonly reanalyze: boolean;
}

/** 진행 중인 작업 표. 갱신은 새 Map으로 바꿔 넣는다 */
class JobTable {
  private jobs: ReadonlyMap<string, Job> = new Map();

  get(photoId: string): Job | undefined {
    return this.jobs.get(photoId);
  }

  ids(): string[] {
    return [...this.jobs.keys()];
  }

  set(photoId: string, job: Job | null): void {
    const next = new Map(this.jobs);
    if (job) next.set(photoId, job);
    else next.delete(photoId);
    this.jobs = next;
  }

  /** 걸린 단계 타이머를 취소한다(작업은 남긴다) */
  cancelTimer(photoId: string): void {
    const job = this.jobs.get(photoId);
    if (!job) return;
    if (job.timer) clearTimeout(job.timer);
    this.set(photoId, { ...job, timer: null });
  }

  /** 타이머를 모두 취소하고 작업을 비운다 */
  clear(): void {
    for (const job of this.jobs.values()) {
      if (job.timer) clearTimeout(job.timer);
    }
    this.jobs = new Map();
  }
}

class Runtime implements MockRuntime {
  private readonly jobs = new JobTable();
  private readonly stepDelayMs: number;
  private readonly manualSteps: boolean;
  private readonly resolveResult: (photo: MockPhoto) => MockResult;
  private readonly now: () => string;
  private readonly stopListeningReset: () => void;

  constructor(options: MockRuntimeOptions) {
    this.stepDelayMs = options.stepDelayMs ?? DEFAULT_STEP_DELAY_MS;
    this.manualSteps = options.manualSteps ?? false;
    this.resolveResult = options.resolveResult ?? (() => "done");
    this.now = options.now ?? (() => new Date().toISOString());
    this.stopListeningReset = mockState.onReset(() => this.jobs.clear());
  }

  photoAccepted(photoId: string): void {
    const photo = currentPhoto(photoId);
    if (!photo) return;
    eventBus.publish(postPhotoEvent(mockState.get(), photo, this.now()));
    if (photo.status === "uploaded") this.start(photoId, false);
  }

  baselineRegistered({ photoId, replaced }: { photoId: string; replaced: boolean }): void {
    const baseline = currentPhoto(photoId);
    if (!baseline) return;
    eventBus.publish(baselineEvent(baseline, this.now()));
    const targets = reprocessTargets(mockState.get(), baseline.meal_plan_id, replaced);
    for (const id of targets.restart) {
      this.move(id, QUEUED);
      this.start(id, false);
    }
    for (const id of targets.reserve) {
      const job = this.jobs.get(id);
      if (job) this.jobs.set(id, { ...job, reanalyze: true });
      else this.start(id, true);
    }
  }

  finishAll(): void {
    for (const photoId of this.jobs.ids()) {
      let running = true;
      while (running) {
        // 단계마다 걸린 타이머를 먼저 취소해 같은 단계 이벤트가 두 번 나가지 않게 한다.
        this.jobs.cancelTimer(photoId);
        running = this.advance(photoId);
      }
    }
  }

  dispose(): void {
    this.jobs.clear();
    this.stopListeningReset();
  }

  /** 사진을 한 단계 옮기고(발주 `record_status` 포함) 이벤트를 낸다 */
  private move(photoId: string, step: Step): void {
    const state = mockState.update((s) => applyStep(s, photoId, step));
    const photo = findPhoto(state, photoId);
    if (photo) eventBus.publish(postPhotoEvent(state, photo, this.now()));
  }

  /** 작업을 한 단계 진행한다. 작업이 이어지면 참, 끝났으면 거짓 */
  private advance(photoId: string): boolean {
    const job = this.jobs.get(photoId);
    const photo = currentPhoto(photoId);
    const step = photo ? nextStep(photo, this.resolveResult(photo)) : null;
    if (!job || !step) {
      this.jobs.set(photoId, null);
      return false;
    }
    this.move(photoId, step);
    // 이벤트 발행 중 구독자가 작업을 바꿨을 수 있으므로(기준 사진 교체로 재시작 등) 다시 읽는다.
    // 다른 경로가 작업을 새로 걸었으면 그 작업에 맡긴다.
    const current = this.jobs.get(photoId);
    if (current !== job) return current !== undefined;
    if (!isTerminal(step.status)) return true;
    if (!current.reanalyze) {
      this.jobs.set(photoId, null);
      return false;
    }
    // 재분석 예약: 지금 처리가 끝났으므로 새 기준으로 `queued`부터 한 번 더 처리한다.
    this.jobs.set(photoId, { timer: null, reanalyze: false });
    this.move(photoId, QUEUED);
    return true;
  }

  /** 다음 단계 타이머를 건다. 수동 모드 정지 지점이면 걸지 않는다 */
  private schedule(photoId: string): void {
    const job = this.jobs.get(photoId);
    const photo = currentPhoto(photoId);
    if (!job || !photo || (this.manualSteps && isManualStop(photo))) return;
    // 이미 걸린 타이머가 있으면(발행 중 재시작 등) 바꿔 걸어 같은 단계가 두 번 나가지 않게 한다.
    if (job.timer) clearTimeout(job.timer);
    const timer = setTimeout(() => {
      this.jobs.cancelTimer(photoId);
      if (this.advance(photoId)) this.schedule(photoId);
    }, this.stepDelayMs);
    this.jobs.set(photoId, { ...job, timer });
  }

  private start(photoId: string, reanalyze: boolean): void {
    this.jobs.cancelTimer(photoId);
    this.jobs.set(photoId, { timer: null, reanalyze });
    this.schedule(photoId);
  }
}

function currentPhoto(photoId: string): MockPhoto | undefined {
  return findPhoto(mockState.get(), photoId);
}

export function createMockRuntime(options: MockRuntimeOptions = {}): MockRuntime {
  return new Runtime(options);
}

let active: MockRuntime | null = null;

/** 핸들러가 쓸 런타임을 새로 만든다. 이전 런타임은 정리한다(부트스트랩·테스트가 옵션을 정할 때) */
export function installMockRuntime(options: MockRuntimeOptions = {}): MockRuntime {
  active?.dispose();
  active = createMockRuntime(options);
  return active;
}

/** 핸들러가 쓰는 현재 런타임. 설치 전이면 기본 옵션으로 만든다 */
export function currentMockRuntime(): MockRuntime {
  return active ?? installMockRuntime();
}
