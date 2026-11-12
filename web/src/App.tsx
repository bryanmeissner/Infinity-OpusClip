import React, { useState, useEffect, useCallback } from 'react';
import type {
  Candidate,
  Edit,
  Job,
  Options,
  Project,
  ProviderConfig,
  ProviderOrder,
} from './types';
import { api } from './api/client';
import { Sidebar, NavTab } from './components/layout/Sidebar';
import { TopBar } from './components/layout/TopBar';
import { ProjectList } from './components/projects/ProjectList';
import { NewProjectModal } from './components/projects/NewProjectModal';
import { ProcessOptionsForm } from './components/process/ProcessOptionsForm';
import { JobProgressCard } from './components/process/JobProgressCard';
import { ResultsList } from './components/results/ResultsList';
import { ClipEditor } from './components/editor/ClipEditor';
import { ProviderSettings } from './components/providers/ProviderSettings';
import { UsageView } from './components/usage/UsageView';
import { ToastContainer, ToastMessage } from './components/common/Toast';
import { Button } from './components/common/Button';
import { EmptyState } from './components/common/EmptyState';
import { AlertCircle, SlidersHorizontal, Loader2, Sparkles, Scissors, FolderOpen } from 'lucide-react';

export const App: React.FC = () => {
  // Estados Principais
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [currentTab, setCurrentTab] = useState<NavTab>('projects');
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);

  // Provedores IA
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [providerOrder, setProviderOrder] = useState<ProviderOrder>({ primary: null, fallback: null });

  // Modais e Toasts
  const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [isLoadingBootstrap, setIsLoadingBootstrap] = useState(true);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);

  // Estados de Operação
  const [isProcessing, setIsProcessing] = useState(false);
  const [renderingCandidateId, setRenderingCandidateId] = useState<string | null>(null);

  const addToast = useCallback((type: 'success' | 'error' | 'info', message: string) => {
    const id = Date.now().toString() + Math.random().toString().slice(2, 6);
    setToasts((prev) => [...prev, { id, type, message }]);

    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Carregamento inicial do Bootstrap
  const loadBootstrap = useCallback(async () => {
    setIsLoadingBootstrap(true);
    setBootstrapError(null);
    try {
      const data = await api.getBootstrap();
      setProjects(data.projects || []);
      setProviders(data.providers || []);
      setProviderOrder(data.provider_order || { primary: null, fallback: null });

      const initialProject =
        data.projects?.find((p) => p.status !== 'failed' && (p.candidates?.length ?? 0) > 0) ||
        data.projects?.find((p) => p.status !== 'failed') ||
        data.projects?.[0];
      setActiveProjectId((current) => current ?? initialProject?.id ?? null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Falha ao conectar com o backend LocalClip.';
      setBootstrapError(msg);
      addToast('error', msg);
    } finally {
      setIsLoadingBootstrap(false);
    }
  }, [addToast]);

  useEffect(() => {
    loadBootstrap();
  }, [loadBootstrap]);

  const activeProject = projects.find((p) => p.id === activeProjectId) || null;

  const updateProjectInState = useCallback((updated: Project) => {
    setProjects((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  }, []);

  // Carrega detalhes completos do projeto ativo
  useEffect(() => {
    if (!activeProjectId) return;
    let isSubscribed = true;
    api
      .getProject(activeProjectId)
      .then((fullProj) => {
        if (isSubscribed) {
          updateProjectInState(fullProj);
        }
      })
      .catch((err) => {
        console.error('Falha ao carregar detalhes completos do projeto:', err);
      });
    return () => {
      isSubscribed = false;
    };
  }, [activeProjectId, updateProjectInState]);

  const hasActiveJobs = (activeProject?.jobs || []).some(
    (job) => job.state === 'queued' || job.state === 'running'
  );

  useEffect(() => {
    if (!activeProjectId || !hasActiveJobs) return;
    let disposed = false;
    let timer: number | undefined;
    const refresh = async () => {
      try {
        const project = await api.getProject(activeProjectId);
        if (disposed) return;
        updateProjectInState(project);
        if (project.jobs.some((job) => job.state === 'queued' || job.state === 'running')) {
          timer = window.setTimeout(refresh, 1500);
        }
      } catch {
        if (!disposed) timer = window.setTimeout(refresh, 3000);
      }
    };
    timer = window.setTimeout(refresh, 1500);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [activeProjectId, hasActiveJobs, updateProjectInState]);

  const handleProjectCreated = (newProject: Project) => {
    setProjects((prev) => [newProject, ...prev]);
    setActiveProjectId(newProject.id);
    setCurrentTab('process');
    addToast('success', `Projeto "${newProject.name}" importado com sucesso!`);
  };

  const handleDeleteProject = async (projectId: string) => {
    try {
      await api.deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
      if (activeProjectId === projectId) {
        const remaining = projects.filter((p) => p.id !== projectId);
        setActiveProjectId(remaining.length > 0 ? remaining[0].id : null);
        setCurrentTab('projects');
      }
      addToast('success', 'Projeto excluído com sucesso.');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Falha ao excluir o projeto.';
      addToast('error', msg);
    }
  };

  // Handlers de Processamento
  const handleStartProcess = async (options: Options) => {
    if (!activeProject) return;
    setIsProcessing(true);
    try {
      const job = await api.processProject(activeProject.id, options);
      addToast('info', 'Processamento de corte e ranking iniciado em segundo plano.');

      const updatedProject: Project = {
        ...activeProject,
        options,
        jobs: [job, ...(activeProject.jobs || [])],
      };
      updateProjectInState(updatedProject);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Falha ao iniciar o processamento.';
      addToast('error', msg);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    try {
      const updatedJob = await api.cancelJob(jobId);
      addToast('info', updatedJob.state === 'cancelled' ? 'Tarefa cancelada.' : 'Cancelamento solicitado; aguardando o worker.');

      if (activeProject) {
        const updatedJobs = (activeProject.jobs || []).map((j) => (j.id === jobId ? updatedJob : j));
        updateProjectInState({ ...activeProject, jobs: updatedJobs });
      }
      setIsProcessing(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Falha ao cancelar o processamento.';
      addToast('error', msg);
    }
  };
  const handleRetryJob = async (jobId: string) => {
    try {
      const retried = await api.retryJob(jobId);
      addToast('info', 'Processamento reiniciado a partir do checkpoint.');
      if (activeProject) {
        const updatedJobs = (activeProject.jobs || []).map((j) => (j.id === jobId ? retried : j));
        updateProjectInState({ ...activeProject, jobs: updatedJobs });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Falha ao tentar novamente a tarefa.';
      addToast('error', msg);
    }
  };

  const handleRenameProject = async (projectId: string, newName: string) => {
    try {
      const updated = await api.updateProjectName(projectId, newName);
      updateProjectInState(updated);
      addToast('success', 'Nome do vídeo atualizado com sucesso.');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Falha ao renomear o projeto.';
      addToast('error', msg);
    }
  };

  // Handlers de Candidatos e Editor
  const handleSaveCandidate = async (candidateId: string, edit: Edit) => {
    if (!activeProject) return;
    try {
      const updatedCandidate = await api.updateCandidate(activeProject.id, candidateId, edit);
      const updatedCandidates = (activeProject.candidates || []).map((c) =>
        c.id === candidateId ? updatedCandidate : c
      );
      updateProjectInState({ ...activeProject, candidates: updatedCandidates });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Falha ao salvar edições do corte.';
      addToast('error', msg);
      throw err;
    }
  };

  const handleRenderCandidate = async (candidateId: string) => {
    if (!activeProject) return;
    setRenderingCandidateId(candidateId);
    try {
      await api.renderCandidate(activeProject.id, candidateId);
      addToast('info', 'Renderização FFmpeg iniciada em segundo plano.');
      updateProjectInState(await api.getProject(activeProject.id));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Falha ao solicitar renderização.';
      addToast('error', msg);
    } finally {
      setRenderingCandidateId(null);
    }
  };

  const handleExportCandidate = (candidateId: string) => {
    if (!activeProject) return;
    const exportUrl = api.getCandidateExportUrl(activeProject.id, candidateId);
    const a = document.createElement('a');
    a.href = exportUrl;
    a.download = `corte_${candidateId.slice(0, 8)}.mp4`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    addToast('success', 'Download iniciado.');
  };

  const handleDeleteCandidate = async (candidateId: string) => {
    if (!activeProject) return;
    try {
      await api.deleteCandidate(activeProject.id, candidateId);
      const remainingCandidates = (activeProject.candidates || []).filter((c) => c.id !== candidateId);
      updateProjectInState({ ...activeProject, candidates: remainingCandidates });
      if (selectedCandidateId === candidateId) {
        setSelectedCandidateId(remainingCandidates.length > 0 ? remainingCandidates[0].id : null);
      }
      addToast('success', 'Corte removido com sucesso.');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Falha ao excluir o corte.';
      addToast('error', msg);
    }
  };

  const handleEditCandidate = (candidate: Candidate) => {
    setSelectedCandidateId(candidate.id);
    setCurrentTab('editor');
  };

  // Candidato atualmente aberto no editor
  const candidateForEditor =
    (activeProject?.candidates || []).find((c) => c.id === selectedCandidateId) ||
    (activeProject?.candidates || [])[0] ||
    null;

  // Job em execução no projeto ativo (se houver)
  const activeJob = (activeProject?.jobs || []).find(
    (j) => j.state === 'queued' || j.state === 'running'
  );

  return (
    <div className="studio-shell">
      {/* SIDEBAR DE NAVEGAÇÃO DO ESTÚDIO */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={(tab) => setCurrentTab(tab)}
        activeProject={activeProject}
        projectsCount={projects.length}
        candidatesCount={activeProject?.candidates?.length || 0}
        onOpenNewProjectModal={() => setIsNewProjectModalOpen(true)}
      />

      {/* ÁREA PRINCIPAL DO ESTÚDIO */}
      <div className="studio-main">
        {/* BARRA SUPERIOR CONTEXTUAL */}
        <TopBar
          activeProject={activeProject}
          projects={projects}
          onSelectProject={(id) => setActiveProjectId(id)}
          onOpenNewProjectModal={() => setIsNewProjectModalOpen(true)}
          activeJob={activeJob}
          onCancelJob={handleCancelJob}
        />

        {/* VIEWPORT PRINCIPAL */}
        <main className="studio-viewport" id="main-content-region">
          {isLoadingBootstrap ? (
            <div style={{ textAlign: 'center', padding: '100px 20px', color: 'var(--text-secondary)' }}>
              <Loader2 className="animate-spin" size={32} color="var(--primary)" style={{ margin: '0 auto 16px' }} />
              <p style={{ fontWeight: 600 }}>Iniciando LocalClip Studio...</p>
            </div>
          ) : bootstrapError && projects.length === 0 ? (
            <div
              className="card"
              style={{
                maxWidth: '560px',
                margin: '40px auto',
                textAlign: 'center',
                borderColor: 'var(--danger)',
              }}
            >
              <AlertCircle size={44} color="var(--danger)" style={{ margin: '0 auto 16px' }} />
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '8px' }}>
                Servidor LocalClip Desconectado
              </h2>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '20px' }}>
                Certifique-se de que o backend FastAPI está em execução na porta 8765.
              </p>
              <Button variant="primary" onClick={loadBootstrap}>
                Tentar Novamente
              </Button>
            </div>
          ) : (
            <>
              {/* Job em andamento ou recém finalizado em destaque se não estiver na tela de projetos */}
              {activeProject?.jobs?.[0] && currentTab !== 'projects' && (
                <JobProgressCard
                  job={activeJob || activeProject.jobs[0]}
                  onCancelJob={handleCancelJob}
                  onRetry={() => handleRetryJob((activeJob || activeProject.jobs[0]).id)}
                />
              )}

              {/* 1. ABA: PROJETOS & MÍDIA */}
              {currentTab === 'projects' && (
                <ProjectList
                  projects={projects}
                  activeProject={activeProject}
                  onSelectProject={(id) => setActiveProjectId(id)}
                  onOpenNewProjectModal={() => setIsNewProjectModalOpen(true)}
                  onNavigateToProcess={() => setCurrentTab('process')}
                  onNavigateToResults={() => setCurrentTab('results')}
                  onDeleteProject={handleDeleteProject}
                  onRenameProject={handleRenameProject}
                />
              )}

              {/* 2. ABA: GERAR CORTES IA */}
              {currentTab === 'process' && activeProject && (
                <div>
                  <ProcessOptionsForm
                    key={activeProject.id}
                    project={activeProject}
                    onSubmit={handleStartProcess}
                    isLoading={isProcessing || Boolean(activeJob)}
                  />
                </div>
              )}

              {/* 3. ABA: CORTES RANQUEADOS */}
              {currentTab === 'results' && activeProject && (
                <ResultsList
                  project={activeProject}
                  onEditCandidate={handleEditCandidate}
                  onRenderCandidate={handleRenderCandidate}
                  onDeleteCandidate={handleDeleteCandidate}
                  onExportCandidate={handleExportCandidate}
                  onNavigateToProcess={() => setCurrentTab('process')}
                  renderingCandidateId={renderingCandidateId}
                />
              )}

              {/* 4. ABA: EDITOR DE VÍDEO & TRANSCRIÇÃO */}
              {currentTab === 'editor' && activeProject && (
                <div>
                  {candidateForEditor ? (
                    <>
                      {/* Seletor Rápido de Corte se houver múltiplos */}
                      {(activeProject.candidates || []).length > 1 && (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '12px',
                            marginBottom: '20px',
                            backgroundColor: 'var(--bg-surface)',
                            padding: '10px 18px',
                            borderRadius: 'var(--radius-md)',
                            border: '1px solid var(--border-subtle)',
                          }}
                        >
                          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                            Alternar Corte em Edição:
                          </span>
                          <select
                            className="form-select"
                            aria-label="Alternar corte em edição"
                            style={{
                              maxWidth: '420px',
                              minHeight: '34px',
                              height: '34px',
                              padding: '4px 12px',
                              fontSize: '0.85rem',
                            }}
                            value={candidateForEditor.id}
                            onChange={(e) => setSelectedCandidateId(e.target.value)}
                          >
                            {(activeProject.candidates || []).map((c, idx) => (
                              <option key={c.id} value={c.id}>
                                #{idx + 1} • {c.title} (Potencial: {Math.round(c.score)}/100)
                              </option>
                            ))}
                          </select>
                        </div>
                      )}

                      <ClipEditor
                        key={candidateForEditor.id}
                        project={activeProject}
                        candidate={candidateForEditor}
                        onSaveCandidate={handleSaveCandidate}
                        onRenderCandidate={handleRenderCandidate}
                        onExportCandidate={handleExportCandidate}
                        onDeleteCandidate={handleDeleteCandidate}
                        isRendering={Boolean(activeJob) || renderingCandidateId === candidateForEditor.id}
                      />
                    </>
                  ) : (
                    <EmptyState
                      icon={<Scissors size={32} />}
                      title="Nenhum corte para edição"
                      description={`O projeto "${activeProject.display_name || activeProject.name}" não possui cortes gerados para editar. Gere seus clipes ou configure o processamento.`}
                      actionText="Configurar e Gerar Cortes"
                      actionIcon={<SlidersHorizontal size={16} />}
                      onAction={() => setCurrentTab('process')}
                    />
                  )}
                </div>
              )}

              {/* 5. ABA: PROVEDORES DE IA */}
              {currentTab === 'providers' && (
                <ProviderSettings
                  providers={providers}
                  providerOrder={providerOrder}
                  onRefresh={async () => {
                    const data = await api.getProviders();
                    setProviders(data.providers);
                    setProviderOrder({ primary: data.primary, fallback: data.fallback });
                  }}
                />
              )}

              {/* 6. ABA: MÉTRICAS DE USO */}
              {currentTab === 'usage' && activeProject && (
                <UsageView project={activeProject} />
              )}
            </>
          )}
        </main>
      </div>

      {/* MODAL DE IMPORTAÇÃO DE VÍDEO */}
      <NewProjectModal
        isOpen={isNewProjectModalOpen}
        onClose={() => setIsNewProjectModalOpen(false)}
        onProjectCreated={handleProjectCreated}
      />

      {/* NOTIFICAÇÕES TOASTS ACESSÍVEIS */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
};
