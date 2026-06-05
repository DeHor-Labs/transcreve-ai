import type { ReactNode } from 'react';

interface BadgeProps {
  children: ReactNode;
  variant?: 'default' | 'accent' | 'muted';
  className?: string;
}

export function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  const variants = {
    default: 'bg-surface2 text-text-secondary border border-border',
    accent: 'bg-accent/10 text-accent border border-accent/30',
    muted: 'bg-surface1 text-text-muted border border-border',
  };
  return (
    <span
      className={[
        'inline-flex items-center px-2 py-0.5 rounded-full',
        'font-heading font-700 text-xs uppercase tracking-wide',
        variants[variant],
        className,
      ].join(' ')}
    >
      {children}
    </span>
  );
}
