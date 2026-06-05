import {
  type ChangeEvent,
  type DragEvent,
  type KeyboardEvent,
  useRef,
  useState,
} from 'react';

interface FileDropzoneProps {
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
}

const ACCEPTED_EXTENSIONS = ['.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.flv'];
const ACCEPTED_TYPES = new Set([
  'video/mp4',
  'video/quicktime',
  'video/x-matroska',
  'video/x-msvideo',
  'video/webm',
  'video/x-m4v',
  'video/x-flv',
]);
const MAX_UPLOAD_BYTES = 1024 * 1024 * 1024;
const ACCEPTED_DESCRIPTION = ACCEPTED_EXTENSIONS.join(', ').toUpperCase();

export function FileDropzone({ file, onChange, disabled }: FileDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = 'video-upload-input';
  const errorId = `${inputId}-error`;

  function normalizeExtension(fileName: string): string {
    const cleanName = fileName.trim().toLowerCase();
    const index = cleanName.lastIndexOf('.');
    return index === -1 ? '' : cleanName.slice(index);
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function getValidationError(candidate: File): string | null {
    const extension = normalizeExtension(candidate.name);
    if (!candidate.size) {
      return 'Arquivo vazio. Escolha um arquivo de video valido.';
    }
    if (!ACCEPTED_EXTENSIONS.includes(extension) && !ACCEPTED_TYPES.has(candidate.type)) {
      return `Formato invalido. Utilize apenas: ${ACCEPTED_DESCRIPTION}`;
    }
    if (candidate.size > MAX_UPLOAD_BYTES) {
      return 'Arquivo acima de 1GB, acima do limite permitido.';
    }
    return null;
  }

  async function hasAvailableSpaceFor(candidate: File): Promise<boolean> {
    if (!('storage' in navigator) || !navigator.storage || !navigator.storage.estimate) {
      return true;
    }
    try {
      const estimate = await navigator.storage.estimate();
      if (estimate.quota == null || estimate.usage == null) return true;
      return candidate.size < estimate.quota - estimate.usage;
    } catch {
      return true;
    }
  }

  async function applyCandidate(candidate: File | null) {
    if (!candidate) {
      setValidationError(null);
      onChange(null);
      return;
    }

    const validation = getValidationError(candidate);
    if (validation !== null) {
      setValidationError(validation);
      onChange(null);
      if (inputRef.current) inputRef.current.value = '';
      return;
    }

    setIsValidating(true);
    const hasSpace = await hasAvailableSpaceFor(candidate);
    setIsValidating(false);
    if (!hasSpace) {
      setValidationError('Espaco insuficiente para processar esse arquivo.');
      onChange(null);
      if (inputRef.current) inputRef.current.value = '';
      return;
    }

    setValidationError(null);
    onChange(candidate);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    void applyCandidate(e.dataTransfer.files[0] ?? null);
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    void applyCandidate(e.target.files?.[0] ?? null);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (disabled || isValidating) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      inputRef.current?.click();
    }
  }

  function clearSelection() {
    setValidationError(null);
    onChange(null);
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted">
        Arquivo de video
      </label>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Selecionar arquivo de video"
        aria-describedby={validationError ? errorId : undefined}
        onClick={() => !disabled && !isValidating && inputRef.current?.click()}
        onKeyDown={handleKeyDown}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={[
          'relative flex flex-col items-center justify-center gap-3',
          'min-h-[140px] rounded-md border-2 border-dashed cursor-pointer',
          'transition-all duration-[180ms] ease-out',
          disabled || isValidating ? 'opacity-40 cursor-not-allowed' : '',
          dragging
            ? 'border-accent bg-accent/8'
            : file
              ? 'border-accent/50 bg-accent/5'
              : 'border-border bg-surface1 hover:border-border/60 hover:bg-surface2',
        ].join(' ')}
      >
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(',')}
          onChange={handleChange}
          disabled={disabled || isValidating}
          className="sr-only"
          aria-hidden="true"
          tabIndex={-1}
        />
        {file ? (
          <div className="flex flex-col items-center gap-1 text-center px-4">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6z"
                stroke="oklch(82% 0.20 102)"
                strokeWidth="1.5"
              />
              <path d="M14 2v6h6" stroke="oklch(82% 0.20 102)" strokeWidth="1.5" />
            </svg>
            <p className="font-heading font-bold text-sm text-text-primary truncate max-w-[200px]">
              {file.name}
            </p>
            <p className="text-text-muted text-xs">{formatSize(file.size)}</p>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                clearSelection();
              }}
              disabled={disabled}
              className="mt-1 text-xs text-text-muted hover:text-status-failed transition-colors"
            >
              Remover
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-center px-6">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"
                stroke="oklch(44% 0.006 260)"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
              <polyline
                points="17 8 12 3 7 8"
                stroke="oklch(44% 0.006 260)"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <line
                x1="12"
                y1="3"
                x2="12"
                y2="15"
                stroke="oklch(44% 0.006 260)"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
            <p className="text-text-secondary text-sm">
              Arraste um arquivo ou <span className="text-accent">clique para selecionar</span>
            </p>
            <p className="text-text-muted text-xs">{ACCEPTED_DESCRIPTION}</p>
            <p className="text-text-muted text-xs">Limite: 1GB</p>
          </div>
        )}
        {validationError && (
          <p
            id={errorId}
            role="alert"
            className="text-status-failed text-xs text-center px-4"
          >
            {validationError}
          </p>
        )}
        {isValidating && <p className="text-text-muted text-xs">Validando arquivo...</p>}
      </div>
    </div>
  );
}
