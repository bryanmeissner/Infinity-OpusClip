import React, { useState } from 'react';
import {
  Plus,
  Trash2,
  SlidersHorizontal,
  Sparkles,
  Clock,
  Film,
  HardDrive,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Search,
  Video,
  Play,
  ArrowRight,
  FolderOpen,
  Pencil,
  Check,
  X,
} from 'lucide-react';
import type { Project } from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { EmptyState } from '../common/EmptyState';
import { api } from '../../api/client';
export interface ProjectListProps {
  projects: Project[];
  activeProject: Project | null;
  onSelectProject: (projectId: string) => void;
  onOpenNewProjectModal: () => void;
  onNavigateToProcess: () => void;
  onNavigateToResults: () => void;
  onDeleteProject: (projectId: string) => Promise<void>;
  onRenameProject?: (projectId: string, newName: string) => Promise<void>;
}

const ProjectThumbnail: React.FC<{ projectId: string; duration?: number; title: string }> = ({
  projectId,
  duration,
  title,
}) => {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const src = api.getProjectThumbnailUrl(projectId);

  const formatDur = (seconds?: number) => {
    if (!seconds || isNaN(seconds)) return null;
    const total = Math.round(seconds);
    const hrs = Math.floor(total / 3600);
    const mins = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hrs > 0) {
      return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const durText = formatDur(duration);

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        aspectRatio: '16 / 9',
        backgroundColor: '#070a13',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        border: '1px solid var(--border-subtle)',
        marginBottom: '14px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {!error ? (
        <>
          <img
            src={src}
            alt={title}
            onLoad={() => setLoaded(true)}
            onError={() => setError(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: loaded ? 'block' : 'none',
              transition: 'transform 0.25s ease',
            }}
          />
          {!loaded && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '100%',
                height: '100%',
                color: 'var(--text-muted)',
              }}
            >
              <Loader2 className="animate-spin" size={20} color="var(--primary)" />
            </div>
          )}
        </>
      ) : (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            width: '100%',
            height: '100%',
            color: 'var(--text-muted)',
            background: 'linear-gradient(135deg, rgba(20, 24, 40, 0.95) 0%, rgba(10, 13, 24, 0.95) 100%)',
          }}
        >
          <Film size={28} style={{ opacity: 0.6, marginBottom: '6px' }} />
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Prévia do vídeo</span>
        </div>
      )}

      {durText && (
        <span
          className="font-mono"
          style={{
            position: 'absolute',
            bottom: '8px',
            right: '8px',
            backgroundColor: 'rgba(0, 0, 0, 0.78)',
            color: '#ffffff',
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '0.72rem',
            fontWeight: 700,
            backdropFilter: 'blur(4px)',
            boxShadow: '0 1px 3px rgba(0,0,0,0.6)',
          }}
        >
          {durText}
        </span>
      )}
    </div>
  );
};

export const ProjectList: React.FC<ProjectListProps> = ({
  projects,
  activeProject,
  onSelectProject,
  onOpenNewProjectModal,
  onNavigateToProcess,
  onNavigateToResults,
  onDeleteProject,
  onRenameProject,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState<string>('');
  const [isSavingName, setIsSavingName] = useState<boolean>(false);

  const startEditing = (p: Project) => {
    setEditingProjectId(p.id);
    setEditingName(p.display_name || p.name);
  };

  const cancelEditing = () => {
    setEditingProjectId(null);
    setEditingName('');
  };

  const saveRename = async (projectId: string) => {
    const trimmed = editingName.trim();
    if (!trimmed || !onRenameProject) {
      cancelEditing();
      return;
    }
    setIsSavingName(true);
    try {
      await onRenameProject(projectId, trimmed);
      cancelEditing();
    } finally {
      setIsSavingName(false);
    }
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds || isNaN(seconds)) return '00:00';
    const totalSecs = Math.round(seconds);
    const hrs = Math.floor(totalSecs / 3600);
    const mins = Math.floor((totalSecs % 3600) / 60);
    const secs = totalSecs % 60;

    if (hrs > 0) {
      return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes || isNaN(bytes)) return '—';
    const mb = bytes / (1024 * 1024);
    if (mb >= 1024) {
      return `${(mb / 1024).toFixed(2)} GB`;
    }
    return `${mb.toFixed(1)} MB`;
  };

  const filteredProjects = projects.filter((p) => {
    const displayName = (p.display_name || p.name || '').toLowerCase();
    return displayName.includes(searchQuery.toLowerCase());
  });

  const handleDeleteConfirm = async () => {
    if (!projectToDelete) return;
    setIsDeleting(true);
    try {
      await onDeleteProject(projectToDelete.id);
      setProjectToDelete(null);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div>
      {/* Topo do Módulo de Projetos */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <Badge variant="indigo" icon={<FolderOpen size={12} />}>
              BIBLIOTECA DE VÍDEOS
            </Badge>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              {projects.length} {projects.length === 1 ? 'projeto gerenciado' : 'projetos gerenciados'}
            </span>
          </div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
            Seus Projetos & Vídeos
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            Gerencie os vídeos importados, configure cortes automáticos e acompanhe o pipeline de inteligência artificial.
          </p>
        </div>

        <div className="projects-toolbar" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {projects.length > 0 && (
            <div className="projects-search" style={{ position: 'relative' }}>
              <Search
                size={16}
                color="var(--text-muted)"
                style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }}
                aria-hidden="true"
              />
              <input
                type="text"
                placeholder="Buscar projeto por nome..."
                className="form-input"
                style={{ paddingLeft: '36px', height: '40px', minHeight: '40px', fontSize: '0.85rem' }}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Buscar projetos por nome"
              />
            </div>
          )}

          <Button
            variant="primary"
            icon={<Plus size={16} />}
            onClick={onOpenNewProjectModal}
          >
            Novo Vídeo
          </Button>
        </div>
      </div>

      {/* Lista ou Grid de Projetos */}
      {filteredProjects.length === 0 ? (
        projects.length === 0 ? (
          <EmptyState
            icon={<Film size={36} />}
            title="Nenhum vídeo importado ainda"
            description="Comece importando um arquivo de vídeo do seu computador (MP4, MKV, MOV) ou forneça uma URL de vídeo para iniciar o corte inteligente."
            actionText="Importar Primeiro Vídeo"
            actionIcon={<Plus size={16} />}
            onAction={onOpenNewProjectModal}
          />
        ) : (
          <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
            <p style={{ color: 'var(--text-secondary)' }}>
              Nenhum projeto encontrado para o termo <strong>"{searchQuery}"</strong>.
            </p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSearchQuery('')}
              style={{ marginTop: '12px' }}
            >
              Limpar busca
            </Button>
          </div>
        )
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
            gap: '20px',
          }}
        >
          {filteredProjects.map((project) => {
            const isActive = activeProject?.id === project.id;
            const hasCandidates = (project.candidates || []).length > 0;
            const runningJob = (project.jobs || []).find((j) => j.state === 'running' || j.state === 'queued');
            const isFailed = project.status === 'failed' || Boolean(project.error);

            return (
              <div
                key={project.id}
                className={`card card-hover ${isActive ? 'card-glass' : ''}`}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  border: isActive ? '2px solid var(--primary)' : '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '20px',
                  boxShadow: isActive ? '0 4px 24px var(--primary-glow)' : 'var(--shadow-sm)',
                  position: 'relative',
                  backgroundColor: 'var(--bg-card)',
                }}
              >
                <div>
                  {/* Thumbnail do Vídeo com fallback elegante */}
                  <ProjectThumbnail
                    key={`${project.id}-${project.status}`}
                    projectId={project.id}
                    duration={project.metadata?.duration}
                    title={project.display_name || project.name}
                  />

                  {/* Topo do Card: Status e Badges */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: '10px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {isActive && (
                        <Badge variant="rose">
                          Ativo no Estúdio
                        </Badge>
                      )}

                      {runningJob ? (
                        <Badge variant="indigo" icon={<Loader2 className="animate-spin" size={11} />}>
                          Processando...
                        </Badge>
                      ) : isFailed ? (
                        <Badge variant="rose" icon={<AlertTriangle size={11} />}>
                          Erro
                        </Badge>
                      ) : (
                        <Badge variant="emerald" icon={<CheckCircle2 size={11} />}>
                          Pronto
                        </Badge>
                      )}
                    </div>

                    {project.metadata?.duration && (
                      <span className="font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        {formatDuration(project.metadata.duration)}
                      </span>
                    )}
                  </div>

                  {/* Nome do Vídeo Editável (Item 6) */}
                  {editingProjectId === project.id ? (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                      <input
                        type="text"
                        className="form-input"
                        style={{ height: '34px', minHeight: '34px', fontSize: '0.88rem', padding: '4px 10px' }}
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') saveRename(project.id);
                          else if (e.key === 'Escape') cancelEditing();
                        }}
                        autoFocus
                      />
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        style={{ minWidth: '32px', padding: '6px' }}
                        onClick={() => saveRename(project.id)}
                        disabled={isSavingName}
                        title="Salvar novo nome"
                      >
                        <Check size={14} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        style={{ minWidth: '32px', padding: '6px' }}
                        onClick={cancelEditing}
                        disabled={isSavingName}
                        title="Cancelar edição"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px', marginBottom: '8px' }}>
                      <h2
                        style={{
                          fontSize: '1.15rem',
                          fontWeight: 700,
                          color: 'var(--text-primary)',
                          lineHeight: 1.3,
                          cursor: 'pointer',
                          margin: 0,
                          wordBreak: 'break-word',
                        }}
                        onClick={() => onSelectProject(project.id)}
                        title={project.display_name || project.name}
                      >
                        {project.display_name || project.name}
                      </h2>
                      {onRenameProject && (
                        <button
                          type="button"
                          onClick={() => startEditing(project)}
                          className="btn btn-ghost btn-sm"
                          style={{ padding: '4px', minWidth: '26px', height: '26px', color: 'var(--text-muted)', flexShrink: 0 }}
                          title="Editar nome do vídeo"
                          aria-label={`Editar nome do vídeo ${project.display_name || project.name}`}
                        >
                          <Pencil size={13} />
                        </button>
                      )}
                    </div>
                  )}
                  {/* Metadados: Cortes, Tamanho, Resolução */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                      gap: '12px',
                      fontSize: '0.8rem',
                      color: 'var(--text-secondary)',
                      marginBottom: '16px',
                    }}
                  >
                    {hasCandidates && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--ai-indigo)' }}>
                        <Sparkles size={13} />
                        <strong>{project.candidates.length}</strong> cortes ranqueados
                      </span>
                    )}

                    {project.metadata?.size && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <HardDrive size={13} />
                        {formatFileSize(project.metadata.size)}
                      </span>
                    )}

                    {project.metadata?.width && project.metadata?.height && (
                      <span>
                        {project.metadata.width}×{project.metadata.height}
                      </span>
                    )}
                  </div>

                  {/* Detalhe de Erro se houver */}
                  {isFailed && project.error && (
                    <div
                      style={{
                        padding: '8px 12px',
                        backgroundColor: 'rgba(239, 68, 68, 0.08)',
                        borderRadius: 'var(--radius-sm)',
                        color: '#fca5a5',
                        fontSize: '0.78rem',
                        marginBottom: '14px',
                        lineHeight: 1.3,
                      }}
                    >
                      {project.error}
                    </div>
                  )}
                </div>

                {/* Ações do Card */}
                <div
                  style={{
                    borderTop: '1px solid var(--border-subtle)',
                    paddingTop: '14px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div style={{ display: 'flex', gap: '8px' }}>
                    {hasCandidates ? (
                      <Button
                        variant={isActive ? 'primary' : 'secondary'}
                        size="sm"
                        icon={<Sparkles size={14} />}
                        onClick={() => {
                          onSelectProject(project.id);
                          onNavigateToResults();
                        }}
                      >
                        Ver Cortes ({project.candidates.length})
                      </Button>
                    ) : (
                      <Button
                        variant={isActive ? 'primary' : 'secondary'}
                        size="sm"
                        icon={<SlidersHorizontal size={14} />}
                        onClick={() => {
                          onSelectProject(project.id);
                          onNavigateToProcess();
                        }}
                      >
                        Configurar Cortes
                      </Button>
                    )}
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {!isActive && (
                      <button
                        type="button"
                        onClick={() => onSelectProject(project.id)}
                        className="btn btn-ghost btn-sm"
                        style={{ fontSize: '0.78rem' }}
                      >
                        Selecionar
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => setProjectToDelete(project)}
                      className="btn btn-ghost btn-sm"
                      style={{ padding: '6px', minWidth: '32px', color: 'var(--text-muted)' }}
                      title="Excluir projeto e mídias locais"
                      aria-label={`Excluir projeto ${project.display_name || project.name}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Confirmação de Exclusão Modal */}
      {projectToDelete && (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-content animate-in-fade" style={{ maxWidth: '440px' }} role="dialog">
            <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
              Confirmar Exclusão
            </h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '20px', lineHeight: 1.4 }}>
              Tem certeza que deseja excluir o projeto <strong>"{projectToDelete.display_name || projectToDelete.name}"</strong>? Todos os cortes e dados de transcrição gerados serão removidos.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <Button
                variant="ghost"
                onClick={() => setProjectToDelete(null)}
                disabled={isDeleting}
              >
                Cancelar
              </Button>
              <Button
                variant="danger"
                loading={isDeleting}
                onClick={handleDeleteConfirm}
              >
                Excluir Projeto
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
