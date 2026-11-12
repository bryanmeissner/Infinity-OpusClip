import type {
  BootstrapData,
  Candidate,
  Edit,
  Job,
  Options,
  Project,
  ProviderConfig,
  ProviderOrder,
  ProviderKind,
  CuratedModel,
  OmpStatus,
  OmpLoginState,
  ProviderModelsResponse,
  ProviderTestResult,
  Timeline,
  UsageRecord,
} from '../types';

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(`Erro ${status}: ${detail}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorDetail = response.statusText || 'Erro inesperado do servidor';
    try {
      const errorJson = (await response.json()) as unknown;
      if (
        errorJson &&
        typeof errorJson === 'object' &&
        'detail' in errorJson &&
        typeof errorJson.detail === 'string'
      ) {
        errorDetail = errorJson.detail;
      }
    } catch {
      // Falha ao ler JSON de erro; mantém mensagem de statusText
    }
    throw new ApiError(response.status, errorDetail);
  }

  // Verifica se há corpo de resposta
  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return (await response.json()) as T;
  }
  return null as unknown as T;
}
export function normalizeJob(raw: unknown): Job {
  const record = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const rawKind = String(record.kind || record.type || 'process');
  const kind: Job['kind'] =
    rawKind === 'analyze' || rawKind === 'process'
      ? 'process'
      : rawKind === 'ingest'
      ? 'ingest'
      : rawKind === 'preview'
      ? 'preview'
      : 'render';

  const rawState = String(record.state || record.status || 'queued');
  const state: Job['state'] =
    rawState === 'running'
      ? 'running'
      : rawState === 'completed'
      ? 'completed'
      : rawState === 'failed'
      ? 'failed'
      : rawState === 'cancelled'
      ? 'cancelled'
      : rawState === 'interrupted'
      ? 'interrupted'
      : 'queued';

  return {
    id: String(record.id || ''),
    project_id: record.project_id ? String(record.project_id) : undefined,
    kind,
    candidate_id: (record.candidate_id as string | null) ?? null,
    state,
    stage: String(record.stage || ''),
    progress: typeof record.progress === 'number' ? record.progress : 0,
    error: record.error ? String(record.error) : null,
    failed_provider: record.failed_provider ? String(record.failed_provider) : null,
    checkpoint: (record.checkpoint && typeof record.checkpoint === 'object' ? record.checkpoint : null) as Record<string, unknown> | null,
    attempts: typeof record.attempts === 'number' ? record.attempts : undefined,
    cancel: record.cancel ? Number(record.cancel) : 0,
    created_at: (record.created_at as number | string) ?? Date.now(),
    updated_at: (record.updated_at as number | string) ?? Date.now(),
  };
}

export function normalizeProject(raw: unknown): Project {
  const record = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const jobsList = Array.isArray(record.jobs) ? record.jobs : [];
  const candidatesList = Array.isArray(record.candidates) ? record.candidates : [];
  const jobs: Job[] = jobsList.map(normalizeJob);
  const candidates: Candidate[] = candidatesList as Candidate[];
  const metadata = (record.metadata && typeof record.metadata === 'object'
    ? record.metadata
    : {
        duration: 0,
        width: 0,
        height: 0,
        fps: 0,
        size: 0,
        codec: '',
        has_audio: false,
      }) as Project['metadata'];
  const options = (record.options && typeof record.options === 'object'
    ? record.options
    : {}) as Options;
  const displayName = String(record.display_name || record.name || 'Sem nome');

  return {
    id: String(record.id || ''),
    name: displayName,
    display_name: displayName,
    original_filename: record.original_filename ? String(record.original_filename) : undefined,
    source_title: record.source_title ? String(record.source_title) : undefined,
    metadata,
    status: (record.status as Project['status']) || 'ready',
    options,
    created_at: (record.created_at as number | string) ?? Date.now(),
    error: record.error ? String(record.error) : null,
    jobs,
    candidates,
  };
}
export const api = {
  // Bootstrap
  async getBootstrap(): Promise<BootstrapData> {
    const res = await fetch('/api/bootstrap');
    const data = await handleResponse<BootstrapData>(res);
    return {
      ...data,
      projects: Array.isArray(data.projects) ? data.projects.map(normalizeProject) : [],
      providers: Array.isArray(data.providers) ? data.providers : [],
      provider_order: data.provider_order || { primary: null, fallback: null },
      options: data.options || { genres: [], durations: [], clip_models: [], platforms: [] },
    };
  },

  // Projetos
  async getProjects(): Promise<Project[]> {
    const res = await fetch('/api/projects');
    const projects = await handleResponse<Project[]>(res);
    return Array.isArray(projects) ? projects.map(normalizeProject) : [];
  },

  async getProject(id: string): Promise<Project> {
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}`);
    const proj = await handleResponse<Project>(res);
    return normalizeProject(proj);
  },

  async createProjectFromFile(file: File): Promise<Project> {
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch('/api/projects', {
      method: 'POST',
      headers: {
        'X-LocalClip': '1',
      },
      body: formData,
    });
    const proj = await handleResponse<Project>(res);
    return normalizeProject(proj);
  },

  async createProjectFromUrl(url: string): Promise<Project> {
    const res = await fetch('/api/projects/url', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-LocalClip': '1',
      },
      body: JSON.stringify({ url }),
    });
    const proj = await handleResponse<Project>(res);
    return normalizeProject(proj);
  },

  async deleteProject(id: string): Promise<{ ok: boolean }> {
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: {
        'X-LocalClip': '1',
      },
    });
    return handleResponse<{ ok: boolean }>(res);
  },
  async updateProjectName(id: string, displayName: string): Promise<Project> {
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-LocalClip': '1',
      },
      body: JSON.stringify({ display_name: displayName.trim() }),
    });
    const proj = await handleResponse<Project>(res);
    return normalizeProject(proj);
  },

  getProjectThumbnailUrl(projectId: string): string {
    return `/api/projects/${encodeURIComponent(projectId)}/thumbnail`;
  },

  async processProject(id: string, options: Partial<Options>): Promise<Job> {
    const res = await fetch(`/api/projects/${encodeURIComponent(id)}/process`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-LocalClip': '1',
      },
      body: JSON.stringify(options),
    });
    const job = await handleResponse<Job>(res);
    return normalizeJob(job);
  },

  // Jobs
  async cancelJob(jobId: string): Promise<Job> {
    const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: 'POST',
      headers: {
        'X-LocalClip': '1',
      },
    });
    const job = await handleResponse<Job>(res);
    return normalizeJob(job);
  },
  async retryJob(jobId: string): Promise<Job> {
    const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: 'POST',
      headers: {
        'X-LocalClip': '1',
      },
    });
    const job = await handleResponse<Job>(res);
    return normalizeJob(job);
  },
  // Mídia e Timeline
  getSourceUrl(projectId: string): string {
    return `/api/projects/${encodeURIComponent(projectId)}/source`;
  },

  async getTimeline(projectId: string): Promise<Timeline> {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/timeline`);
    return handleResponse<Timeline>(res);
  },

  // Candidatos & Edição
  async updateCandidate(projectId: string, candidateId: string, edit: Edit): Promise<Candidate> {
    const sanitizedWords = Array.isArray(edit.words)
      ? edit.words.map((w) => ({
          start: Number(w.start),
          end: Number(w.end),
          word: String(w.word || ''),
        }))
      : [];

    const payload = {
      ...edit,
      words: sanitizedWords,
    };

    const res = await fetch(
      `/api/projects/${encodeURIComponent(projectId)}/candidates/${encodeURIComponent(candidateId)}`,
      {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-LocalClip': '1',
        },
        body: JSON.stringify(payload),
      }
    );
    return handleResponse<Candidate>(res);
  },

  async renderCandidate(projectId: string, candidateId: string): Promise<Job> {
    const res = await fetch(
      `/api/projects/${encodeURIComponent(projectId)}/candidates/${encodeURIComponent(candidateId)}/render`,
      {
        method: 'POST',
        headers: {
          'X-LocalClip': '1',
        },
      }
    );
    const job = await handleResponse<Job>(res);
    return normalizeJob(job);
  },

  getCandidateVideoUrl(projectId: string, candidateId: string): string {
    return `/api/projects/${encodeURIComponent(projectId)}/candidates/${encodeURIComponent(candidateId)}/video`;
  },

  getCandidateExportUrl(projectId: string, candidateId: string): string {
    return `/api/projects/${encodeURIComponent(projectId)}/candidates/${encodeURIComponent(candidateId)}/export`;
  },

  async deleteCandidate(projectId: string, candidateId: string): Promise<{ ok: boolean }> {
    const res = await fetch(
      `/api/projects/${encodeURIComponent(projectId)}/candidates/${encodeURIComponent(candidateId)}`,
      {
        method: 'DELETE',
        headers: {
          'X-LocalClip': '1',
        },
      }
    );
    return handleResponse<{ ok: boolean }>(res);
  },

  // Provedores IA
  async getProviders(): Promise<{
    providers: ProviderConfig[];
    primary: string | null;
    fallback: string | null;
  }> {
    const res = await fetch('/api/providers');
    return handleResponse<{
      providers: ProviderConfig[];
      primary: string | null;
      fallback: string | null;
    }>(res);
  },

  async updateProvider(id: string, config: ProviderConfig): Promise<ProviderConfig> {
    const payload = {
      kind: config.kind,
      model: String(config.model || '').trim(),
      base_url: String(config.base_url || '').trim(),
      enabled: Boolean(config.enabled),
      api_key: config.api_key ? String(config.api_key).trim() : null,
    };
    const res = await fetch(`/api/providers/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-LocalClip': '1',
      },
      body: JSON.stringify(payload),
    });
    return handleResponse<ProviderConfig>(res);
  },

  async deleteProvider(id: string): Promise<{ ok: boolean }> {
    const res = await fetch(`/api/providers/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: {
        'X-LocalClip': '1',
      },
    });
    return handleResponse<{ ok: boolean }>(res);
  },

  async testProvider(id: string, config: Partial<ProviderConfig>): Promise<ProviderTestResult> {
    const res = await fetch(`/api/providers/${encodeURIComponent(id)}/test`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-LocalClip': '1',
      },
      body: JSON.stringify(config),
    });
    return handleResponse<ProviderTestResult>(res);
  },

  async getProviderCatalog(): Promise<Record<ProviderKind, CuratedModel[]>> {
    const res = await fetch('/api/providers/catalog', {
      headers: { 'X-LocalClip': '1' },
    });
    return handleResponse<Record<ProviderKind, CuratedModel[]>>(res);
  },

  async getProviderModels(
    providerId: string,
    customConfig?: Partial<ProviderConfig>
  ): Promise<ProviderModelsResponse> {
    const url = `/api/providers/${encodeURIComponent(providerId)}/models`;
    const options: RequestInit = customConfig
      ? {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-LocalClip': '1',
          },
          body: JSON.stringify(customConfig),
        }
      : {
          method: 'GET',
          headers: {
            'X-LocalClip': '1',
          },
        };
    const res = await fetch(url, options);
    return handleResponse<ProviderModelsResponse>(res);
  },

  async getOmpStatus(): Promise<OmpStatus> {
    const res = await fetch('/api/omp/status');
    return handleResponse<OmpStatus>(res);
  },

  async startOmpLogin(provider: string, googleCloudProject?: string | null): Promise<OmpLoginState> {
    const res = await fetch('/api/omp/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-LocalClip': '1',
      },
      body: JSON.stringify({
        provider,
        google_cloud_project: googleCloudProject == null ? null : googleCloudProject.trim(),
      }),
    });
    return handleResponse<OmpLoginState>(res);
  },

  async updateProviderOrder(order: ProviderOrder): Promise<ProviderOrder> {
    const res = await fetch('/api/provider-order', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-LocalClip': '1',
      },
      body: JSON.stringify(order),
    });
    return handleResponse<ProviderOrder>(res);
  },

  // Uso de IA
  async getProjectUsage(projectId: string): Promise<UsageRecord[]> {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/usage`);
    return handleResponse<UsageRecord[]>(res);
  },
};
