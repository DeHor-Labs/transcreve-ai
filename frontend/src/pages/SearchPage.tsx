import { type FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { askKnowledge, searchKnowledge } from '../api/search';
import type { AskResponse, SearchResponse, SearchResult } from '../api/search';
import { isApiError } from '../api/client';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorState } from '../components/ui/ErrorState';
import { Spinner } from '../components/ui/Spinner';

// ---------------------------------------------------------------------------
// Tipos de estado da pagina
// ---------------------------------------------------------------------------

type PageState =
  | { tag: 'idle' }
  | { tag: 'loading' }
  | { tag: 'error'; message: string }
  | { tag: 'results-search'; data: SearchResponse }
  | { tag: 'results-ask'; data: AskResponse };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CHUNK_TYPE_LABELS: Record<string, string> = {
  summary: 'resumo',
  chapter: 'capitulo',
  entity: 'entidades',
  transcript: 'transcricao',
};

function chunkLabel(type: string): string {
  return CHUNK_TYPE_LABELS[type] ?? type;
}

function chunkVariant(type: string): 'default' | 'accent' | 'muted' {
  if (type === 'summary') return 'accent';
  if (type === 'chapter') return 'default';
  return 'muted';
}

function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function formatChapterTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function extractErrorMessage(err: unknown): string {
  if (isApiError(err)) {
    const body = err.body as Record<string, unknown> | null;
    if (body && typeof body.message === 'string') return body.message;
    if (err.status === 503)
      return 'Provider nao suporta busca semantica. Configure um provider com suporte a embeddings (openai, local ou gemini).';
    return `Erro ${err.status}`;
  }
  if (err instanceof Error) return err.message;
  return 'Erro desconhecido';
}

// ---------------------------------------------------------------------------
// Componente de card de resultado
// ---------------------------------------------------------------------------

function ResultCard({ hit }: { hit: SearchResult }) {
  return (
    <article className="rounded-xl border border-border bg-surface2 p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <Link
          to={`/jobs/${hit.run_id}`}
          className="text-sm font-heading font-700 text-accent hover:underline truncate max-w-xs"
        >
          {hit.title || hit.run_id}
        </Link>
        <div className="flex items-center gap-2 shrink-0">
          <Badge variant={chunkVariant(hit.chunk_type)}>
            {chunkLabel(hit.chunk_type)}
          </Badge>
          <span className="text-xs text-text-secondary font-mono tabular-nums">
            {formatScore(hit.score)}
          </span>
        </div>
      </div>

      <p className="text-sm text-text-secondary leading-relaxed line-clamp-3">
        {hit.excerpt}
      </p>

      {hit.chapter_start != null && (
        <span className="text-xs text-text-muted">
          capitulo em {formatChapterTime(hit.chapter_start)}
        </span>
      )}
    </article>
  );
}

// ---------------------------------------------------------------------------
// SearchPage
// ---------------------------------------------------------------------------

export function SearchPage() {
  const [query, setQuery] = useState('');
  const [generateAnswer, setGenerateAnswer] = useState(false);
  const [state, setState] = useState<PageState>({ tag: 'idle' });

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    setState({ tag: 'loading' });

    try {
      if (generateAnswer) {
        const data = await askKnowledge(q);
        setState({ tag: 'results-ask', data });
      } else {
        const data = await searchKnowledge(q);
        setState({ tag: 'results-search', data });
      }
    } catch (err) {
      setState({ tag: 'error', message: extractErrorMessage(err) });
    }
  }

  const isLoading = state.tag === 'loading';

  return (
    <div className="min-h-dvh bg-[var(--color-bg)]">
      {/* Header global */}
      <header className="sticky top-0 z-10 border-b border-border bg-[var(--color-bg)]/95 backdrop-blur-sm">
        <div className="max-w-[860px] mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <Link
            to="/"
            className="font-heading font-bold text-lg text-text-primary hover:opacity-100"
            aria-label="TranscreveAI - pagina inicial"
          >
            Transcreve<span className="text-accent">AI</span>
          </Link>
          <nav aria-label="Navegacao principal" className="flex items-center gap-5">
            <Link
              to="/search"
              aria-current="page"
              className="text-accent text-sm font-heading"
            >
              Buscar
            </Link>
            <a
              href="/#historico"
              className="text-text-muted text-sm hover:text-text-primary transition-colors font-heading"
            >
              Historico
            </a>
          </nav>
        </div>
      </header>

    <main className="max-w-3xl mx-auto px-4 py-10 flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-heading font-700 text-text-primary">
          Busca semantica
        </h1>
        <p className="text-sm text-text-secondary">
          Pesquise nos videos indexados por conteudo, trechos e capitulos.
        </p>
      </div>

      {/* Formulario */}
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4"
        aria-label="Formulario de busca semantica"
      >
        <label htmlFor="search-query" className="sr-only">
          Consulta
        </label>
        <textarea
          id="search-query"
          name="search-query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="O que foi dito sobre...?"
          rows={3}
          aria-describedby="search-help"
          className={[
            'w-full rounded-xl border border-border bg-surface2',
            'px-4 py-3 text-sm text-text-primary placeholder:text-text-muted',
            'resize-none focus:outline-none focus:ring-2 focus:ring-accent/40',
          ].join(' ')}
        />
        <p id="search-help" className="sr-only">
          Digite o texto para buscar por trechos ou contexto no seu historico.
        </p>

        <div className="flex items-center justify-between gap-4 flex-wrap">
          <label
            htmlFor="search-generate-answer"
            className="flex items-center gap-2 cursor-pointer select-none"
          >
            <input
              id="search-generate-answer"
              type="checkbox"
              checked={generateAnswer}
              onChange={(e) => setGenerateAnswer(e.target.checked)}
              className="w-4 h-4 accent-accent rounded"
            />
            <span className="text-sm text-text-secondary">Gerar resposta com IA</span>
          </label>

          <Button type="submit" disabled={isLoading || !query.trim()}>
            {isLoading ? <Spinner size="sm" /> : null}
            {isLoading ? 'Buscando...' : 'Buscar'}
          </Button>
        </div>
      </form>

      {/* Estados de resultado */}
      {state.tag === 'loading' && (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      )}

      {state.tag === 'error' && (
        <ErrorState message={state.message} />
      )}

      {state.tag === 'results-search' && state.data.total === 0 && (
        <EmptyState message="Nenhum trecho encontrado para essa busca. Tente outros termos ou indexe mais videos." />
      )}

      {state.tag === 'results-search' && state.data.total > 0 && (
        <section className="flex flex-col gap-4">
          <p className="text-xs text-text-muted">
            {state.data.total} trecho{state.data.total !== 1 ? 's' : ''} encontrado{state.data.total !== 1 ? 's' : ''}
          </p>
          {state.data.results.map((hit, i) => (
            <ResultCard key={`${hit.run_id}-${i}`} hit={hit} />
          ))}
        </section>
      )}

      {state.tag === 'results-ask' && (
        <section className="flex flex-col gap-6">
          {/* Bloco de resposta */}
          <div className="rounded-xl border border-accent/30 bg-accent-bg p-5 flex flex-col gap-2">
            <span className="text-xs font-heading font-700 uppercase tracking-wide text-accent">
              Resposta
            </span>
            <p className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
              {state.data.answer}
            </p>
          </div>

          {/* Fontes */}
          {state.data.sources.length > 0 && (
            <div className="flex flex-col gap-3">
              <p className="text-xs text-text-muted">
                {state.data.sources.length} fonte{state.data.sources.length !== 1 ? 's' : ''} usada{state.data.sources.length !== 1 ? 's' : ''}
              </p>
              {state.data.sources.map((hit, i) => (
                <ResultCard key={`${hit.run_id}-${i}`} hit={hit} />
              ))}
            </div>
          )}

          {state.data.sources.length === 0 && (
            <EmptyState message="Nenhuma fonte encontrada nos videos indexados." />
          )}
        </section>
      )}
    </main>
    </div>
  );
}
