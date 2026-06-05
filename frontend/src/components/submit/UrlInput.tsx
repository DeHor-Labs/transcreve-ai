import { type ChangeEvent } from 'react';

interface UrlInputProps {
  value: string;
  onChange: (val: string) => void;
  disabled?: boolean;
}

export function UrlInput({ value, onChange, disabled }: UrlInputProps) {
  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    onChange(e.target.value);
  }

  const isValid = !value || value.startsWith('http://') || value.startsWith('https://');

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor="url-input" className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted">
        URL do video
      </label>
      <input
        id="url-input"
        type="url"
        inputMode="url"
        autoComplete="url"
        value={value}
        onChange={handleChange}
        disabled={disabled}
        placeholder="https://youtube.com/watch?v=..."
        aria-describedby={!isValid ? 'url-error' : undefined}
        className={[
          'w-full px-4 py-3 rounded-md text-sm',
          'bg-surface1 border text-text-primary placeholder:text-text-muted',
          'transition-colors duration-[120ms] outline-none',
          !isValid
            ? 'border-status-failed focus:border-status-failed'
            : 'border-border focus:border-accent hover:border-border/80',
          'disabled:opacity-40 disabled:cursor-not-allowed',
        ].join(' ')}
      />
      {!isValid && (
        <p id="url-error" role="alert" className="text-status-failed text-xs">
          Informe uma URL valida comecando com http:// ou https://
        </p>
      )}
    </div>
  );
}
