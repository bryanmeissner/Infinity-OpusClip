/**
 * Tipos de domínio e contratos HTTP do LocalClip.
 * Alinhado estritamente com schemas.py e local://implementation-contract.md.
 */

export type ClipModel = 'Auto' | 'Conversa / Talking Head' | 'Multimodal / Clip Anything';

export type ContentGenre =
  | 'Auto'
  | 'Podcast'
  | 'Lifestyle'
  | 'Vlog'
  | 'Viagem'
  | 'Comida'
  | 'Beleza'
  | 'Fitness'
  | 'Esportes'
  | 'Futebol'
  | 'Basquete'
  | 'Marketing'
  | 'Talking Head'
  | 'Discurso'
  | 'Comentário'
  | 'Entrevista'
  | 'Entretenimento'
  | 'Filmes'
  | 'Reality'
  | 'Notícias'
  | 'Educacional'
  | 'Produtos'
  | 'História'
  | 'Ciência e tecnologia'
  | 'Música'
  | 'Games'
  | 'Outros';
export type ClipDuration =
  | 'Auto'
  | '<30s'
  | '30s–59s'
  | '60s–89s'
  | '90s–3min'
  | '3min–5min'
  | '5min–10min'
  | 'personalizada';

export type ClipFormat = '9:16' | '1:1' | '16:9';

export type ClipPlatform = 'TikTok' | 'YouTube Shorts' | 'Instagram Reels';

export type SubtitleStyle = 'classic' | 'highlight';

export type SubtitlePosition = 'bottom' | 'center' | 'top';

export interface Word {
  start: number;
  end: number;
  word: string;
  score?: number;
}

export interface RemoveRange {
  start: number;
  end: number;
}

export interface Edit {
  start: number;
  end: number;
  title: string;
  format: ClipFormat;
  reframe: boolean;
  auto_zoom?: boolean;
  zoom_level?: number;
  subtitles: boolean;
  subtitle_style: SubtitleStyle;
  subtitle_size: number;
  subtitle_position: SubtitlePosition;
  crop_x: number | null; // 0.0 a 1.0 (centro horizontal do recorte)
  remove_ranges: RemoveRange[];
  words: Word[];
}

export interface CandidateScores {
  hook: number;
  flow: number;
  value: number;
  platform_fit?: number;
  narrative: number;
  emotion: number;
  audio: number;
  visual: number;
  shareability: number;
  context_penalty?: number;
  silence_penalty?: number;
  [key: string]: number | undefined;
}

export interface Candidate {
  id: string;
  start: number;
  end: number;
  title: string;
  summary: string;
  score: number; // 0 a 100
  scores: CandidateScores;
  reason: string;
  mode: 'hybrid' | 'local';
  weights?: Record<string, number>;
  request_boost?: number;
  resolved_clip_model?: ClipModel;
  words: Word[];
  edit: Edit;
  rendered?: boolean;
  revision?: number;
}

export type JobKind = 'ingest' | 'preview' | 'process' | 'render';
export type JobState = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted';

export interface Job {
  id: string;
  project_id?: string;
  kind: JobKind;
  candidate_id?: string | null;
  state: JobState;
  stage: string;
  progress: number; // 0.0 a 1.0 ou 0 a 100
  error: string | null;
  failed_provider?: string | null;
  checkpoint?: Record<string, unknown> | null;
  attempts?: number;
  cancel?: number;
  created_at: number | string;
  updated_at: number | string;
}

export interface ProjectMetadata {
  duration: number; // em segundos
  width: number;
  height: number;
  fps: number;
  size: number; // em bytes
  codec: string;
  has_audio: boolean;
  [key: string]: unknown;
}

export interface Options {
  clip_model: ClipModel;
  genre: ContentGenre | string;
  duration?: ClipDuration;
  durations?: ClipDuration[] | string[];
  custom_min: number;
  custom_max: number;
  format: ClipFormat;
  platform: ClipPlatform;
  auto_title: boolean;
  reframe: boolean;
  subtitles: boolean;
  subtitle_style: SubtitleStyle;
  subtitle_size: number;
  subtitle_position: SubtitlePosition;
  request: string;
  start: number;
  end: number | null;
  results?: number | null;
  allow_images: boolean; // Consentimento explícito para 1-2 frames em análise multimodal
}

export interface Project {
  id: string;
  name: string;
  display_name?: string;
  original_filename?: string;
  source_title?: string;
  metadata: ProjectMetadata;
  status:
    | 'importing'
    | 'ready'
    | 'processing'
    | 'rendering'
    | 'failed'
    | 'interrupted'
    | 'created'
    | 'analyzing'
    | 'ranking'
    | 'error';
  options: Options;
  created_at: number | string;
  error: string | null;
  jobs: Job[];
  candidates: Candidate[];
}

export type ProviderKind = 'openai' | 'gemini' | 'anthropic' | 'compatible' | 'glm' | 'omp' | 'openrouter';

export interface ProviderConfig {
  id: string;
  name?: string;
  kind: ProviderKind;
  model: string;
  base_url: string;
  enabled: boolean;
  has_key: boolean;
  api_key?: string; // Enviado apenas pelo formulário, nunca retornado pelo backend
  credential_error?: string | null;
}

export interface ProviderOrder {
  primary: string | null;
  fallback: string | null;
}

export interface ProviderTestResult {
  ok: boolean;
  message: string;
  latency_ms?: number;
}

export interface OmpAccount {
  id: string;
  name: string;
  logged_in: boolean;
}

export interface OmpLoginState {
  provider: string;
  running: boolean;
  exit_code: number | null;
  auth_url: string | null;
  error?: string | null;
  google_cloud_project?: string | null;
}

export interface OmpStatus {
  installed: boolean;
  providers: OmpAccount[];
  login: OmpLoginState | null;
  google_cloud_project?: string | null;
}

export interface CuratedModel {
  id: string;
  name: string;
  description: string;
  recommended: boolean;
  badge?: string;
}

export interface DiscoveredModel {
  id: string;
  name: string;
  description?: string;
  context_tokens?: number;
  logged_in?: boolean;
}

export interface ProviderModelsResponse {
  provider: string;
  kind: ProviderKind;
  curated: CuratedModel[];
  discovered: DiscoveredModel[];
  source: 'api' | 'curated_fallback' | 'unauthenticated' | 'auth_error';
  error: string | null;
}

export interface BootstrapData {
  options: {
    genres: string[];
    durations: string[];
    clip_models: string[];
    platforms: string[];
  };
  projects: Project[];
  providers: ProviderConfig[];
  provider_order: ProviderOrder;
  capabilities: Record<string, unknown>;
}

export interface UsageRecord {
  id?: string;
  provider: string;
  model: string;
  calls: number;
  tokens?: number;
  duration: number;
  timestamp: string;
  error?: string | null;
}

export interface TimelineWord {
  start: number;
  end: number;
  word: string;
}

export interface TimelineSegment {
  start: number;
  end: number;
  text: string;
  words: TimelineWord[];
  speaker: string | null;
}

export interface Timeline {
  start: number;
  end: number;
  segments: TimelineSegment[];
  words: TimelineWord[];
  scenes: Array<{ start: number; end: number }>;
  silence: Array<{ start: number; end: number }>;
  audio_events: Array<{ start: number; end: number; type: string; confidence?: number }>;
  visual_events: Array<{ start: number; end: number; type: string; confidence?: number }>;
  tracks: Array<{ time: number; boxes: Array<{ x: number; y: number; w: number; h: number }> }>;
  keywords: string[];
  semantic_tags: string[];
}
