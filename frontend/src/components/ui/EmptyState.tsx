interface EmptyStateProps {
  title?: string;
  message?: string;
}

export function EmptyState({
  title = 'Nenhum resultado',
  message = 'Ainda nao ha nada aqui.',
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <div className="w-12 h-12 rounded-full bg-surface2 flex items-center justify-center">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="3" stroke="oklch(44% 0.006 260)" strokeWidth="1.5" />
          <path d="M8 12h8M12 8v8" stroke="oklch(44% 0.006 260)" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </div>
      <div>
        <p className="font-heading font-bold text-text-secondary text-sm">{title}</p>
        <p className="text-text-muted text-xs mt-0.5">{message}</p>
      </div>
    </div>
  );
}
