interface EntityCloudProps {
  entities: string[];
  label: string;
  variant?: 'default' | 'accent';
}

export function EntityCloud({ entities, label, variant = 'default' }: EntityCloudProps) {
  if (entities.length === 0) {
    return <p className="text-text-muted text-sm italic">Nenhum item identificado.</p>;
  }

  const tagBase = 'inline-flex items-center px-2.5 py-1 rounded-full text-xs transition-all duration-[120ms]';
  const tagStyle =
    variant === 'accent'
      ? 'bg-accent/8 text-accent border border-accent/20 hover:border-accent/50 hover:bg-accent/15'
      : 'bg-surface2 text-text-secondary border border-border hover:border-accent/40 hover:text-accent';

  return (
    <div>
      <p className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted mb-3">
        {label}
      </p>
      <div className="flex flex-wrap gap-2" role="list" aria-label={label}>
        {entities.map((entity, i) => (
          <span key={i} role="listitem" className={[tagBase, tagStyle].join(' ')}>
            {entity}
          </span>
        ))}
      </div>
    </div>
  );
}
