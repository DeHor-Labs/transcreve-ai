import type { ProgressEvent } from '../../api/types';

interface LiveStepProps {
  event: ProgressEvent;
}

export function LiveStep({ event }: LiveStepProps) {
  const isFailed = event.status === 'failed';
  return (
    <div className="flex items-start gap-3">
      <div
        className={[
          'mt-0.5 w-2 h-2 rounded-full shrink-0',
          isFailed ? 'bg-status-failed' : 'bg-accent pulse-ring',
        ].join(' ')}
      />
      <div className="flex-1 min-w-0">
        <p
          className={[
            'text-sm',
            isFailed ? 'text-status-failed' : 'text-text-primary',
          ].join(' ')}
        >
          {event.detail}
        </p>
      </div>
      <span className="font-heading font-bold text-accent text-xl leading-none shrink-0">
        {event.pct}%
      </span>
    </div>
  );
}
