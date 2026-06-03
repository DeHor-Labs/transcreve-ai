interface ClaimsListProps {
  claims: string[];
  actionItems: string[];
  questions: string[];
}

function Section({ title, items, icon }: { title: string; items: string[]; icon: string }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted mb-3">
        {icon} {title}
      </p>
      <ul className="flex flex-col gap-2">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm text-text-secondary">
            <span className="shrink-0 w-1 h-1 mt-2 rounded-full bg-accent/50" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ClaimsList({ claims, actionItems, questions }: ClaimsListProps) {
  return (
    <div className="flex flex-col gap-6">
      <Section title="Afirmacoes" items={claims} icon="" />
      <Section title="Proximos passos" items={actionItems} icon="" />
      <Section title="Perguntas levantadas" items={questions} icon="" />
    </div>
  );
}
