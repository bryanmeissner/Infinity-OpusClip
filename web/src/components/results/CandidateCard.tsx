import React, { useState } from 'react';
import {
  Play,
  Scissors,
  Download,
  Trash2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Clock,
  Sparkles,
  CheckCircle2,
  Video,
  Flame,
  TrendingUp,
  MessageSquareQuote,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import type { Candidate } from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { ScoreGauge } from '../common/ScoreGauge';

export interface CandidateCardProps {
  candidate: Candidate;
  rank: number;
  onPreview: (candidate: Candidate) => void;
  onEdit: (candidate: Candidate) => void;
  onRender: (candidateId: string) => Promise<void>;
  onExport: (candidateId: string) => void;
  onDelete: (candidateId: string) => Promise<void>;
  isRendering?: boolean;
}

export const CandidateCard: React.FC<CandidateCardProps> = ({
  candidate,
  rank,
  onPreview,
  onEdit,
  onRender,
  onExport,
  onDelete,
  isRendering = false,
}) => {
  const [showScoreDetails, setShowScoreDetails] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Formata segundos em MM:SS
  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const effectiveStart = candidate.edit?.start ?? candidate.start;
  const effectiveEnd = candidate.edit?.end ?? candidate.end;
  const removeRangesTotal = (candidate.edit?.remove_ranges || []).reduce(
    (sum, range) => sum + range.end - range.start,
    0
  );
  const durationSecs = Math.max(1, Math.round(effectiveEnd - effectiveStart - removeRangesTotal));
  const isRendered = Boolean(candidate.rendered);

  // Cores de Rank
  const rankGradient =
    rank === 1
      ? 'linear-gradient(135deg, #eab308 0%, #ca8a04 100%)'
      : rank === 2
      ? 'linear-gradient(135deg, #94a3b8 0%, #64748b 100%)'
      : rank === 3
      ? 'linear-gradient(135deg, #b45309 0%, #78350f 100%)'
      : 'var(--bg-surface)';

  const rankTextColor = rank <= 3 ? '#ffffff' : 'var(--text-secondary)';
  const rankGlow = rank === 1 ? '0 0 14px rgba(234, 179, 8, 0.4)' : undefined;

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await onDelete(candidate.id);
      setShowDeleteConfirm(false);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div
      className="card card-hover"
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        position: 'relative',
        border: '1px solid var(--border-default)',
        background: 'var(--bg-card)',
        padding: '22px',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
      }}
    >
      <div>
        {/* TOPO: Posição no Ranking, Gauge de Score e Status */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: '16px',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {/* Badge de Posição */}
            <span
              style={{
                background: rankGradient,
                color: rankTextColor,
                fontWeight: 800,
                fontSize: '0.82rem',
                padding: '4px 10px',
                borderRadius: 'var(--radius-sm)',
                boxShadow: rankGlow,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              {rank === 1 && <Flame size={13} />}
              #{rank}
            </span>

            {/* Modalidade de Análise */}
            {candidate.mode === 'hybrid' ? (
              <Badge variant="indigo" icon={<Sparkles size={11} />}>
                IA Híbrida
              </Badge>
            ) : (
              <Badge variant="muted" icon={<Cpu size={11} />}>
                Local Heurístico
              </Badge>
            )}

            {/* Status de Render */}
            {isRendered ? (
              <Badge variant="emerald" icon={<CheckCircle2 size={11} />}>
                Renderizado
              </Badge>
            ) : isRendering ? (
              <Badge variant="amber" icon={<Loader2 className="animate-spin" size={11} />}>
                Renderizando...
              </Badge>
            ) : (
              <Badge variant="muted">
                Rascunho
              </Badge>
            )}
          </div>

          {/* Medidor Circular de Score */}
          <ScoreGauge score={candidate.score} size="sm" showLabel={false} />
        </div>

        {/* TÍTULO & DURAÇÃO */}
        <div style={{ marginBottom: '12px' }}>
          <h2
            style={{
              fontSize: '1.15rem',
              fontWeight: 700,
              color: 'var(--text-primary)',
              lineHeight: 1.35,
              marginBottom: '6px',
            }}
          >
            {candidate.title || `Corte #${rank}`}
          </h2>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              fontSize: '0.8rem',
              color: 'var(--text-muted)',
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <Clock size={13} />
              <span className="font-mono">{durationSecs}s</span>
            </span>
            <span>•</span>
            <span className="font-mono">
              {formatTime(effectiveStart)} → {formatTime(effectiveEnd)}
            </span>
            {candidate.edit?.format && (
              <>
                <span>•</span>
                <span className="font-mono">{candidate.edit.format}</span>
              </>
            )}
          </div>
        </div>

        {/* BOX DE GANCHO (HOOK / SUMMARY) */}
        {candidate.summary && (
          <div
            style={{
              backgroundColor: 'rgba(99, 102, 241, 0.08)',
              borderLeft: '3px solid var(--ai-indigo)',
              padding: '10px 14px',
              borderRadius: '0 var(--radius-sm) var(--radius-sm) 0',
              marginBottom: '14px',
            }}
          >
            <div
              style={{
                fontSize: '0.7rem',
                fontWeight: 700,
                color: 'var(--ai-indigo)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginBottom: '4px',
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
              }}
            >
              <MessageSquareQuote size={12} />
              Gancho Inicial (Hook)
            </div>
            <p
              style={{
                fontSize: '0.85rem',
                color: 'var(--text-secondary)',
                fontStyle: 'italic',
                lineHeight: 1.4,
              }}
            >
              "{candidate.summary}"
            </p>
          </div>
        )}

        {/* MOTIVO / EXPLICAÇÃO DO CORTE */}
        {candidate.reason && (
          <p
            style={{
              fontSize: '0.85rem',
              color: 'var(--text-secondary)',
              lineHeight: 1.45,
              marginBottom: '16px',
            }}
          >
            {candidate.reason}
          </p>
        )}

        {/* DETALHAMENTO DE SCORES DA IA (Colapsável) */}
        {candidate.scores && (
          <div style={{ marginBottom: '18px' }}>
            <button
              type="button"
              onClick={() => setShowScoreDetails(!showScoreDetails)}
              className="btn btn-ghost btn-sm"
              style={{
                padding: '4px 8px',
                fontSize: '0.78rem',
                color: 'var(--text-muted)',
                gap: '4px',
                marginBottom: '8px',
              }}
            >
              <TrendingUp size={13} color="var(--primary)" />
              <span>{showScoreDetails ? 'Ocultar Métricas de Retenção' : 'Ver Métricas de Retenção (IA)'}</span>
              {showScoreDetails ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>

            {showScoreDetails && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, 1fr)',
                  gap: '8px',
                  backgroundColor: 'var(--bg-input)',
                  padding: '12px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.78rem',
                }}
              >
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Força do Gancho:</span>{' '}
                  <strong className="font-mono" style={{ color: 'var(--text-primary)' }}>
                    {Math.round(candidate.scores.hook || 0)}/100
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Valor / Engajamento:</span>{' '}
                  <strong className="font-mono" style={{ color: 'var(--text-primary)' }}>
                    {Math.round(candidate.scores.value || 0)}/100
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Compartilhamento:</span>{' '}
                  <strong className="font-mono" style={{ color: 'var(--text-primary)' }}>
                    {Math.round(candidate.scores.shareability || 0)}/100
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Fluidez / Ritmo:</span>{' '}
                  <strong className="font-mono" style={{ color: 'var(--text-primary)' }}>
                    {Math.round(candidate.scores.flow || 0)}/100
                  </strong>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* RODAPÉ DE AÇÕES */}
      <div
        style={{
          borderTop: '1px solid var(--border-subtle)',
          paddingTop: '16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {/* Botão de Edição Primário */}
          <Button
            variant="primary"
            size="sm"
            icon={<Scissors size={14} />}
            onClick={() => onEdit(candidate)}
          >
            Editar no Estúdio
          </Button>

          {/* Prévia Rápida */}
          <Button
            variant="secondary"
            size="sm"
            icon={<Play size={14} />}
            onClick={() => onPreview(candidate)}
          >
            Prévia
          </Button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Renderização FFmpeg */}
          {!isRendered && (
            <Button
              variant="outline"
              size="sm"
              icon={isRendering ? <Loader2 className="animate-spin" size={14} /> : <Video size={14} />}
              loading={isRendering}
              onClick={() => onRender(candidate.id)}
              title="Renderizar corte com enquadramento e legendas queimadas"
            >
              Renderizar
            </Button>
          )}

          {/* Exportar / Download se renderizado */}
          {isRendered && (
            <Button
              variant="ai"
              size="sm"
              icon={<Download size={14} />}
              onClick={() => onExport(candidate.id)}
              title="Baixar vídeo final pronto para redes sociais"
            >
              Baixar MP4
            </Button>
          )}

          {/* Exclusão do Corte */}
          {showDeleteConfirm ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Button
                variant="danger"
                size="sm"
                loading={isDeleting}
                onClick={handleDelete}
              >
                Confirmar
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowDeleteConfirm(false)}
              >
                Cancelar
              </Button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowDeleteConfirm(true)}
              className="btn btn-ghost btn-sm"
              style={{ padding: '6px', minWidth: '32px', color: 'var(--text-muted)' }}
              title="Excluir este corte"
              aria-label="Excluir este corte"
            >
              <Trash2 size={15} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
