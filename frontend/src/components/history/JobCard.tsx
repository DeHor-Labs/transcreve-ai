import { useNavigate } from 'react-router-dom';
import type { JobSummary } from '../../api/types';
import { StatusBadge } from './StatusBadge';

interface JobCardProps {
  job: JobSummary;
}

function formatDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat('pt-BR', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function formatDuration(secs: number | null): string {
  if (!secs) return '';
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function shortSource(src: string): string {
  if (src.startsWith('http')) {
    try {
      const url = new URL(src);
      return url.hostname + url.pathname.slice(0, 40);
    } catch {
      return src.slice(0, 60);
    }
  }
  const parts = src.split('/');
  return parts[parts.length - 1] ?? src;
}

export function JobCard({ job }: JobCardProps) {
  const navigate = useNavigate();
  const title = job.title || shortSource(job.source);
  const isActive = job.status === 'running' || job.status === 'queued';

  return (
    <article
      role="button"
      tabIndex={0}
      aria-label={`Ver job: ${title}`}
      onClick={() => navigate(`/jobs/${job.job_id}`)}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/jobs/${job.job_id}`)}
      className={[
        'group relative flex items-start gap-4 p-4 rounded-lg cursor-pointer',
        'bg-surface1 border border-border',
        'transition-all duration-[240ms] ease-out',
        'hover:-translate-y-0.5 hover:bg-surface2 hover:border-border/80',
        'hover:shadow-[0_4px_20px_oklch(0%_0_0/0.3)]',
        'focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2',
      ].join(' ')}
    >
      {/* Status indicator line */}
      <div
        className={[
          'absolute left-0 top-3 bottom-3 w-0.5 rounded-full transition-opacity',
          job.status === 'completed' ? 'bg-status-completed opacity-60' : '',
          job.status === 'running' ? 'bg-status-running opacity-80' : '',
          job.status === 'failed' ? 'bg-status-failed opacity-60' : '',
          job.status === 'queued' ? 'bg-status-queued opacity-40' : '',
        ].join(' ')}
      />

      <div className="flex-1 min-w-0 pl-2">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-heading font-bold text-sm text-text-primary truncate leading-snug">
            {title}
          </h3>
          <StatusBadge status={job.status} animated={isActive} />
        </div>

        <p className="text-text-muted text-xs mt-1 truncate">
          {shortSource(job.source)}
        </p>

        {/* Progress bar para jobs em andamento */}
        {isActive && job.progress && (
          <div className="mt-2.5 space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-secondary">{job.progress.detail}</span>
              <span className="text-xs font-heading font-bold text-accent">{job.progress.pct}%</span>
            </div>
            <div className="h-0.5 bg-surface2 rounded-full overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-all duration-[400ms] ease-out"
                style={{ width: `${job.progress.pct}%` }}
              />
            </div>
          </div>
        )}

        <div className="flex items-center gap-3 mt-2">
          <span className="text-text-muted text-xs">{formatDate(job.created_at)}</span>
          {job.duration_seconds && (
            <span className="text-text-muted text-xs">
              {formatDuration(job.duration_seconds)}
            </span>
          )}
          {job.provider && (
            <span className="text-text-muted text-xs uppercase tracking-wide font-heading">
              {job.provider}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}
