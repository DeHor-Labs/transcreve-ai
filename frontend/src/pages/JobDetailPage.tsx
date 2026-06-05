import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { getDossier } from '../api/jobs';
import { DossierView } from '../components/dossier/DossierView';
import { StatusBadge } from '../components/history/StatusBadge';
import { LiveStep } from '../components/progress/LiveStep';
import { ProgressBar } from '../components/progress/ProgressBar';
import { StepTimeline } from '../components/progress/StepTimeline';
import { ErrorState } from '../components/ui/ErrorState';
import { Spinner } from '../components/ui/Spinner';
import { useJobDetail } from '../hooks/useJobDetail';
import { useJobEvents } from '../hooks/useJobEvents';

export function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const jobId = id ?? '';

  const { data: job, isLoading, isError, refetch } = useJobDetail(jobId);

  const isActive = job?.status === 'running' || job?.status === 'queued';
  const isDone = job?.status === 'completed';
  const isFailed = job?.status === 'failed';
  const { events, latest, done: sseDone, failed: sseFailed } = useJobEvents(jobId, !!job && isActive);
  const hasFailed = isFailed || sseFailed;

  // Usa eventos SSE se disponivel, caso contrario usa progress do polling
  const currentEvent = latest ?? job?.progress ?? null;
  const currentStep = currentEvent?.step ?? 'download';
  const effectivePct = currentEvent?.pct ?? 0;

  // Historico de eventos para a timeline (SSE > progress_history do job)
  const timelineEvents = events.length > 0 ? events : (job?.progress_history ?? []);

  // Query do dossie - ativa quando done (por SSE ou por polling)
  const shouldFetchDossier = !hasFailed && (isDone || sseDone);
  const dossierQuery = useQuery({
    queryKey: ['dossier', jobId],
    queryFn: () => getDossier(jobId),
    enabled: shouldFetchDossier,
    staleTime: Infinity,
  });

  const title = job?.title || jobId.slice(0, 40);

  return (
    <div className="min-h-dvh bg-[var(--color-bg)]">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-border bg-[var(--color-bg)]/95 backdrop-blur-sm">
        <div className="max-w-[1100px] mx-auto px-4 sm:px-6 h-14 flex items-center gap-4">
          <Link
            to="/"
            aria-label="Voltar para pagina inicial"
            className="text-text-muted hover:text-text-primary transition-colors shrink-0"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M19 12H5M12 5l-7 7 7 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>

          <div className="flex-1 min-w-0 flex items-center gap-3">
            <h1 className="font-heading font-bold text-sm text-text-primary truncate">
              {title}
            </h1>
            {job && (
              <StatusBadge status={job.status} animated={isActive} />
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1100px] mx-auto px-4 sm:px-6 py-8">
        {/* Loading inicial */}
        {isLoading && (
          <div className="flex justify-center py-20" aria-busy="true" aria-label="Carregando job">
            <Spinner size="lg" className="text-text-muted" />
          </div>
        )}

        {isError && (
          <ErrorState
            title="Job nao encontrado"
            message="Esse job nao existe ou foi removido."
            onRetry={() => void refetch()}
          />
        )}

        {job && (
          <>
            {/* Estado: em andamento */}
            {(isActive && !hasFailed) && (
              <div className="flex flex-col lg:flex-row gap-8">
                {/* Sidebar: timeline */}
                <aside
                  aria-label="Progresso das etapas"
                  className="lg:w-56 shrink-0"
                >
                  <StepTimeline
                    events={timelineEvents}
                    currentStep={currentStep}
                    status={job.status}
                  />
                </aside>

                {/* Area principal de progresso */}
                <div className="flex-1 flex flex-col gap-6">
                  <div className="bg-surface1 border border-border rounded-xl p-6 space-y-5">
                    <ProgressBar pct={effectivePct} />
                    {currentEvent ? (
                      <LiveStep event={currentEvent} />
                    ) : (
                      <div className="flex items-center gap-3">
                        <Spinner size="sm" className="text-accent" />
                        <span className="text-text-secondary text-sm">Aguardando inicio...</span>
                      </div>
                    )}
                  </div>

                  {/* Log de eventos */}
                  {timelineEvents.length > 1 && (
                    <div className="bg-surface1 border border-border rounded-xl p-4">
                      <p className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted mb-3">
                        Log
                      </p>
                      <ol className="flex flex-col gap-1.5">
                        {timelineEvents.slice(0, -1).map((ev, i) => (
                          <li key={i} className="flex items-center gap-3 text-xs text-text-muted">
                            <span className="w-1 h-1 rounded-full bg-accent/40 shrink-0" />
                            <span className="flex-1">{ev.detail}</span>
                            <span className="shrink-0 font-heading">{ev.pct}%</span>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Estado: falhou */}
            {hasFailed && (
              <div className="max-w-lg mx-auto">
                <ErrorState
                  title="Analise falhou"
                  message={currentEvent?.detail ?? 'A analise falhou. Verifique a fonte e tente novamente.'}
                  onRetry={() => void refetch()}
                />
              </div>
            )}

            {/* Estado: concluido - dossie */}
            {(isDone || sseDone) && !hasFailed && (
              <>
                {dossierQuery.isLoading && (
                  <div className="flex justify-center py-20" aria-busy="true" aria-label="Carregando dossie">
                    <Spinner size="lg" className="text-text-muted" />
                  </div>
                )}
                {dossierQuery.isError && (
                  <ErrorState
                    title="Erro ao carregar dossie"
                    message="Nao foi possivel carregar os artefatos da analise."
                    onRetry={() => void dossierQuery.refetch()}
                  />
                )}
                {dossierQuery.data && (
                  <DossierView dossier={dossierQuery.data} />
                )}
              </>
            )}
          </>
        )}
      </main>
    </div>
  );
}
