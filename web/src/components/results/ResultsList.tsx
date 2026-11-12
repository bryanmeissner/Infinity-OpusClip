import React, { useState } from 'react';
import {
  Filter,
  ArrowUpDown,
  Download,
  Scissors,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Sparkles,
  TrendingUp,
  Film,
  Play,
  RotateCcw,
} from 'lucide-react';
import type { Candidate, Project } from '../../types';
import { CandidateCard } from './CandidateCard';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { Modal } from '../common/Modal';
import { EmptyState } from '../common/EmptyState';
import { api } from '../../api/client';

export interface ResultsListProps {
  project: Project;
  onEditCandidate: (candidate: Candidate) => void;
  onRenderCandidate: (candidateId: string) => Promise<void>;
  onDeleteCandidate: (candidateId: string) => Promise<void>;
  onExportCandidate: (candidateId: string) => void;
  onNavigateToProcess: () => void;
  renderingCandidateId?: string | null;
}

export const ResultsList: React.FC<ResultsListProps> = ({
  project,
  onEditCandidate,
  onRenderCandidate,
  onDeleteCandidate,
  onExportCandidate,
  onNavigateToProcess,
  renderingCandidateId,
}) => {
  const [filterMode, setFilterMode] = useState<'all' | 'top3' | 'high_score' | 'rendered'>('all');
  const [sortMode, setSortMode] = useState<'score' | 'duration' | 'chronological'>('score');
  const [previewCandidate, setPreviewCandidate] = useState<Candidate | null>(null);

  const candidates = (project.candidates || []).map((candidate) => ({
    ...candidate,
    start: candidate.edit?.start ?? candidate.start,
    end: candidate.edit?.end ?? candidate.end,
  }));

  // Filtragem
  const filteredCandidates = candidates.filter((c) => {
    if (filterMode === 'top3') {
      const sortedByScore = [...candidates].sort((a, b) => b.score - a.score);
      return sortedByScore.slice(0, 3).some((top) => top.id === c.id);
    }
    if (filterMode === 'rendered') {
      return Boolean(c.rendered);
    }
    if (filterMode === 'high_score') {
      return c.score >= 80;
    }
    return true;
  });

  // Ordenação
  const sortedCandidates = [...filteredCandidates].sort((a, b) => {
    if (sortMode === 'score') {
      return b.score - a.score;
    }
    if (sortMode === 'duration') {
      return (b.end - b.start) - (a.end - a.start);
    }
    if (sortMode === 'chronological') {
      return a.start - b.start;
    }
    return 0;
  });

  const renderedCount = candidates.filter((c) => c.rendered).length;
  const avgScore =
    candidates.length > 0
      ? Math.round(candidates.reduce((acc, c) => acc + c.score, 0) / candidates.length)
      : 0;

  // Estado vazio
  if (candidates.length === 0) {
    return (
      <EmptyState
        icon={<Sparkles size={32} />}
        title="Nenhum corte gerado ainda"
        description={`O vídeo "${project.display_name || project.name}" ainda não possui candidatos de cortes ranqueados. Configure os parâmetros de IA e gere seus clipes verticais agora.`}
        actionText="Configurar e Gerar Cortes"
        actionIcon={<Scissors size={16} />}
        onAction={onNavigateToProcess}
      />
    );
  }

  return (
    <div>
      {/* CABEÇALHO DO ESTÚDIO COM KPIS E AÇÃO */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '24px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <Badge variant="indigo" icon={<Sparkles size={12} />}>
              GALERIA DE CORTES
            </Badge>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              Projeto: <strong>{project.display_name || project.name}</strong>
            </span>
          </div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            Cortes Ranqueados por Potencial
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            A IA avaliou ganchos, ritmo e relevância para classificar os momentos de maior retenção.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px' }}>
          <Button
            variant="secondary"
            icon={<Scissors size={16} />}
            onClick={onNavigateToProcess}
          >
            Refazer / Ajustar Análise
          </Button>
        </div>
      </div>

      {/* CARDS DE RESUMO (KPIS) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '14px',
          marginBottom: '24px',
        }}
      >
        <div className="card" style={{ padding: '16px 18px', background: 'var(--bg-surface)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Total de Cortes
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>
            {candidates.length}
          </div>
        </div>

        <div className="card" style={{ padding: '16px 18px', background: 'var(--bg-surface)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Potencial Médio
          </div>
          <div
            style={{
              fontSize: '1.5rem',
              fontWeight: 800,
              color: avgScore >= 80 ? 'var(--emerald)' : avgScore >= 50 ? 'var(--amber)' : 'var(--rose)',
              marginTop: '4px',
            }}
          >
            {avgScore} / 100
          </div>
        </div>

        <div className="card" style={{ padding: '16px 18px', background: 'var(--bg-surface)' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            Prontos para Postar
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>
            {renderedCount}{' '}
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 500 }}>
              de {candidates.length} renderizados
            </span>
          </div>
        </div>
      </div>

      {/* BARRA DE FILTROS & ORDENAÇÃO */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '14px',
          marginBottom: '24px',
          padding: '12px 18px',
          backgroundColor: 'var(--bg-surface)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        {/* Filtros em Pílulas */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginRight: '4px' }}>
            Filtrar:
          </span>

          <button
            type="button"
            onClick={() => setFilterMode('all')}
            className={`btn btn-sm ${filterMode === 'all' ? 'btn-primary' : 'btn-ghost'}`}
          >
            Todos ({candidates.length})
          </button>

          <button
            type="button"
            onClick={() => setFilterMode('top3')}
            className={`btn btn-sm ${filterMode === 'top3' ? 'btn-primary' : 'btn-ghost'}`}
          >
            Top 3 Destaques
          </button>

          <button
            type="button"
            onClick={() => setFilterMode('high_score')}
            className={`btn btn-sm ${filterMode === 'high_score' ? 'btn-primary' : 'btn-ghost'}`}
          >
            Alto Potencial (80+)
          </button>

          <button
            type="button"
            onClick={() => setFilterMode('rendered')}
            className={`btn btn-sm ${filterMode === 'rendered' ? 'btn-primary' : 'btn-ghost'}`}
          >
            Prontos ({renderedCount})
          </button>
        </div>

        {/* Seletor de Ordenação */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ArrowUpDown size={15} color="var(--text-muted)" aria-hidden="true" />
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Ordenar por:</span>
          <select
            className="form-select"
            style={{ minHeight: '34px', height: '34px', padding: '4px 28px 4px 10px', fontSize: '0.82rem', width: 'auto' }}
            value={sortMode}
            onChange={(e) => setSortMode(e.target.value as 'score' | 'duration' | 'chronological')}
            aria-label="Critério de ordenação de cortes"
          >
            <option value="score">Maior Potencial</option>
            <option value="duration">Maior Duração</option>
            <option value="chronological">Ordem no Vídeo Original</option>
          </select>
        </div>
      </div>

      {/* GRID DE CARDS DOS CORTES */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
          gap: '20px',
        }}
      >
        {sortedCandidates.map((candidate, idx) => {
          // Achar posição absoluta no ranking por score
          const absoluteRank = [...candidates].sort((a, b) => b.score - a.score).findIndex((c) => c.id === candidate.id) + 1;

          return (
            <CandidateCard
              key={candidate.id}
              candidate={candidate}
              rank={absoluteRank}
              onPreview={(c) => setPreviewCandidate(c)}
              onEdit={onEditCandidate}
              onRender={onRenderCandidate}
              onExport={onExportCandidate}
              onDelete={onDeleteCandidate}
              isRendering={renderingCandidateId === candidate.id}
            />
          );
        })}
      </div>

      {/* MODAL DE PRÉVIA RÁPIDA DE VÍDEO */}
      {previewCandidate && (
        <Modal
          isOpen={Boolean(previewCandidate)}
          onClose={() => setPreviewCandidate(null)}
          title={`Prévia do Corte: ${previewCandidate.title || 'Sem título'}`}
          subtitle={`Intervalo: ${Math.round(previewCandidate.end - previewCandidate.start)} segundos (Score: ${Math.round(previewCandidate.score)})`}
          maxWidth="700px"
        >
          <div>
            <div
              style={{
                width: '100%',
                maxHeight: '440px',
                borderRadius: 'var(--radius-lg)',
                overflow: 'hidden',
                backgroundColor: '#000000',
                marginBottom: '18px',
                border: '1px solid var(--border-default)',
              }}
            >
              <video
                controls
                autoPlay
                playsInline
                style={{ width: '100%', maxHeight: '440px', objectFit: 'contain' }}
                src={
                  previewCandidate.rendered
                    ? api.getCandidateVideoUrl(project.id, previewCandidate.id)
                    : `${api.getSourceUrl(project.id)}#t=${previewCandidate.start},${previewCandidate.end}`
                }
              >
                Seu navegador não suporta a reprodução deste vídeo.
              </video>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {previewCandidate.rendered ? (
                  <Badge variant="emerald" icon={<CheckCircle2 size={12} />}>
                    Exibindo corte renderizado final com enquadramento
                  </Badge>
                ) : (
                  <Badge variant="muted" icon={<Film size={12} />}>
                    Exibindo trecho bruto original (não renderizado)
                  </Badge>
                )}
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <Button
                  variant="primary"
                  icon={<Scissors size={15} />}
                  onClick={() => {
                    const c = previewCandidate;
                    setPreviewCandidate(null);
                    onEditCandidate(c);
                  }}
                >
                  Abrir no Estúdio de Edição
                </Button>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
