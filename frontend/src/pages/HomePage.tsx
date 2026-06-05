import { Link } from 'react-router-dom';
import { JobList } from '../components/history/JobList';
import { SubmitForm } from '../components/submit/SubmitForm';
import { ErrorState } from '../components/ui/ErrorState';
import { Separator } from '../components/ui/Separator';
import { Spinner } from '../components/ui/Spinner';
import { useJobList } from '../hooks/useJobList';

export function HomePage() {
  const { data, isLoading, isError, refetch } = useJobList();

  return (
    <div className="min-h-dvh bg-[var(--color-bg)]">
      {/* Header */}
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
              className="text-text-muted text-sm hover:text-text-primary transition-colors font-heading"
            >
              Buscar
            </Link>
            <a
              href="#historico"
              className="text-text-muted text-sm hover:text-text-primary transition-colors font-heading"
            >
              Historico
            </a>
          </nav>
        </div>
      </header>

      <main>
        {/* Secao de submit */}
        <section
          aria-labelledby="submit-heading"
          className="max-w-[680px] mx-auto px-4 sm:px-6 py-[var(--space-3xl)]"
        >
          <div className="mb-10">
            <h1
              id="submit-heading"
              className="font-heading font-bold text-[var(--text-3xl)] text-text-primary leading-tight mb-3"
            >
              Analise qualquer video
            </h1>
            <p className="text-text-secondary text-base">
              Envie um link ou arquivo e obtenha um dossie completo com transcricao,
              capitulos, entidades e insights extraidos por IA.
            </p>
          </div>
          <div className="bg-surface1 border border-border rounded-xl p-6 sm:p-8">
            <SubmitForm />
          </div>
        </section>

        {/* Historico */}
        <section
          id="historico"
          aria-labelledby="history-heading"
          className="max-w-[860px] mx-auto px-4 sm:px-6 pb-16"
        >
          <Separator label="Historico recente" className="mb-6" />

          {isLoading && (
            <div className="flex justify-center py-12" aria-busy="true" aria-label="Carregando historico">
              <Spinner size="lg" className="text-text-muted" />
            </div>
          )}

          {isError && (
            <ErrorState
              title="Erro ao carregar historico"
              message="Nao foi possivel buscar os jobs. Verifique se a API esta rodando."
              onRetry={() => void refetch()}
            />
          )}

          {!isLoading && !isError && (
            <JobList jobs={data?.jobs ?? []} />
          )}
        </section>
      </main>
    </div>
  );
}
