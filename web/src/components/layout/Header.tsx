import React from 'react';
import {
  Film,
  SlidersHorizontal,
  Sparkles,
  Scissors,
  Bot,
  Activity,
  FolderOpen,
  ChevronDown,
} from 'lucide-react';
import type { Project } from '../../types';
import { Badge } from '../common/Badge';

export type NavTab = 'projects' | 'process' | 'results' | 'editor' | 'providers' | 'usage';

export interface HeaderProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  activeProject: Project | null;
  projects: Project[];
  onSelectProject: (projectId: string) => void;
  onOpenNewProjectModal: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentTab,
  onSelectTab,
  activeProject,
  projects,
  onSelectProject,
  onOpenNewProjectModal,
}) => {
  const isJobRunning =
    (activeProject?.jobs || []).some((j) => j.state === 'queued' || j.state === 'running');

  return (
    <header className="app-header">
      <div className="app-header-inner">
        {/* Marca & Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              onSelectTab('projects');
            }}
            className="brand-section"
            aria-label="LocalClip início"
          >
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--primary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 12px var(--primary-glow)',
              }}
            >
              <Film size={20} color="#ffffff" aria-hidden="true" />
            </div>
            <span>LocalClip</span>
            <span className="brand-badge">LOCAL-FIRST</span>
          </a>

          {/* Seletor de Projeto Atual */}
          {projects.length > 0 && (
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  backgroundColor: 'var(--bg-canvas)',
                  padding: '6px 12px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.85rem',
                }}
              >
                <FolderOpen size={15} color="var(--text-muted)" aria-hidden="true" />
                <select
                  value={activeProject?.id || ''}
                  onChange={(e) => {
                    if (e.target.value === '__new__') {
                      onOpenNewProjectModal();
                    } else if (e.target.value) {
                      onSelectProject(e.target.value);
                    }
                  }}
                  style={{
                    backgroundColor: 'transparent',
                    border: 'none',
                    color: 'var(--text-primary)',
                    fontFamily: 'inherit',
                    fontSize: 'inherit',
                    cursor: 'pointer',
                    outline: 'none',
                    fontWeight: 600,
                    maxWidth: '180px',
                  }}
                  aria-label="Selecionar projeto ativo"
                >
                  <option value="" disabled style={{ background: '#131728' }}>
                    Selecionar projeto...
                  </option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id} style={{ background: '#131728' }}>
                      {p.name}
                    </option>
                  ))}
                  <option value="__new__" style={{ background: '#131728', color: 'var(--primary)' }}>
                    + Novo Projeto
                  </option>
                </select>
                <ChevronDown size={14} color="var(--text-muted)" aria-hidden="true" />
              </div>

              {isJobRunning && (
                <div style={{ marginLeft: '8px' }}>
                  <Badge variant="amber" icon={<Activity size={12} className="animate-spin" />}>
                    Processando
                  </Badge>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Abas de Navegação */}
        <nav className="nav-tabs" aria-label="Navegação primária">
          <button
            onClick={() => onSelectTab('projects')}
            className={`nav-tab-btn ${currentTab === 'projects' ? 'active' : ''}`}
            aria-current={currentTab === 'projects' ? 'page' : undefined}
          >
            <FolderOpen size={16} aria-hidden="true" />
            <span>Projetos</span>
          </button>

          <button
            onClick={() => onSelectTab('process')}
            disabled={!activeProject}
            className={`nav-tab-btn ${currentTab === 'process' ? 'active' : ''}`}
            aria-current={currentTab === 'process' ? 'page' : undefined}
            title={!activeProject ? 'Selecione ou crie um projeto primeiro' : undefined}
          >
            <SlidersHorizontal size={16} aria-hidden="true" />
            <span>Processar</span>
          </button>

          <button
            onClick={() => onSelectTab('results')}
            disabled={!activeProject || ((activeProject.candidates || []).length === 0 && !isJobRunning)}
            className={`nav-tab-btn ${currentTab === 'results' ? 'active' : ''}`}
            aria-current={currentTab === 'results' ? 'page' : undefined}
            title={
              !activeProject
                ? 'Selecione um projeto primeiro'
                : (activeProject.candidates || []).length === 0
                ? 'Nenhum resultado processado ainda'
                : undefined
            }
          >
            <Sparkles size={16} aria-hidden="true" />
            <span>Resultados</span>
            {activeProject && (activeProject.candidates || []).length > 0 && (
              <span
                style={{
                  backgroundColor: 'var(--primary)',
                  color: 'white',
                  borderRadius: 'var(--radius-full)',
                  padding: '1px 6px',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                }}
              >
                {(activeProject.candidates || []).length}
              </span>
            )}
          </button>

          <button
            onClick={() => onSelectTab('editor')}
            disabled={!activeProject || (activeProject.candidates || []).length === 0}
            className={`nav-tab-btn ${currentTab === 'editor' ? 'active' : ''}`}
            aria-current={currentTab === 'editor' ? 'page' : undefined}
          >
            <Scissors size={16} aria-hidden="true" />
            <span>Editor</span>
          </button>

          <button
            onClick={() => onSelectTab('providers')}
            className={`nav-tab-btn ${currentTab === 'providers' ? 'active' : ''}`}
            aria-current={currentTab === 'providers' ? 'page' : undefined}
          >
            <Bot size={16} aria-hidden="true" />
            <span>Provedores IA</span>
          </button>

          <button
            onClick={() => onSelectTab('usage')}
            disabled={!activeProject}
            className={`nav-tab-btn ${currentTab === 'usage' ? 'active' : ''}`}
            aria-current={currentTab === 'usage' ? 'page' : undefined}
          >
            <Activity size={16} aria-hidden="true" />
            <span>Métricas</span>
          </button>
        </nav>
      </div>
    </header>
  );
};
