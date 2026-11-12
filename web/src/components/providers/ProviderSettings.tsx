import React, { useState, useEffect } from 'react';
import {
  Bot,
  CheckCircle2,
  AlertTriangle,
  Zap,
  ShieldCheck,
  Trash2,
  Lock,
  Eye,
  EyeOff,
  Layers,
  RefreshCw,
  Server,
  Sparkles,
  Info,
  ExternalLink,
  Loader2,
  Sliders,
  Check,
  ChevronRight,
  Globe,
  Key,
} from 'lucide-react';
import type {
  CuratedModel,
  DiscoveredModel,
  OmpStatus,
  ProviderConfig,
  ProviderOrder,
  ProviderTestResult,
} from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { ProviderLogo } from '../common/ProviderLogo';
import { api } from '../../api/client';

export interface ProviderSettingsProps {
  providers: ProviderConfig[];
  providerOrder: ProviderOrder;
  onRefresh: () => Promise<void>;
}

const DEFAULT_PRESETS: Array<{
  id: string;
  name: string;
  kind: ProviderConfig['kind'];
  model: string;
  base_url: string;
  desc: string;
}> = [
  {
    id: 'omp',
    name: 'Conta logada via OMP (sem chave de API)',
    kind: 'omp',
    model: 'google-antigravity/gemini-3.8-flash',
    base_url: '',
    desc: 'Conecta contas por assinatura (Google, ChatGPT, Claude, Z.AI) via OMP, respeitando limites e cotas por janela de cada plano.',
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    kind: 'openrouter',
    model: 'openai/gpt-4o-mini',
    base_url: 'https://openrouter.ai/api/v1',
    desc: 'Acesso unificado a centenas de modelos de IA (Claude, GPT-4o, Llama, Gemini) com uma única chave de API.',
  },
  {
    id: 'openai',
    name: 'OpenAI',
    kind: 'openai',
    model: 'gpt-6-luna',
    base_url: 'https://api.openai.com/v1',
    desc: 'Modelos GPT-6 e GPT-5.6 pela API oficial com chave.',
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    kind: 'gemini',
    model: 'gemini-3.8-flash',
    base_url: '',
    desc: 'Modelos Gemini com ampla janela de contexto e análise multimodal.',
  },
  {
    id: 'anthropic',
    name: 'Anthropic Claude',
    kind: 'anthropic',
    model: 'claude-sonnet-5-5',
    base_url: 'https://api.anthropic.com/v1',
    desc: 'Modelos Claude para refinamento de texto de alta fidelidade e retenção.',
  },
  {
    id: 'compatible',
    name: 'OpenAI-Compatible (Ollama / Local)',
    kind: 'compatible',
    model: 'llama3.2',
    base_url: 'http://localhost:11434/v1',
    desc: 'Servidores locais compatíveis: Ollama, vLLM ou LM Studio.',
  },
  {
    id: 'glm',
    name: 'Z.AI (GLM)',
    kind: 'glm',
    model: 'glm-4.7',
    base_url: 'https://api.z.ai/api/paas/v4',
    desc: 'Modelos GLM-4.x e GLM-5.x pela API Z.AI (GLM-4.5 Flash gratuito).',
  },
];

const OMP_POLL_MS = 2000;

export const ProviderSettings: React.FC<ProviderSettingsProps> = ({
  providers,
  providerOrder,
  onRefresh,
}) => {
  const allProviders: ProviderConfig[] = DEFAULT_PRESETS.map((preset) => {
    const existing = providers.find((p) => p.id === preset.id);
    if (existing) {
      return {
        ...existing,
        name: existing.name || preset.name,
        kind: existing.kind || preset.kind,
        base_url: existing.base_url ?? preset.base_url,
      };
    }
    return {
      id: preset.id,
      name: preset.name,
      kind: preset.kind,
      model: preset.model,
      base_url: preset.base_url,
      enabled: false,
      has_key: false,
    };
  });
  for (const p of providers) {
    if (!allProviders.some((ap) => ap.id === p.id)) {
      allProviders.push(p);
    }
  }

  const [providerForms, setProviderForms] = useState<
    Record<string, { model: string; base_url: string; api_key: string; enabled: boolean }>
  >(() => {
    const initial: Record<string, { model: string; base_url: string; api_key: string; enabled: boolean }> = {};
    for (const p of allProviders) {
      initial[p.id] = {
        model: p.model || '',
        base_url: p.base_url || '',
        api_key: '',
        enabled: p.enabled,
      };
    }
    return initial;
  });

  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [testingId, setTestingId] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, ProviderTestResult>>({});
  const [actionSuccess, setActionSuccess] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<Record<string, string>>({});
  const [orderError, setOrderError] = useState<string | null>(null);
  const [orderSuccess, setOrderSuccess] = useState<string | null>(null);
  // Catálogo curado
  const [catalog, setCatalog] = useState<Record<string, CuratedModel[]>>({});
  const [discoveredModels, setDiscoveredModels] = useState<Record<string, DiscoveredModel[]>>({});
  const [loadingModelsId, setLoadingModelsId] = useState<string | null>(null);
  const [ompStatus, setOmpStatus] = useState<OmpStatus | null>(null);
  const [ompLoginStarting, setOmpLoginStarting] = useState<string | null>(null);
  const [ompError, setOmpError] = useState<string | null>(null);
  const [customModelMode, setCustomModelMode] = useState<Record<string, boolean>>({});
  const [googleCloudProject, setGoogleCloudProject] = useState<string>('');

  const ompLoginRunning = Boolean(ompStatus?.login?.running);
  const ompLoggedIn = Boolean(ompStatus?.providers.some((acc) => acc.logged_in));

  const refreshOmpStatus = async () => {
    try {
      setOmpStatus(await api.getOmpStatus());
    } catch (err: unknown) {
      setOmpError(err instanceof Error ? err.message : 'Falha ao consultar o OMP.');
    }
  };

  useEffect(() => {
    let disposed = false;
    api.getProviderCatalog()
      .then((cat) => {
        if (!disposed && cat) setCatalog(cat);
      })
      .catch(() => {});
    api.getOmpStatus()
      .then((st) => {
        if (!disposed) setOmpStatus(st);
        if (!disposed) setGoogleCloudProject(st.google_cloud_project || '');
      })
      .catch(() => {});
    return () => {
      disposed = true;
    };
  }, []);

  // Enquanto o login no navegador estiver aberto, acompanha o processo `omp login`.
  useEffect(() => {
    if (!ompLoginRunning) return;
    const timer = window.setInterval(() => {
      api.getOmpStatus()
        .then((st) => {
          setOmpStatus(st);
          if (!st.login?.running) {
            const ompProvider = allProviders.find((p) => p.kind === 'omp');
            if (ompProvider) handleFetchModels(ompProvider).catch(() => {});
          }
        })
        .catch(() => {});
    }, OMP_POLL_MS);
    return () => window.clearInterval(timer);
  }, [ompLoginRunning]);

  useEffect(() => {
    for (const p of allProviders) {
      const eligible = p.kind === 'omp' ? Boolean(ompStatus?.installed) : p.enabled || p.has_key || p.kind === 'compatible';
      if (eligible && !discoveredModels[p.id]) {
        handleFetchModels(p).catch(() => {});
      }
    }
  }, [providers, ompStatus?.installed]);

  const handleFieldChange = (id: string, field: string, value: string | boolean) => {
    setProviderForms((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        [field]: value,
      },
    }));
  };

  // Configuração atual do formulário (ainda não salva); chave vazia = usar a do keyring.
  const formConfig = (p: ProviderConfig): Partial<ProviderConfig> => {
    const form = providerForms[p.id];
    return {
      kind: p.kind,
      model: (form?.model || p.model || 'default').trim(),
      base_url: (form?.base_url ?? p.base_url ?? '').trim(),
      enabled: form?.enabled ?? p.enabled,
      ...(form?.api_key ? { api_key: form.api_key.trim() } : {}),
    };
  };

  const handleTestConnection = async (p: ProviderConfig) => {
    setTestingId(p.id);
    setActionError((prev) => ({ ...prev, [p.id]: '' }));
    setActionSuccess((prev) => ({ ...prev, [p.id]: '' }));
    try {
      const result = await api.testProvider(p.id, formConfig(p));
      setTestResults((prev) => ({ ...prev, [p.id]: result }));
      if (result.ok) {
        setActionSuccess((prev) => ({ ...prev, [p.id]: `${result.message} Latência: ${result.latency_ms ?? '-'} ms.` }));
      } else {
        setActionError((prev) => ({ ...prev, [p.id]: result.message || 'Falha no teste de conexão.' }));
      }
    } catch (err: unknown) {
      setActionError((prev) => ({ ...prev, [p.id]: err instanceof Error ? err.message : 'Falha na requisição.' }));
    } finally {
      setTestingId(null);
    }
  };

  const handleSaveProvider = async (p: ProviderConfig) => {
    setSavingId(p.id);
    setActionError((prev) => ({ ...prev, [p.id]: '' }));
    setActionSuccess((prev) => ({ ...prev, [p.id]: '' }));
    try {
      const form = providerForms[p.id];
      await api.updateProvider(p.id, {
        id: p.id,
        name: p.name,
        kind: p.kind,
        model: form.model,
        base_url: form.base_url,
        enabled: form.enabled,
        has_key: p.has_key,
        api_key: form.api_key ? form.api_key : undefined,
      });
      setActionSuccess((prev) => ({
        ...prev,
        [p.id]: p.kind === 'omp' ? 'Configuração salva. As credenciais ficam no OMP.' : 'Configurações salvas no Secret Service local.',
      }));
      await onRefresh();
    } catch (err: unknown) {
      setActionError((prev) => ({ ...prev, [p.id]: err instanceof Error ? err.message : 'Falha ao salvar.' }));
    } finally {
      setSavingId(null);
    }
  };

  const handleFetchModels = async (p: ProviderConfig) => {
    setLoadingModelsId(p.id);
    try {
      const config = formConfig(p);
      const res = await api.getProviderModels(p.id, config.model ? config : undefined);
      setDiscoveredModels((prev) => ({ ...prev, [p.id]: res.discovered || [] }));
      if (res.error && res.source !== 'unauthenticated') {
        setActionError((prev) => ({ ...prev, [p.id]: `Lista dinâmica indisponível: ${res.error}` }));
      }
    } catch (err: unknown) {
      setActionError((prev) => ({ ...prev, [p.id]: 'Não foi possível listar modelos dinâmicos do provedor.' }));
    } finally {
      setLoadingModelsId(null);
    }
  };

  const handleOmpLogin = async (loginProvider: string) => {
    setOmpError(null);
    setOmpLoginStarting(loginProvider);
    try {
      const login = await api.startOmpLogin(loginProvider, googleCloudProject);
      setOmpStatus((prev) => (prev ? { ...prev, login } : prev));
    } catch (err: unknown) {
      setOmpError(err instanceof Error ? err.message : 'Falha ao iniciar o login.');
    } finally {
      setOmpLoginStarting(null);
    }
  };

  // Credencial pronta: chave no keyring, ou conta logada no OMP para o provedor `omp`.
  const hasCredential = (p: ProviderConfig) =>
    p.kind === 'omp' ? ompLoggedIn : Boolean(p.has_key || providerForms[p.id]?.api_key);

  const handleOrderChange = async (type: 'primary' | 'fallback', value: string | null) => {
    setOrderError(null);
    setOrderSuccess(null);
    const newPrimary = type === 'primary' ? value : providerOrder.primary;
    const newFallback = type === 'fallback' ? value : providerOrder.fallback;

    if (newPrimary && newFallback && newPrimary === newFallback) {
      setOrderError('O provedor primário e o fallback não podem ser o mesmo provedor.');
      return;
    }

    const newOrder: ProviderOrder = {
      primary: newPrimary,
      fallback: newFallback,
    };
    try {
      await api.updateProviderOrder(newOrder);
      setOrderSuccess('Ordem de prioridade salva com sucesso.');
      setTimeout(() => setOrderSuccess(null), 3000);
      await onRefresh();
    } catch (err: unknown) {
      setOrderError(err instanceof Error ? err.message : 'Falha ao atualizar a ordem de provedores.');
    }
  };

  return (
    <div style={{ maxWidth: '1040px', margin: '0 auto' }}>
      {/* CABEÇALHO */}
      <div style={{ marginBottom: '28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <Badge variant="indigo" icon={<Bot size={12} />}>
            CENTRAL DE INTELIGÊNCIA ARTIFICIAL
          </Badge>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Modelos de Análise & Virality Ranking
          </span>
        </div>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
          Provedores de IA & Modelos
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Configure suas chaves para análise semântica avançada. Suas credenciais são guardadas de forma segura no Secret Service do Fedora Linux e nunca expostas em arquivos públicos.
        </p>
      </div>

      {/* ORDEM DE PRIORIDADE: PROVEDOR PRINCIPAL E FALLBACK */}
      <div
        className="card"
        style={{
          marginBottom: '28px',
          background: 'linear-gradient(135deg, rgba(19, 23, 40, 0.9) 0%, rgba(14, 17, 29, 0.9) 100%)',
          border: '1px solid var(--border-default)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
          <Zap size={18} color="var(--primary)" />
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Ordem de Execução do Pipeline
          </h2>
        </div>

        {orderSuccess && (
          <div
            style={{
              padding: '8px 12px',
              backgroundColor: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              borderRadius: 'var(--radius-sm)',
              color: '#6ee7b7',
              fontSize: '0.82rem',
              marginBottom: '14px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <CheckCircle2 size={15} />
            <span>{orderSuccess}</span>
          </div>
        )}

        {orderError && (
          <div
            style={{
              padding: '8px 12px',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 'var(--radius-sm)',
              color: '#fca5a5',
              fontSize: '0.82rem',
              marginBottom: '14px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <AlertTriangle size={15} />
            <span>{orderError}</span>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
          {/* Provedor Primário */}
          <div>
            <label className="form-label">
              Provedor Primário (1ª Escolha)
              <span className="form-hint">Executado primeiro</span>
            </label>
            <select
              className="form-select"
              aria-label="Provedor primário de inteligência artificial"
              value={providerOrder.primary || ''}
              onChange={(e) => handleOrderChange('primary', e.target.value || null)}
            >
              <option value="">Nenhum (Usar modo local determinístico)</option>
              {allProviders.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} {hasCredential(p) ? '✓ (Credencial pronta)' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Provedor Fallback */}
          <div>
            <label className="form-label">
              Provedor Fallback (Contingência)
              <span className="form-hint">Acionado em caso de erro/rate-limit</span>
            </label>
            <select
              className="form-select"
              aria-label="Provedor fallback de inteligência artificial"
              value={providerOrder.fallback || ''}
              onChange={(e) => handleOrderChange('fallback', e.target.value || null)}
            >
              <option value="">Nenhum</option>
              {allProviders.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} {hasCredential(p) ? '✓' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* CARDS DE CADA PROVEDOR */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {allProviders.map((p) => {
          const form = providerForms[p.id] || { model: p.model || '', base_url: p.base_url || '', api_key: '', enabled: p.enabled };
          const isTesting = testingId === p.id;
          const isSaving = savingId === p.id;
          const testRes = testResults[p.id];
          const hasKeySaved = Boolean(p.has_key);
          const credentialReady = hasCredential(p);
          const isOmp = p.kind === 'omp';
          const curatedForKind = catalog[p.kind] || [];
          const discovered = discoveredModels[p.id] || [];

          return (
            <div
              key={p.id}
              className="card"
              style={{
                border: form.enabled ? '1px solid rgba(99, 102, 241, 0.35)' : '1px solid var(--border-subtle)',
                backgroundColor: 'var(--bg-card)',
                transition: 'border-color 0.2s',
              }}
            >
              {/* TOPO DO CARD: LOGO OFICIAL, NOME E TOGGLE */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '12px',
                  marginBottom: '16px',
                  paddingBottom: '14px',
                  borderBottom: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div
                    style={{
                      width: '40px',
                      height: '40px',
                      borderRadius: 'var(--radius-md)',
                      backgroundColor: 'var(--bg-surface)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      border: '1px solid var(--border-default)',
                    }}
                  >
                    <ProviderLogo kind={p.kind} size={22} />
                  </div>

                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {p.name}
                      </h3>
                      {credentialReady ? (
                        <Badge variant="emerald" icon={<ShieldCheck size={11} />}>
                          {isOmp ? 'Conta Conectada' : 'Credencial Salva'}
                        </Badge>
                      ) : (
                        <Badge variant="muted">{isOmp ? 'Sem login' : 'Sem chave'}</Badge>
                      )}
                    </div>
                    <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      ID interno: <span className="font-mono">{p.id}</span>
                    </span>
                  </div>
                </div>

                {/* Habilitar / Desabilitar Toggle */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <label
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      cursor: 'pointer',
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      color: form.enabled ? 'var(--text-primary)' : 'var(--text-muted)',
                    }}
                  >
                    <span>{form.enabled ? 'Habilitado' : 'Desabilitado'}</span>
                    <input
                      type="checkbox"
                      checked={form.enabled}
                      onChange={(e) => handleFieldChange(p.id, 'enabled', e.target.checked)}
                      style={{ width: '18px', height: '18px', accentColor: 'var(--primary)', cursor: 'pointer' }}
                    />
                  </label>
                </div>
              </div>

              {/* DESCRIÇÃO DO PROVEDOR */}
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '14px', marginTop: '-6px', lineHeight: 1.4 }}>
                {DEFAULT_PRESETS.find((pr) => pr.id === p.id)?.desc || ''}
              </p>

              {/* MENSAGENS DE SUCESSO / ERRO */}
              {actionSuccess[p.id] && (
                <div
                  style={{
                    padding: '8px 12px',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    borderRadius: 'var(--radius-sm)',
                    color: '#6ee7b7',
                    fontSize: '0.82rem',
                    marginBottom: '14px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <CheckCircle2 size={15} />
                  <span>{actionSuccess[p.id]}</span>
                </div>
              )}

              {actionError[p.id] && (
                <div
                  style={{
                    padding: '8px 12px',
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    borderRadius: 'var(--radius-sm)',
                    color: '#fca5a5',
                    fontSize: '0.82rem',
                    marginBottom: '14px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <AlertTriangle size={15} />
                  <span>{actionError[p.id]}</span>
                </div>
              )}

              {/* LOGIN NO NAVEGADOR VIA OMP (ITEM 2) */}
              {isOmp && (
                <div
                  style={{
                    marginBottom: '18px',
                    padding: '16px',
                    borderRadius: 'var(--radius-md)',
                    backgroundColor: 'rgba(59, 130, 246, 0.08)',
                    border: '1px solid rgba(59, 130, 246, 0.25)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                    <Globe size={18} color="var(--ai-indigo)" aria-hidden="true" />
                    <div>
                      <div style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                        Entrar com sua conta no navegador via OMP
                      </div>
                      <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                        O OMP gerencia a autenticação local com segurança. A disponibilidade dos modelos depende das permissões e cotas do seu plano em cada provedor.
                      </div>
                    </div>
                  </div>

                  {/* CAMPO DE PROJETO GOOGLE CLOUD (PARA RESOLVER ERRO 1 NO GEMINI) */}
                  <div
                    style={{
                      marginBottom: '14px',
                      padding: '12px 14px',
                      backgroundColor: 'var(--bg-card)',
                      borderRadius: 'var(--radius-sm)',
                      border: '1px solid var(--border-default)',
                    }}
                  >
                    <label className="form-label" style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: '4px' }}>
                      ID do Projeto Google Cloud (GOOGLE_CLOUD_PROJECT)
                      <span className="form-hint" style={{ fontSize: '0.72rem' }}>
                        Obrigatório para contas Google corporativas / Gemini CLI
                      </span>
                    </label>
                    <input
                      type="text"
                      className="form-input font-mono"
                      placeholder="Ex: meu-projeto-gcp-12345"
                      value={googleCloudProject}
                      onChange={(e) => setGoogleCloudProject(e.target.value)}
                      style={{ fontSize: '0.82rem', height: '36px', minHeight: '36px' }}
                    />
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                      Preencha antes de clicar em "Entrar com conta" no Google Gemini caso sua conta exija projeto corporativo no GCP.
                    </div>
                  </div>

                  {ompError && (
                    <div role="alert" style={{ fontSize: '0.8rem', color: '#fca5a5', marginBottom: '10px' }}>
                      {ompError}
                    </div>
                  )}

                  {!ompStatus ? (
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Consultando o OMP...</div>
                  ) : !ompStatus.installed ? (
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      OMP não encontrado neste computador. Instale em{' '}
                      <a href="https://omp.sh" target="_blank" rel="noopener noreferrer">omp.sh</a> e recarregue esta página.
                    </div>
                  ) : (
                    <>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {ompStatus.providers.map((acc) => {
                          const waiting = ompStatus.login?.running && ompStatus.login.provider === acc.id;
                          return (
                            <div
                              key={acc.id}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                padding: '10px 14px',
                                backgroundColor: 'var(--bg-surface)',
                                borderRadius: 'var(--radius-sm)',
                                border: '1px solid var(--border-subtle)',
                                gap: '12px',
                                flexWrap: 'wrap',
                              }}
                            >
                              <div>
                                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                                  {acc.name}
                                </div>
                                <div className="font-mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                  {acc.id}
                                </div>
                              </div>

                              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                {acc.logged_in ? (
                                  <Badge variant="emerald" icon={<ShieldCheck size={11} />}>Conectado</Badge>
                                ) : (
                                  <Badge variant="muted">Desconectado</Badge>
                                )}
                                <Button
                                  type="button"
                                  variant="secondary"
                                  size="sm"
                                  loading={ompLoginStarting === acc.id || Boolean(waiting)}
                                  disabled={ompLoginRunning && !waiting}
                                  onClick={() => handleOmpLogin(acc.id)}
                                >
                                  {waiting ? 'Aguardando navegador...' : acc.logged_in ? 'Entrar novamente' : 'Entrar com conta'}
                                </Button>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {ompStatus.login?.running && (
                        <div role="status" style={{ marginTop: '12px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          Conclua o login na aba aberta do navegador.
                          {ompStatus.login.auth_url && (
                            <>
                              {' '}Se nenhuma aba abriu,{' '}
                              <a href={ompStatus.login.auth_url} target="_blank" rel="noopener noreferrer">
                                abra a página de login <ExternalLink size={11} aria-hidden="true" />
                              </a>.
                            </>
                          )}
                        </div>
                      )}

                      {ompStatus.login && !ompStatus.login.running && ompStatus.login.exit_code !== 0 && (
                        <div
                          role="alert"
                          style={{
                            marginTop: '12px',
                            padding: '10px 14px',
                            borderRadius: 'var(--radius-sm)',
                            backgroundColor: 'rgba(239, 68, 68, 0.12)',
                            border: '1px solid rgba(239, 68, 68, 0.35)',
                            color: '#fca5a5',
                            fontSize: '0.82rem',
                            lineHeight: 1.4,
                          }}
                        >
                          <div style={{ fontWeight: 700, marginBottom: '2px' }}>
                            O login em {ompStatus.login.provider} não foi concluído (código {ompStatus.login.exit_code}):
                          </div>
                          <div>{ompStatus.login.error || 'Erro desconhecido durante autenticação.'}</div>
                          {ompStatus.login.error && (ompStatus.login.error.includes('GOOGLE_CLOUD_PROJECT') || ompStatus.login.error.includes('project')) && (
                            <div style={{ marginTop: '6px', color: '#fed7aa', fontWeight: 500 }}>
                              💡 Dica: Preencha o campo <strong>ID do Projeto Google Cloud</strong> acima com seu ID de projeto do GCP e clique em "Entrar com conta" novamente.
                            </div>
                          )}
                        </div>
                      )}

                      <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'flex-end' }}>
                        <Button type="button" variant="ghost" size="sm" icon={<RefreshCw size={13} />} onClick={refreshOmpStatus}>
                          Atualizar status
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* CAMPOS DO FORMULÁRIO */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isOmp ? '1fr' : 'repeat(auto-fit, minmax(280px, 1fr))',
                  gap: '16px',
                  marginBottom: '16px',
                }}
              >
                {/* Modelo de Linguagem com Lista Selecionável Dinâmica (Item 1) */}
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                    <label className="form-label" style={{ margin: 0, fontWeight: 600 }}>
                      Modelo de Linguagem
                    </label>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <button
                        type="button"
                        onClick={() => handleFetchModels(p)}
                        disabled={loadingModelsId === p.id}
                        className="btn btn-ghost btn-sm"
                        style={{ padding: '2px 6px', fontSize: '0.72rem', color: 'var(--ai-indigo)', minHeight: 'auto', display: 'flex', alignItems: 'center', gap: '4px' }}
                        title="Consultar modelos disponíveis na API"
                      >
                        {loadingModelsId === p.id ? (
                          <>
                            <Loader2 className="animate-spin" size={11} />
                            <span>Buscando...</span>
                          </>
                        ) : (
                          <>
                            <RefreshCw size={11} />
                            <span>Buscar Modelos</span>
                          </>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => setCustomModelMode((prev) => ({ ...prev, [p.id]: !prev[p.id] }))}
                        className="btn btn-ghost btn-sm"
                        style={{ padding: '2px 6px', fontSize: '0.72rem', color: 'var(--text-muted)', minHeight: 'auto' }}
                        title="Alternar entre lista e digitação manual"
                      >
                        {customModelMode[p.id] ? 'Ver Lista' : 'Digitar Manual'}
                      </button>
                    </div>
                  </div>

                  {customModelMode[p.id] ? (
                    <input
                      type="text"
                      className="form-input font-mono"
                      placeholder={isOmp ? 'Ex: google-antigravity/gemini-3.8-flash' : 'Ex: gpt-6-luna ou glm-4.7'}
                      value={form.model}
                      onChange={(e) => handleFieldChange(p.id, 'model', e.target.value)}
                    />
                  ) : (
                    <select
                      className="form-select font-mono"
                      value={form.model}
                      aria-label={`Selecionar modelo de inteligência artificial para ${p.name}`}
                      onChange={(e) => {
                        if (e.target.value === '__custom__') {
                          setCustomModelMode((prev) => ({ ...prev, [p.id]: true }));
                        } else {
                          handleFieldChange(p.id, 'model', e.target.value);
                        }
                      }}
                      style={{ width: '100%', cursor: 'pointer' }}
                    >
                      {curatedForKind.length > 0 && (
                        <optgroup label="Modelos Oficiais / Recomendados">
                          {curatedForKind.map((cm) => (
                            <option key={cm.id} value={cm.id}>
                              {cm.name || cm.id} ({cm.id}){cm.badge ? ` — ${cm.badge}` : ''}
                            </option>
                          ))}
                        </optgroup>
                      )}

                      {discovered.length > 0 && (
                        <optgroup label={isOmp ? 'Modelos Disponíveis no OMP' : 'Modelos Detectados na API / Runtime'}>
                          {discovered
                            .filter((dm) => !curatedForKind.some((cm) => cm.id === dm.id))
                            .map((dm) => (
                              <option key={dm.id} value={dm.id}>
                                {dm.name || dm.id} ({dm.id}){dm.description ? ` — ${dm.description}` : ''}
                              </option>
                            ))}
                        </optgroup>
                      )}

                      {/* Mantém visível o modelo salvo mesmo quando não está nas listas (evita o select exibir outro valor). */}
                      {form.model &&
                        !curatedForKind.some((cm) => cm.id === form.model) &&
                        !discovered.some((dm) => dm.id === form.model) && (
                          <option value={form.model}>{form.model} (atual)</option>
                        )}

                      <option value="__custom__">Digitar outro modelo manualmente...</option>
                    </select>
                  )}

                  {/* Resumo ou descrição do modelo selecionado */}
                  {(() => {
                    const matchedCurated = curatedForKind.find((cm) => cm.id === form.model);
                    const matchedDiscovered = discovered.find((dm) => dm.id === form.model);
                    const desc = matchedCurated?.description || matchedDiscovered?.description;
                    if (desc) {
                      return (
                        <div style={{ marginTop: '5px', fontSize: '0.73rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Info size={12} style={{ flexShrink: 0 }} />
                          <span>{desc}</span>
                        </div>
                      );
                    }
                    return null;
                  })()}
                </div>

                {!isOmp && (
                  <>
                    {/* Chave de API */}
                    <div>
                      <label className="form-label" htmlFor={`api-key-${p.id}`}>
                        Chave de API (Secret Key)
                        {hasKeySaved && <span style={{ fontSize: '0.72rem', color: 'var(--emerald)' }}>● Salva no Keyring</span>}
                      </label>
                      <div style={{ position: 'relative' }}>
                        <input
                          id={`api-key-${p.id}`}
                          type={showKeys[p.id] ? 'text' : 'password'}
                          className="form-input font-mono"
                          placeholder={hasKeySaved ? '••••••••••••••••••••••••' : 'Insira a chave secreta...'}
                          value={form.api_key}
                          onChange={(e) => handleFieldChange(p.id, 'api_key', e.target.value)}
                          style={{ paddingRight: '40px' }}
                          autoComplete="off"
                        />
                        <button
                          type="button"
                          onClick={() => setShowKeys((prev) => ({ ...prev, [p.id]: !prev[p.id] }))}
                          style={{
                            position: 'absolute',
                            right: '10px',
                            top: '50%',
                            transform: 'translateY(-50%)',
                            background: 'transparent',
                            border: 'none',
                            color: 'var(--text-muted)',
                            cursor: 'pointer',
                          }}
                          aria-label="Alternar visibilidade da chave"
                        >
                          {showKeys[p.id] ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    </div>

                    {/* Base URL (opcional ou para servidores locais) */}
                    <div>
                      <label className="form-label" htmlFor={`base-url-${p.id}`}>
                        Base URL (Endpoint API)
                        <span className="form-hint">Opcional para oficiais</span>
                      </label>
                      <input
                        id={`base-url-${p.id}`}
                        type="text"
                        className="form-input font-mono"
                        placeholder="https://api... ou http://localhost:11434/v1"
                        value={form.base_url}
                        onChange={(e) => handleFieldChange(p.id, 'base_url', e.target.value)}
                      />
                    </div>
                  </>
                )}
              </div>

              {/* BARRA DE AÇÕES DO CARD */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={isTesting ? <Loader2 className="animate-spin" size={14} /> : <Zap size={14} />}
                  loading={isTesting}
                  onClick={() => handleTestConnection(p)}
                >
                  Testar Conexão
                </Button>

                <Button
                  variant="primary"
                  size="sm"
                  loading={isSaving}
                  onClick={() => handleSaveProvider(p)}
                >
                  Salvar Configuração
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
