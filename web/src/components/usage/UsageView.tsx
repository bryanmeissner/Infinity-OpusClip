import React, { useEffect, useState } from 'react';
import { Activity, Clock, AlertTriangle, Database, Cpu, Zap, CheckCircle2 } from 'lucide-react';
import type { Project, UsageRecord } from '../../types';
import { api } from '../../api/client';
import { Badge } from '../common/Badge';
import { EmptyState } from '../common/EmptyState';
import { ProviderLogo } from '../common/ProviderLogo';

export interface UsageViewProps {
  project: Project;
}

export const UsageView: React.FC<UsageViewProps> = ({ project }) => {
  const [usageRecords, setUsageRecords] = useState<UsageRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadUsage() {
      setIsLoading(true);
      setError(null);
      try {
        const records = await api.getProjectUsage(project.id);
        if (isMounted) {
          setUsageRecords(records || []);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Falha ao obter métricas de uso de IA.');
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    loadUsage();

    return () => {
      isMounted = false;
    };
  }, [project.id]);

  const totalCalls = usageRecords.reduce((acc, r) => acc + (r.calls || 1), 0);
  const totalTokens = usageRecords.reduce((acc, r) => acc + (r.tokens || 0), 0);
  const totalDuration = usageRecords.reduce((acc, r) => acc + (r.duration || 0), 0);
  const errorCount = usageRecords.filter((r) => Boolean(r.error)).length;

  return (
    <div style={{ maxWidth: '1040px', margin: '0 auto' }}>
      {/* Topo do Módulo */}
      <div style={{ marginBottom: '28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
          <Badge variant="indigo" icon={<Activity size={12} />}>
            TELEMETRIA & CONSUMO
          </Badge>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Projeto: <strong>{project.display_name || project.name}</strong>
          </span>
        </div>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
          Métricas de Uso de Inteligência Artificial
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Monitore o volume de chamadas, contagem de tokens e tempo de resposta de cada requisição semântica.
        </p>
      </div>

      {error && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-md)',
            color: '#fca5a5',
            fontSize: '0.88rem',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <AlertTriangle size={18} color="var(--danger)" />
          <span>{error}</span>
        </div>
      )}

      {/* Cards de Resumo (KPIs) */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: '16px',
          marginBottom: '28px',
        }}
      >
        <div className="card" style={{ padding: '18px 20px', backgroundColor: 'var(--bg-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <Zap size={16} color="var(--primary)" />
            <span style={{ fontSize: '0.78rem', fontWeight: 600, textTransform: 'uppercase' }}>Chamadas de IA</span>
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            {totalCalls}
          </div>
        </div>

        <div className="card" style={{ padding: '18px 20px', backgroundColor: 'var(--bg-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <Database size={16} color="var(--ai-indigo)" />
            <span style={{ fontSize: '0.78rem', fontWeight: 600, textTransform: 'uppercase' }}>Tokens Processados</span>
          </div>
          <div className="font-mono" style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            {totalTokens.toLocaleString('pt-BR')}
          </div>
        </div>

        <div className="card" style={{ padding: '18px 20px', backgroundColor: 'var(--bg-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <Clock size={16} color="var(--emerald)" />
            <span style={{ fontSize: '0.78rem', fontWeight: 600, textTransform: 'uppercase' }}>Latência Total</span>
          </div>
          <div className="font-mono" style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            {totalDuration > 0 ? `${totalDuration.toFixed(1)}s` : '—'}
          </div>
        </div>

        <div className="card" style={{ padding: '18px 20px', backgroundColor: 'var(--bg-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', marginBottom: '8px' }}>
            <AlertTriangle size={16} color={errorCount > 0 ? 'var(--danger)' : 'var(--emerald)'} />
            <span style={{ fontSize: '0.78rem', fontWeight: 600, textTransform: 'uppercase' }}>Taxa de Falhas</span>
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 800, color: errorCount > 0 ? 'var(--danger)' : 'var(--emerald)' }}>
            {errorCount === 0 ? '0 falhas' : `${errorCount} falhas`}
          </div>
        </div>
      </div>

      {/* Tabela de Histórico de Chamadas */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary)' }}>
          <p>Carregando registros de telemetria...</p>
        </div>
      ) : usageRecords.length === 0 ? (
        <EmptyState
          icon={<Cpu size={32} />}
          title="Nenhum registro de IA ainda"
          description={`Nenhuma chamada de modelo foi registrada para o projeto "${project.display_name || project.name}". Quando você executar uma análise de corte com OpenAI, Claude ou Gemini, as métricas detalhadas aparecerão aqui.`}
        />
      ) : (
        <div className="card" style={{ padding: '20px', overflowX: 'auto' }}>
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '16px' }}>
            Registro Detalhado de Execuções
          </h2>

          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-default)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '10px 12px' }}>Provedor & Modelo</th>
                <th style={{ padding: '10px 12px' }}>Chamadas</th>
                <th style={{ padding: '10px 12px' }}>Tokens</th>
                <th style={{ padding: '10px 12px' }}>Duração</th>
                <th style={{ padding: '10px 12px' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {usageRecords.map((r, i) => (
                <tr
                  key={i}
                  style={{
                    borderBottom: '1px solid var(--border-subtle)',
                    transition: 'background-color 0.15s',
                  }}
                >
                  <td style={{ padding: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <ProviderLogo kind={r.provider} size={18} />
                    <div>
                      <strong style={{ color: 'var(--text-primary)' }}>{r.provider}</strong>
                      <div className="font-mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {r.model}
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '12px' }}>{r.calls || 1}</td>
                  <td className="font-mono" style={{ padding: '12px' }}>
                    {r.tokens ? r.tokens.toLocaleString('pt-BR') : '—'}
                  </td>
                  <td className="font-mono" style={{ padding: '12px' }}>
                    {r.duration ? `${r.duration.toFixed(2)}s` : '—'}
                  </td>
                  <td style={{ padding: '12px' }}>
                    {r.error ? (
                      <Badge variant="rose" icon={<AlertTriangle size={11} />}>
                        Erro
                      </Badge>
                    ) : (
                      <Badge variant="emerald" icon={<CheckCircle2 size={11} />}>
                        Sucesso
                      </Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
