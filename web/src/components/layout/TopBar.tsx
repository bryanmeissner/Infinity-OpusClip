import React from 'react';
import {
  Plus,
  Loader2,
  X,
} from 'lucide-react';
import type { Job, Project } from '../../types';
import { Button } from '../common/Button';
export interface TopBarProps {
  activeProject: Project | null;
  projects: Project[];
  onSelectProject: (projectId: string) => void;
  onOpenNewProjectModal: () => void;
  activeJob?: Job | null;
  onCancelJob?: (jobId: string) => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  activeProject,
  projects,
  onSelectProject,
  onOpenNewProjectModal,
  activeJob,
  onCancelJob,
}) => {

  const getJobLabel = (job: Job) => {
    switch (job.kind) {
      case 'ingest':
        return 'Importando vídeo';
      case 'preview':
        return 'Gerando prévia local';
      case 'process':
        return 'Analisando transcrição & IA';
      case 'render':
        return 'Renderizando corte final (FFmpeg)';
      default:
        return 'Processando';
    }
  };

  return (
    <header className="studio-topbar" aria-label="Barra de status do projeto">
      <div className="studio-topbar-right" style={{ marginLeft: 'auto' }}>
        {/* Indicador de Job em Andamento */}
        {activeJob && (activeJob.state === 'running' || activeJob.state === 'queued') && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              backgroundColor: 'rgba(99, 102, 241, 0.12)',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              borderRadius: 'var(--radius-full)',
              padding: '6px 14px',
              boxShadow: '0 0 16px rgba(99, 102, 241, 0.2)',
            }}
            role="status"
            aria-live="polite"
          >
            <Loader2 className="animate-spin" size={15} color="var(--ai-indigo)" />
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-primary)' }}>
              {getJobLabel(activeJob)}
            </span>
            <span
              className="font-mono"
              style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--ai-indigo)' }}
            >
              {Math.round((activeJob.progress || 0) * 100)}%
            </span>

            {onCancelJob && (
              <button
                onClick={() => onCancelJob(activeJob.id)}
                className="btn btn-ghost btn-sm"
                style={{ padding: '2px', minHeight: '22px', minWidth: '22px', marginLeft: '4px' }}
                title="Cancelar processamento"
                aria-label="Cancelar processamento em andamento"
              >
                <X size={14} color="var(--text-muted)" />
              </button>
            )}
          </div>
        )}

        {/* Botão de Novo Vídeo */}
        <Button
          variant="primary"
          size="sm"
          icon={<Plus size={16} />}
          onClick={onOpenNewProjectModal}
        >
          Novo Vídeo
        </Button>
      </div>
    </header>
  );
};
