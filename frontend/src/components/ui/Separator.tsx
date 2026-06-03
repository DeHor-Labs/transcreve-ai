interface SeparatorProps {
  label?: string;
  className?: string;
}

export function Separator({ label, className = '' }: SeparatorProps) {
  if (!label) {
    return (
      <hr
        className={['border-0 border-t border-border', className].join(' ')}
      />
    );
  }
  return (
    <div className={['flex items-center gap-4', className].join(' ')}>
      <hr className="flex-1 border-0 border-t border-border" />
      <span className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted whitespace-nowrap">
        {label}
      </span>
      <hr className="flex-1 border-0 border-t border-border" />
    </div>
  );
}
