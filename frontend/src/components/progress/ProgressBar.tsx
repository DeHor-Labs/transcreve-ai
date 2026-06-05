interface ProgressBarProps {
  pct: number;
  className?: string;
}

export function ProgressBar({ pct, className = '' }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <div
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Progresso da analise"
      className={['relative h-1 bg-surface2 rounded-full overflow-hidden', className].join(' ')}
    >
      <div
        className="absolute inset-y-0 left-0 bg-accent rounded-full transition-[width] duration-[400ms] ease-out"
        style={{ width: `${clamped}%` }}
      >
        {/* brilho na ponta */}
        <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-r from-transparent to-white/20 rounded-full" />
      </div>
    </div>
  );
}
