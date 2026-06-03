import { useState } from 'react';
import type { DossierResponse } from '../../api/types';
import { Separator } from '../ui/Separator';
import { ChapterList } from './ChapterList';
import { ClaimsList } from './ClaimsList';
import { EntityCloud } from './EntityCloud';
import { MarkdownRenderer } from './MarkdownRenderer';
import { SynthesisCard } from './SynthesisCard';

interface DossierViewProps {
  dossier: DossierResponse;
}

function MetaItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted">
        {label}
      </span>
      <span className="text-text-secondary text-sm">{value}</span>
    </div>
  );
}

function formatDuration(secs: number): string {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}min`;
}

export function DossierView({ dossier }: DossierViewProps) {
  const [showMarkdown, setShowMarkdown] = useState(false);
  const { analysis, markdown } = dossier;
  const { metadata, synthesis } = analysis;

  return (
    <div className="animate-[fadeIn_0.3s_ease-out_both]" style={{ animation: 'fadeIn 0.3s ease-out both' }}>
      {/* Layout: sidebar + main */}
      <div className="flex flex-col lg:flex-row gap-0 lg:gap-8">
        {/* Sidebar de metadata */}
        <aside
          aria-label="Metadados do video"
          className="lg:w-64 shrink-0 flex flex-col gap-4 pb-6 lg:pb-0 lg:border-r lg:border-border lg:pr-8"
        >
          <SynthesisCard analysis={analysis} />

          <Separator />

          {metadata?.duration && (
            <MetaItem label="Duracao" value={formatDuration(metadata.duration)} />
          )}
          {metadata?.channel && metadata.channel !== metadata?.uploader && (
            <MetaItem label="Canal" value={metadata.channel} />
          )}
          {metadata?.upload_date && (
            <MetaItem
              label="Publicado"
              value={
                metadata.upload_date.length === 8
                  ? `${metadata.upload_date.slice(6, 8)}/${metadata.upload_date.slice(4, 6)}/${metadata.upload_date.slice(0, 4)}`
                  : metadata.upload_date
              }
            />
          )}
          {analysis.frames_count > 0 && (
            <MetaItem label="Frames" value={`${analysis.frames_count} analisados`} />
          )}
          {analysis.warnings?.length > 0 && (
            <div>
              <span className="font-heading font-bold text-xs uppercase tracking-widest text-status-failed/80">
                Avisos ({analysis.warnings.length})
              </span>
              <ul className="mt-1 flex flex-col gap-1">
                {analysis.warnings.map((w, i) => (
                  <li key={i} className="text-xs text-text-muted">{w}</li>
                ))}
              </ul>
            </div>
          )}
        </aside>

        {/* Conteudo principal */}
        <main className="flex-1 min-w-0 flex flex-col gap-8">
          {/* Resumo */}
          {synthesis?.summary && (
            <section aria-labelledby="summary-heading">
              <h3
                id="summary-heading"
                className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted mb-3"
              >
                Resumo
              </h3>
              <p className="text-text-secondary text-sm leading-relaxed">{synthesis.summary}</p>
            </section>
          )}

          {/* Capitulos */}
          {synthesis?.chapters?.length > 0 && (
            <section aria-labelledby="chapters-heading">
              <Separator label="Capitulos" className="mb-4" />
              <ChapterList chapters={synthesis.chapters} />
            </section>
          )}

          {/* Entidades e ferramentas */}
          {(synthesis?.entities?.length > 0 || synthesis?.tools_or_products?.length > 0) && (
            <section aria-labelledby="entities-heading">
              <Separator label="Entidades e ferramentas" className="mb-4" />
              <div className="flex flex-col gap-5">
                {synthesis?.entities?.length > 0 && (
                  <EntityCloud
                    entities={synthesis.entities}
                    label="Conceitos e entidades"
                  />
                )}
                {synthesis?.tools_or_products?.length > 0 && (
                  <EntityCloud
                    entities={synthesis.tools_or_products}
                    label="Ferramentas e produtos"
                    variant="accent"
                  />
                )}
              </div>
            </section>
          )}

          {/* Claims, action items, perguntas */}
          {(synthesis?.claims?.length > 0 ||
            synthesis?.action_items?.length > 0 ||
            synthesis?.questions?.length > 0) && (
            <section aria-labelledby="claims-heading">
              <Separator label="Insights" className="mb-4" />
              <ClaimsList
                claims={synthesis.claims ?? []}
                actionItems={synthesis.action_items ?? []}
                questions={synthesis.questions ?? []}
              />
            </section>
          )}

          {/* Toggle markdown bruto */}
          <div>
            <Separator className="mb-4" />
            <button
              type="button"
              onClick={() => setShowMarkdown((v) => !v)}
              className="font-heading font-bold text-xs uppercase tracking-widest text-text-muted hover:text-accent transition-colors flex items-center gap-2"
              aria-expanded={showMarkdown}
            >
              <svg
                width="14" height="14" viewBox="0 0 24 24" fill="none"
                className={`transition-transform duration-[180ms] ${showMarkdown ? 'rotate-90' : ''}`}
                aria-hidden="true"
              >
                <path d="M9 18l6-6-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {showMarkdown ? 'Ocultar markdown' : 'Ver markdown bruto'}
            </button>
            {showMarkdown && (
              <div className="mt-4 p-4 rounded-md bg-surface1 border border-border overflow-auto max-h-[600px]">
                <MarkdownRenderer content={markdown} />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
