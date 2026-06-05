import type { ProgressEvent } from '../../api/types';
import { STEP_ORDER, stepIndex } from '../../hooks/useJobEvents';

const STEP_LABELS: Record<string, string> = {
  download: 'Download',
  audio: 'Audio',
  frames: 'Frames',
  ocr: 'OCR',
  ai: 'Analise IA',
  persist: 'Salvando',
  done: 'Concluido',
};

interface StepTimelineProps {
  events: ProgressEvent[];
  currentStep: string;
  status?: 'running' | 'completed' | 'failed' | 'queued' | null;
}

export function StepTimeline({ events, currentStep, status }: StepTimelineProps) {
  const normalizedCurrentStep = currentStep === 'ai_frame' ? 'ai' : currentStep;
  const currentIdx = stepIndex(normalizedCurrentStep);
  const hasFailed = status === 'failed';
  const failedEventStep = events.find((e) => e.status === 'failed')?.step ?? null;
  const failedStep = failedEventStep
    ? (failedEventStep === 'ai_frame' ? 'ai' : failedEventStep)
    : null;
  const failedIdx = failedStep ? stepIndex(failedStep) : -1;
  const completedSteps = new Set(events.map((e) => (e.step === 'ai_frame' ? 'ai' : e.step)));

  return (
    <nav aria-label="Etapas da analise">
      <ol className="flex flex-col gap-0">
        {STEP_ORDER.map((step, idx) => {
          const isCompleted = completedSteps.has(step) && idx < currentIdx && !hasFailed;
          const isCurrent = !hasFailed && (idx === currentIdx);
          const isFailedStep = failedStep === step;
          const isFuture = idx > currentIdx && !hasFailed;
          const isTerminalPastFailure = hasFailed && failedIdx >= 0 && idx > failedIdx;

          return (
            <li key={step} className="flex items-start gap-3 relative">
              {/* Linha vertical conectando os steps */}
              {idx < STEP_ORDER.length - 1 && (
                <div
                  className={[
                    'absolute left-[7px] top-5 w-px h-full -mb-1',
                    isTerminalPastFailure
                      ? 'bg-status-failed/40'
                      : isCompleted
                        ? 'bg-accent/40'
                        : 'bg-border',
                  ].join(' ')}
                />
              )}

              {/* Ponto */}
              <div
                className={[
                  'relative z-10 mt-0.5 rounded-full shrink-0 transition-all duration-[240ms]',
                  isCompleted
                    ? 'w-3.5 h-3.5 bg-accent flex items-center justify-center'
                    : isCurrent
                    ? 'w-3.5 h-3.5 bg-accent'
                    : isFailedStep
                    ? 'w-3.5 h-3.5 bg-status-failed'
                    : 'w-2 h-2 mt-1 bg-surface2 border border-border',
                  isCurrent
                    ? 'shadow-[0_0_0_4px_color-mix(in_oklch,oklch(82%_0.20_102)_20%,transparent)]'
                    : isFailedStep
                      ? 'shadow-[0_0_0_4px_color-mix(in_oklch,oklch(65%_0.20_25)_25%,transparent)]'
                      : '',
                ].join(' ')}
              >
                {isCompleted && (
                  <svg width="8" height="8" viewBox="0 0 8 8" fill="none" aria-hidden="true">
                    <path d="M1.5 4l2 2 3-3" stroke="oklch(11% 0.005 260)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
                {isFailedStep && (
                  <svg width="8" height="8" viewBox="0 0 8 8" fill="none" aria-hidden="true" className="ml-[1px]">
                    <path d="M2 2l4 4M6 2l-4 4" stroke="oklch(94% 0.005 20)" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                )}
              </div>

              {/* Label */}
              <div className="pb-4">
                <span
                  className={[
                    'text-sm font-heading font-bold leading-none',
                    isFailedStep
                      ? 'text-status-failed'
                      : hasFailed
                        ? 'text-text-muted'
                        : isCompleted
                          ? 'text-accent/70'
                          : isCurrent
                            ? 'text-accent'
                            : isFuture
                              ? 'text-text-muted'
                              : 'text-text-secondary',
                  ].join(' ')}
                >
                  {STEP_LABELS[step] ?? step}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
