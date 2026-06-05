interface ErrorStateProps {
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = 'Algo deu errado',
  message = 'Tente novamente em instantes.',
  onRetry,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-4 py-16 text-center"
    >
      <div className="w-12 h-12 rounded-full bg-status-failed/10 flex items-center justify-center">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="10" stroke="oklch(65% 0.20 25)" strokeWidth="1.5" />
          <path d="M12 7v6M12 16.5v.5" stroke="oklch(65% 0.20 25)" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </div>
      <div>
        <p className="font-heading font-bold text-text-primary">{title}</p>
        <p className="text-text-muted text-sm mt-1">{message}</p>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-accent text-sm underline underline-offset-2 hover:opacity-80 transition-opacity"
        >
          Tentar novamente
        </button>
      )}
    </div>
  );
}
