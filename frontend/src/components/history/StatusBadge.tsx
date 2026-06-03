import type { JobSummary } from '../../api/types';

interface StatusBadgeProps {
  status: JobSummary['status'];
  animated?: boolean;
}

const labels: Record<JobSummary['status'], string> = {
  queued: 'Na fila',
  running: 'Processando',
  completed: 'Concluido',
  failed: 'Falhou',
};

const styles: Record<JobSummary['status'], string> = {
  queued:    'bg-status-queued/10 text-status-queued border border-status-queued/30',
  running:   'bg-status-running/10 text-status-running border border-status-running/30',
  completed: 'bg-status-completed/10 text-status-completed border border-status-completed/30',
  failed:    'bg-status-failed/10 text-status-failed border border-status-failed/30',
};

const dotColors: Record<JobSummary['status'], string> = {
  queued:    'bg-status-queued',
  running:   'bg-status-running',
  completed: 'bg-status-completed',
  failed:    'bg-status-failed',
};

export function StatusBadge({ status, animated = false }: StatusBadgeProps) {
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full',
        'font-heading font-bold text-xs uppercase tracking-wide',
        styles[status],
      ].join(' ')}
    >
      <span
        className={[
          'w-1.5 h-1.5 rounded-full shrink-0',
          dotColors[status],
          animated && status === 'running' ? 'animate-pulse' : '',
        ].join(' ')}
      />
      {labels[status]}
    </span>
  );
}
