import { type DragEvent, type ChangeEvent, useRef, useState } from 'react';

interface FileDropzoneProps {
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
}

const ACCEPTED = '.mp4,.mov,.mkv,.avi,.webm,.m4v,.flv';

export function FileDropzone({ file, onChange, disabled }: FileDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const f = e.dataTransfer.files[0];
    if (f) onChange(f);
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    onChange(f);
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted">
        Arquivo de video
      </span>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Selecionar arquivo de video"
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && !disabled && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={[
          'relative flex flex-col items-center justify-center gap-3',
          'min-h-[140px] rounded-md border-2 border-dashed cursor-pointer',
          'transition-all duration-[180ms] ease-out',
          disabled ? 'opacity-40 cursor-not-allowed' : '',
          dragging
            ? 'border-accent bg-accent/8'
            : file
            ? 'border-accent/50 bg-accent/5'
            : 'border-border bg-surface1 hover:border-border/60 hover:bg-surface2',
        ].join(' ')}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          onChange={handleChange}
          disabled={disabled}
          className="sr-only"
          aria-hidden="true"
          tabIndex={-1}
        />
        {file ? (
          <div className="flex flex-col items-center gap-1 text-center px-4">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"
                stroke="oklch(82% 0.20 102)" strokeWidth="1.5" />
              <path d="M14 2v6h6" stroke="oklch(82% 0.20 102)" strokeWidth="1.5" />
            </svg>
            <p className="font-heading font-bold text-sm text-text-primary truncate max-w-[200px]">
              {file.name}
            </p>
            <p className="text-text-muted text-xs">{formatSize(file.size)}</p>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onChange(null); if (inputRef.current) inputRef.current.value = ''; }}
              className="mt-1 text-xs text-text-muted hover:text-status-failed transition-colors"
            >
              Remover
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-center px-6">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="oklch(44% 0.006 260)" strokeWidth="1.5" strokeLinecap="round" />
              <polyline points="17 8 12 3 7 8" stroke="oklch(44% 0.006 260)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              <line x1="12" y1="3" x2="12" y2="15" stroke="oklch(44% 0.006 260)" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <p className="text-text-secondary text-sm">
              Arraste um arquivo ou <span className="text-accent">clique para selecionar</span>
            </p>
            <p className="text-text-muted text-xs">{ACCEPTED.replaceAll('.', '').toUpperCase()}</p>
          </div>
        )}
      </div>
    </div>
  );
}
