import { useEffect, useMemo, useState } from 'react';
import { useSubmitJob } from '../../hooks/useSubmitJob';
import { useSourceProbe } from '../../hooks/useSourceProbe';
import { isApiError } from '../../api/client';
import { Button } from '../ui/Button';
import { UrlInput } from './UrlInput';
import { FileDropzone } from './FileDropzone';
import type { SourceProbeResponse } from '../../api/types';

type Tab = 'url' | 'file';
type AiMode = 'auto' | 'off' | 'full';
type Provider = 'openai' | 'gemini' | 'anthropic' | 'local';

function isHttpUrl(value: string): boolean {
  return value.startsWith('http://') || value.startsWith('https://');
}

function collectProbeWarnings(
  probe: SourceProbeResponse | null,
  probeRequestError: string | null,
): string[] {
  if (!probe && !probeRequestError) return [];

  const warnings: string[] = [];

  if (probe) {
    const kind = probe.kind.toLowerCase();
    const adapter = probe.adapter.toLowerCase();
    const notes = probe.notes.join(' ').toLowerCase();

    if (kind === 'unknown' || kind.includes('unknown')) {
      warnings.push('Fonte desconhecida - envio continua pelo fluxo de fallback.');
    }

    if (probe.requires_cookies) {
      warnings.push('Esta fonte pode exigir cookies ou autenticacao para extracao completa.');
    }

    if (adapter.includes('fallback') || notes.includes('fallback')) {
      warnings.push('Fonte marcada para fallback automatico.');
    }
  }

  if (probeRequestError) {
    warnings.push(probeRequestError);
  }

  return warnings;
}

export function SubmitForm() {
  const [tab, setTab] = useState<Tab>('url');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [aiMode, setAiMode] = useState<AiMode>('auto');
  const [provider, setProvider] = useState<Provider>('openai');
  const [language, setLanguage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const { result: sourceProbe, isProbing: isProbingSource, error: sourceProbeError, probe: runSourceProbe, clear: clearSourceProbe } = useSourceProbe();
  const isProbeMode = tab === 'url' && isHttpUrl(url);

  const submit = useSubmitJob();

  useEffect(() => {
    if (!isProbeMode) {
      clearSourceProbe();
      return;
    }

    clearSourceProbe();
    const timer = window.setTimeout(() => {
      void runSourceProbe(url);
    }, 450);

    return () => {
      window.clearTimeout(timer);
    };
  }, [isProbeMode, tab, url, runSourceProbe, clearSourceProbe]);

  const isValid =
    tab === 'url'
      ? isHttpUrl(url)
      : file !== null;

  const probeWarnings = useMemo(
    () => collectProbeWarnings(sourceProbe, sourceProbeError),
    [sourceProbe, sourceProbeError],
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (tab === 'url') {
        await submit.mutateAsync({
          type: 'url',
          payload: { source: url, ai_mode: aiMode, provider, language: language || undefined },
        });
      } else if (file) {
        await submit.mutateAsync({
          type: 'file',
          file,
          opts: { ai_mode: aiMode, provider, language: language || undefined },
        });
      }
    } catch (err) {
      if (isApiError(err) && err.status === 409) {
        const body = err.body as { existing_run_id?: string };
        setError(`Esse video ja foi analisado. ID: ${body.existing_run_id ?? ''}`);
      } else if (isApiError(err)) {
        const body = err.body as { message?: string };
        setError(body?.message ?? 'Erro ao submeter. Tente novamente.');
      } else {
        setError('Erro inesperado. Verifique a conexao.');
      }
    }
  }

  return (
    <form
      onSubmit={(e) => void handleSubmit(e)}
      noValidate
      aria-label="Formulario de submissao de video"
    >
      {/* Tabs URL / Upload */}
      <div role="tablist" aria-label="Tipo de entrada" className="flex gap-0 mb-6 border-b border-border">
        {(['url', 'file'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            onClick={() => { setTab(t); setError(null); }}
            className={[
              'px-5 py-2.5 font-heading font-bold text-sm transition-all duration-[120ms] relative',
              tab === t
                ? 'text-text-primary'
                : 'text-text-muted hover:text-text-secondary',
            ].join(' ')}
          >
            {t === 'url' ? 'Link' : 'Arquivo'}
            {tab === t && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent rounded-t-full" />
            )}
          </button>
        ))}
      </div>

      <div role="tabpanel" className="flex flex-col gap-5">
        {tab === 'url' ? (
          <UrlInput value={url} onChange={setUrl} disabled={submit.isPending} />
        ) : (
          <FileDropzone file={file} onChange={setFile} disabled={submit.isPending} />
        )}

        {tab === 'url' && (isProbingSource || sourceProbe || sourceProbeError) && (
          <div className="rounded-md border border-border bg-surface2 px-3 py-2 text-xs text-text-muted space-y-1">
            {isProbingSource ? (
              <p className="text-text-secondary">Verificando fonte...</p>
            ) : (
              <>
                {sourceProbe && (
                  <p className="text-text-secondary">
                    Fonte: <span className="text-text-primary">{sourceProbe.adapter}</span>
                    <span className="text-text-muted"> • </span>
                    <span className="uppercase">{sourceProbe.kind}</span>
                  </p>
                )}

                {(sourceProbe?.canonical || sourceProbe?.source) && (
                  <p className="text-text-muted break-all">
                    Canonical: {sourceProbe.canonical || sourceProbe.source}
                  </p>
                )}
              </>
            )}

            {probeWarnings.length > 0 && (
              <ul className="flex flex-col gap-1 pt-1 border-t border-border/80 mt-1.5">
                {probeWarnings.map((note) => (
                  <li key={note} className="flex items-start gap-1.5">
                    <span className="text-status-failed font-heading font-bold">Aviso:</span>
                    <span className="text-status-failed">{note}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Opcoes avancadas */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ai-mode" className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted">
              Modo IA
            </label>
            <select
              id="ai-mode"
              value={aiMode}
              onChange={(e) => setAiMode(e.target.value as AiMode)}
              disabled={submit.isPending}
              className="px-3 py-2 rounded bg-surface1 border border-border text-text-primary text-sm outline-none focus:border-accent hover:border-border/80 transition-colors disabled:opacity-40"
            >
              <option value="auto">Auto</option>
              <option value="full">Completo</option>
              <option value="off">Desativado</option>
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="provider" className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted">
              Provider
            </label>
            <select
              id="provider"
              value={provider}
              onChange={(e) => setProvider(e.target.value as Provider)}
              disabled={submit.isPending}
              className="px-3 py-2 rounded bg-surface1 border border-border text-text-primary text-sm outline-none focus:border-accent hover:border-border/80 transition-colors disabled:opacity-40"
            >
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
              <option value="anthropic">Anthropic</option>
              <option value="local">Local</option>
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="language" className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted">
              Idioma
            </label>
            <input
              id="language"
              type="text"
              placeholder="pt, en..."
              maxLength={5}
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              disabled={submit.isPending}
              className="px-3 py-2 rounded bg-surface1 border border-border text-text-primary text-sm outline-none focus:border-accent hover:border-border/80 transition-colors placeholder:text-text-muted disabled:opacity-40"
            />
          </div>
        </div>

        {error && (
          <p role="alert" className="text-sm text-status-failed bg-status-failed/10 border border-status-failed/30 px-4 py-3 rounded-md">
            {error}
          </p>
        )}

        <Button
          type="submit"
          size="lg"
          loading={submit.isPending}
          disabled={!isValid}
        >
          {submit.isPending ? 'Analisando...' : 'Analisar video'}
        </Button>
      </div>
    </form>
  );
}
