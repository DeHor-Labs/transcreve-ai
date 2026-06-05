interface Chapter {
  title: string;
  start: number;
  end: number;
}

interface ChapterListProps {
  chapters: Chapter[];
}

function formatTime(secs: number): string {
  const total = Math.max(0, Math.floor(secs));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function ChapterList({ chapters }: ChapterListProps) {
  if (chapters.length === 0) {
    return <p className="text-text-muted text-sm italic">Nenhum capítulo detectado.</p>;
  }

  return (
    <ol className="flex flex-col gap-2">
      {chapters.map((ch, i) => (
        <li key={i} className="flex items-start gap-3 group">
          <span className="shrink-0 font-heading font-bold text-xs text-accent/60 min-w-[40px] pt-0.5">
            {formatTime(ch.start)}
          </span>
          <span className="text-sm text-text-secondary group-hover:text-text-primary transition-colors">
            {ch.title}
          </span>
          <span className="ml-auto shrink-0 text-xs text-text-muted">
            {formatTime(ch.end)}
          </span>
        </li>
      ))}
    </ol>
  );
}
