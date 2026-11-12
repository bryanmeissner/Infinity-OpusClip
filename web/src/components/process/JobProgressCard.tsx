import React, { useState } from 'react';
import { Loader2, XCircle, AlertCircle, CheckCircle2, RefreshCw, Sparkles, Video, Film, Scissors } from 'lucide-react';
import type { Job } from '../../types';
import { ProgressBar } from '../common/ProgressBar';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';

export interface JobProgressCardProps {
  job: Job;
  onCancelJob: (jobId: string) => Promise<void>;
  onRetry?: () => void | Promise<void>;
}

export const JobProgressCard: React.FC<JobProgressCardProps> = ({
  job,
  onCancelJob,
  onRetry,
}) => {
  const [isCancelling, setIsCancelling] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [showConfirmCancel, setShowConfirmCancel] = useState(false);

  const isRunning = job.state === 'queued' || job.state === 'running';
  const isFailed = job.state === 'failed' || job.state === 'interrupted';
  const isCancelled = job.state === 'cancelled';
  const isCompleted = job.state === 'completed';

  const handleCancelClick = async () => {
    setIsCancelling(true);
    try {
      await onCancelJob(job.id);
      setShowConfirmCancel(false);
    } finally {
      setIsCancelling(false);
    }
  };
  const handleRetryClick = async () => {
    if (!onRetry) return;
    setIsRetrying(true);
    try {
      await onRetry();
    } finally {
      setIsRetrying(false);
    }
  };

  const getJobTitle = () => {
    switch (job.kind) {
      case 'ingest':
        return 'Importação de Arquivo de Vídeo';
      case 'preview':
        return 'Geração de Prévia do Original';
      case 'process':
        return 'Transcrição Local & Análise de IA';
      case 'render':
        return 'Renderização de Corte Final (FFmpeg)';
      default:
        return 'Processamento em Segundo Plano';
    }
  };

  const getJobIcon = () => {
    switch (job.kind) {
      case 'ingest':
        return <Film size={18} color="var(--primary)" />;
      case 'process':
        return <Sparkles size={18} color="var(--ai-indigo)" />;
      case 'render':
        return <Video size={18} color="var(--primary)" />;
      default:
        return <Scissors size={18} color="var(--text-secondary)" />;
    }
  };

  return (
    <div
      className="card"
      style={{
        marginBottom: '24px',
        backgroundColor: 'var(--bg-card-elevated)',
        border: isRunning
          ? '1px solid rgba(99, 102, 241, 0.35)'
          : isFailed
          ? '1px solid rgba(239, 68, 68, 0.4)'
          : '1px solid var(--border-default)',
        boxShadow: isRunning ? '0 4px 20px rgba(99, 102, 241, 0.15)' : undefined,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {getJobIcon()}
          <div>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              {getJobTitle()}
            </h3>
            {job.stage && (
              <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                Fase atual: {job.stage}
              </span>
            )}
          </div>
        </div>

        <div>
          {isRunning && (
            <Badge variant="indigo" icon={<Loader2 className="animate-spin" size={12} />}>
              Em Execução
            </Badge>
          )}
          {isCompleted && (
            <Badge variant="emerald" icon={<CheckCircle2 size={12} />}>
              Concluído
            </Badge>
          )}
          {isFailed && (
            <Badge variant="rose" icon={<AlertCircle size={12} />}>
              Falha
            </Badge>
          )}
          {isCancelled && (
            <Badge variant="muted">
              Cancelado
            </Badge>
          )}
        </div>
      </div>

      {/* Barra de Progresso */}
      <div style={{ marginBottom: isFailed ? '14px' : '0' }}>
        <ProgressBar
          progress={job.progress || 0}
          label={job.stage || 'Progresso'}
          variant={job.kind === 'process' ? 'ai' : 'primary'}
        />
      </div>

      {/* Detalhe de Erro amigável */}
      {isFailed && job.error && (
        <div
          style={{
            padding: '12px 14px',
            backgroundColor: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
            borderRadius: 'var(--radius-md)',
            color: '#fca5a5',
            fontSize: '0.85rem',
            marginBottom: '14px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '8px',
          }}
        >
          <AlertCircle size={16} color="var(--danger)" style={{ flexShrink: 0, marginTop: '2px' }} />
          <div>{job.error}</div>
        </div>
      )}

      {/* Ações de Cancelamento */}
      {isRunning && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '12px' }}>
          {showConfirmCancel ? (
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Confirmar cancelamento?</span>
              <Button
                variant="danger"
                size="sm"
                loading={isCancelling}
                onClick={handleCancelClick}
              >
                Sim, Cancelar
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowConfirmCancel(false)}
              >
                Voltar
              </Button>
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowConfirmCancel(true)}
              style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}
            >
              Cancelar Tarefa
            </Button>
          )}
        </div>
      )}

      {(Array.isArray(job.checkpoint?.fallback_events) ? job.checkpoint.fallback_events as string[] : []).map((notice) => (
        <div key={notice} role="status" style={{
          padding: '10px 14px', marginTop: '12px',
          backgroundColor: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.3)',
          borderRadius: 'var(--radius-md)', color: '#fde68a', fontSize: '0.82rem',
        }}>
          {notice}
        </div>
      ))}

      {/* Uma falha de provider exige intervenção; não inferir crédito a partir de HTTP 400/401/403. */}
      {isFailed && (
        <div style={{ marginTop: '12px' }}>
          {job.failed_provider && (
            <p style={{ color: '#fde68a', fontSize: '0.82rem', marginBottom: '12px' }}>
              O provedor {job.failed_provider} falhou. Corrija a configuração ou selecione outro provedor em Provedores de IA e tente novamente; a análise concluída será reutilizada.
            </p>
          )}

          {onRetry && job.kind === 'process' && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <Button
                variant="primary"
                size="sm"
                icon={<RefreshCw size={14} className={isRetrying ? 'animate-spin' : ''} />}
                loading={isRetrying}
                onClick={handleRetryClick}
              >
                Tentar novamente
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
