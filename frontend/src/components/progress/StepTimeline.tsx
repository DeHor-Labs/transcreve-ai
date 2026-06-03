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
}

export function StepTimeline({ events, currentStep }: StepTimelineProps) {
  const currentIdx = stepIndex(currentStep);
  const completedSteps = new Set(events.map((e) => e.step === 'ai_frame' ? 'ai' : e.step));

  return (
    <nav aria-label="Etapas da analise">
      <ol className="flex flex-col gap-0">
        {STEP_ORDER.map((step, idx) => {
          const isCompleted = completedSteps.has(step) && idx < currentIdx;
          const isCurrent = idx === currentIdx || (step === 'ai' && currentStep === 'ai_frame');
          const isFuture = idx > currentIdx;

          return (
            <li key={step} className="flex items-start gap-3 relative">
              {/* Linha vertical conectando os steps */}
              {idx < STEP_ORDER.length - 1 && (
                <div
                  className={[
                    'absolute left-[7px] top-5 w-px h-full -mb-1',
                    isCompleted ? 'bg-accent/40' : 'bg-border',
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
                    : 'w-2 h-2 mt-1 bg-surface2 border border-border',
                  isCurrent ? 'shadow-[0_0_0_4px_color-mix(in_oklch,oklch(82%_0.20_102)_20%,transparent)]' : '',
                ].join(' ')}
              >
                {isCompleted && (
                  <svg width="8" height="8" viewBox="0 0 8 8" fill="none" aria-hidden="true">
                    <path d="M1.5 4l2 2 3-3" stroke="oklch(11% 0.005 260)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>

              {/* Label */}
              <div className="pb-4">
                <span
                  className={[
                    'text-sm font-heading font-bold leading-none',
                    isCompleted ? 'text-accent/70' : isCurrent ? 'text-accent' : isFuture ? 'text-text-muted' : 'text-text-secondary',
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
