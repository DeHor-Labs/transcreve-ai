import type { DossierAnalysis } from '../../api/types';

interface SynthesisCardProps {
  analysis: DossierAnalysis;
}

export function SynthesisCard({ analysis }: SynthesisCardProps) {
  const { synthesis, metadata } = analysis;

  return (
    <div className="space-y-1">
      {metadata?.title && (
        <h2 className="font-heading font-bold text-xl text-text-primary leading-snug">
          {metadata.title}
        </h2>
      )}
      {metadata?.uploader && (
        <p className="text-text-muted text-sm">{metadata.uploader}</p>
      )}
      {synthesis?.summary && (
        <p className="text-text-secondary text-sm leading-relaxed pt-3 border-t border-border mt-3">
          {synthesis.summary}
        </p>
      )}
    </div>
  );
}
