import React from 'react';
import {
  Film,
  SlidersHorizontal,
  Sparkles,
  Scissors,
  Bot,
  Activity,
  FolderOpen,
  Plus,
  Shield,
  Layers,
} from 'lucide-react';
import type { Project } from '../../types';
import { Badge } from '../common/Badge';

export type NavTab = 'projects' | 'process' | 'results' | 'editor' | 'providers' | 'usage';

export interface SidebarProps {
  currentTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  activeProject: Project | null;
  projectsCount: number;
  candidatesCount: number;
  onOpenNewProjectModal: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  activeProject,
  projectsCount,
  candidatesCount,
  onOpenNewProjectModal,
}) => {
  return (
    <aside className="studio-sidebar" aria-label="Navegação do Estúdio">
      <div>
        {/* Marca & Logo */}
        <div className="studio-sidebar-header">
          <a
            href="#"
            className="studio-brand"
            onClick={(e) => {
              e.preventDefault();
              onSelectTab('projects');
            }}
          >
            <div className="studio-logo-icon" aria-hidden="true">
              <Film size={20} />
            </div>
            <div className="studio-brand-text">
              <div className="studio-brand-title">
                LocalClip
                <span className="studio-brand-badge">STUDIO</span>
              </div>
              <span className="studio-brand-tagline">Editor IA Local-First</span>
            </div>
          </a>
        </div>

        {/* Lista de Navegação Principal */}
        <nav className="studio-nav-list" aria-label="Menu principal">
          <div className="studio-nav-heading">
            Fluxo Criativo
          </div>

          <div className="studio-nav-item">
            <button
              onClick={() => onSelectTab('projects')}
              className={`studio-nav-button ${currentTab === 'projects' ? 'active' : ''}`}
              aria-current={currentTab === 'projects' ? 'page' : undefined}
            >
              <span className="studio-nav-icon">
                <FolderOpen size={18} />
              </span>
              <span>Projetos & Mídia</span>
              {projectsCount > 0 && (
                <span className="studio-nav-badge">{projectsCount}</span>
              )}
            </button>
          </div>

          <div className="studio-nav-item">
            <button
              onClick={() => onSelectTab('process')}
              className={`studio-nav-button ${currentTab === 'process' ? 'active' : ''}`}
              aria-current={currentTab === 'process' ? 'page' : undefined}
              disabled={!activeProject}
              title={!activeProject ? 'Selecione ou crie um projeto primeiro' : undefined}
            >
              <span className="studio-nav-icon">
                <SlidersHorizontal size={18} />
              </span>
              <span>Gerar Cortes IA</span>
            </button>
          </div>

          <div className="studio-nav-item">
            <button
              onClick={() => onSelectTab('results')}
              className={`studio-nav-button ${currentTab === 'results' ? 'active' : ''}`}
              aria-current={currentTab === 'results' ? 'page' : undefined}
              disabled={!activeProject}
              title={!activeProject ? 'Selecione ou crie um projeto primeiro' : undefined}
            >
              <span className="studio-nav-icon">
                <Sparkles size={18} />
              </span>
              <span>Cortes Ranqueados</span>
              {candidatesCount > 0 && (
                <span className="studio-nav-badge">{candidatesCount}</span>
              )}
            </button>
          </div>

          <div className="studio-nav-item">
            <button
              onClick={() => onSelectTab('editor')}
              className={`studio-nav-button ${currentTab === 'editor' ? 'active' : ''}`}
              aria-current={currentTab === 'editor' ? 'page' : undefined}
              disabled={!activeProject}
              title={!activeProject ? 'Selecione ou crie um projeto primeiro' : undefined}
            >
              <span className="studio-nav-icon">
                <Scissors size={18} />
              </span>
              <span>Editor de Vídeo</span>
            </button>
          </div>

          <div className="studio-nav-heading">
            Configurações & IA
          </div>

          <div className="studio-nav-item">
            <button
              onClick={() => onSelectTab('providers')}
              className={`studio-nav-button ${currentTab === 'providers' ? 'active' : ''}`}
              aria-current={currentTab === 'providers' ? 'page' : undefined}
            >
              <span className="studio-nav-icon">
                <Bot size={18} />
              </span>
              <span>Provedores de IA</span>
            </button>
          </div>

          <div className="studio-nav-item">
            <button
              onClick={() => onSelectTab('usage')}
              className={`studio-nav-button ${currentTab === 'usage' ? 'active' : ''}`}
              aria-current={currentTab === 'usage' ? 'page' : undefined}
              disabled={!activeProject}
              title={!activeProject ? 'Selecione um projeto para ver métricas' : undefined}
            >
              <span className="studio-nav-icon">
                <Activity size={18} />
              </span>
              <span>Métricas de Uso</span>
            </button>
          </div>
        </nav>
      </div>

      {/* Rodapé da Sidebar: Privacidade & Engine */}
      <div className="studio-sidebar-footer">
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '6px',
            fontSize: '0.78rem',
            fontWeight: 600,
            color: 'var(--text-secondary)',
          }}
        >
          <Shield size={14} color="var(--emerald)" aria-hidden="true" />
          <span>Privacidade Total</span>
        </div>
        <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', lineHeight: 1.3 }}>
          Processamento e render 100% locais no Fedora Linux. Sem envio involuntário de dados.
        </p>
      </div>
    </aside>
  );
};
