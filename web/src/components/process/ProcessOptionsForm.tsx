import React, { useRef, useState } from 'react';
import {
  Sparkles,
  Clock,
  Layout,
  Smartphone,
  RotateCcw,
  Check,
  Layers,
  Type,
} from 'lucide-react';
import type {
  ClipDuration,
  ClipFormat,
  ClipModel,
  ClipPlatform,
  ContentGenre,
  Options,
  Project,
  SubtitlePosition,
  SubtitleStyle,
} from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';

export interface ProcessOptionsFormProps {
  project: Project;
  onSubmit: (options: Options) => Promise<void>;
  isLoading: boolean;
}

const GENRES: ContentGenre[] = [
  'Auto',
  'Podcast',
  'Lifestyle',
  'Vlog',
  'Viagem',
  'Comida',
  'Beleza',
  'Fitness',
  'Esportes',
  'Futebol',
  'Basquete',
  'Marketing',
  'Talking Head',
  'Discurso',
  'Comentário',
  'Entrevista',
  'Entretenimento',
  'Filmes',
  'Reality',
  'Notícias',
  'Educacional',
  'Produtos',
  'História',
  'Ciência e tecnologia',
  'Música',
  'Games',
  'Outros',
];

const DURATION_PRESETS: Array<{ id: ClipDuration; label: string; desc: string }> = [
  { id: 'Auto', label: 'Auto (IA)', desc: 'Detecta a duração ideal' },
  { id: '<30s', label: '< 30s', desc: 'Ultra-rápido & viral' },
  { id: '30s–59s', label: '30s – 59s', desc: 'Padrão Shorts & Reels' },
  { id: '60s–89s', label: '60s – 89s', desc: 'Storytelling envolvente' },
  { id: '90s–3min', label: '90s – 3min', desc: 'Aprofundamento' },
  { id: 'personalizada', label: 'Personalizada', desc: 'Defina intervalo exato' },
];

const PLATFORMS: Array<{ id: ClipPlatform; name: string; defaultRatio: ClipFormat }> = [
  { id: 'TikTok', name: 'TikTok', defaultRatio: '9:16' },
  { id: 'YouTube Shorts', name: 'YouTube Shorts', defaultRatio: '9:16' },
  { id: 'Instagram Reels', name: 'Instagram Reels', defaultRatio: '9:16' },
];

const FORMATS: Array<{ id: ClipFormat; label: string; ratio: string; desc: string }> = [
  { id: '9:16', label: '9:16 Vertical', ratio: '9:16', desc: 'Reels, Shorts e TikTok' },
  { id: '1:1', label: '1:1 Quadrado', ratio: '1:1', desc: 'Feed do Instagram / LinkedIn' },
  { id: '16:9', label: '16:9 Paisagem', ratio: '16:9', desc: 'YouTube clássico e TV' },
];

const PROMPT_SUGGESTIONS = [
  'Destaque os momentos mais hilários e reações espontâneas',
  'Encontre os ganchos mais impactantes e surpresas',
  'Pegue as melhores explicações e conclusões importantes',
  'Encontre partes onde falaram sobre tecnologia e inovação',
  'Destaque momentos com forte debate emocional',
];

export const ProcessOptionsForm: React.FC<ProcessOptionsFormProps> = ({
  project,
  onSubmit,
  isLoading,
}) => {
  const sourceDuration = project.metadata?.duration ?? 0;
  const videoDuration = Number.isFinite(sourceDuration) && sourceDuration > 0 ? sourceDuration : 0;
  const minimumInterval = Math.min(1, videoDuration > 0 ? videoDuration : 1);
  const hasActiveJob = (project.jobs || []).some((j) => j.state === 'queued' || j.state === 'running');
  const isButtonDisabled = isLoading || hasActiveJob || videoDuration === 0;

  // Estados dos formulários com valores padrão pré-carregados
  const [clipModel, setClipModel] = useState<ClipModel>(project.options?.clip_model || 'Auto');
  const [genre, setGenre] = useState<ContentGenre | string>(project.options?.genre || 'Auto');
  const [durations, setDurations] = useState<ClipDuration[]>(() => {
    if (project.options?.durations && Array.isArray(project.options.durations) && project.options.durations.length > 0) {
      return project.options.durations as ClipDuration[];
    }
    if (project.options?.duration) {
      return [project.options.duration];
    }
    return ['Auto'];
  });

  const toggleDuration = (id: ClipDuration) => {
    if (id === 'Auto') {
      setDurations(['Auto']);
      return;
    }
    setDurations((prev) => {
      const withoutAuto = prev.filter((d) => d !== 'Auto');
      if (withoutAuto.includes(id)) {
        const remaining = withoutAuto.filter((d) => d !== id);
        return remaining.length > 0 ? remaining : ['Auto'];
      } else {
        return [...withoutAuto, id];
      }
    });
  };
  const [customMin, setCustomMin] = useState<number>(project.options?.custom_min || 15);
  const [customMax, setCustomMax] = useState<number>(project.options?.custom_max || 60);

  // Intervalo do Vídeo
  const [intervalStart, setIntervalStart] = useState<number>(project.options?.start ?? 0);
  const [intervalEnd, setIntervalEnd] = useState<number | null>(project.options?.end ?? null);

  const selectedStart = Math.max(
    0,
    Math.min(Number.isFinite(intervalStart) ? intervalStart : 0, videoDuration - minimumInterval)
  );
  const selectedEnd = Math.max(
    selectedStart + minimumInterval,
    Math.min(intervalEnd !== null && Number.isFinite(intervalEnd) ? intervalEnd : videoDuration, videoDuration)
  );
  const useWholeVideo = selectedStart === 0 && selectedEnd === videoDuration;
  const startPercent = videoDuration > 0 ? (selectedStart / videoDuration) * 100 : 0;
  const endPercent = videoDuration > 0 ? (selectedEnd / videoDuration) * 100 : 100;

  // Configurações de Saída e IA
  const [platform, setPlatform] = useState<ClipPlatform>(project.options?.platform || 'TikTok');
  const [format, setFormat] = useState<ClipFormat>(project.options?.format || '9:16');
  const [prompt, setPrompt] = useState<string>(project.options?.request || '');
  const reframe = true;
  const subtitles = true;
  const [subtitleStyle, setSubtitleStyle] = useState<SubtitleStyle>(project.options?.subtitle_style || 'highlight');
  const [subtitleSize, setSubtitleSize] = useState<number>(project.options?.subtitle_size || 48);
  const [subtitlePosition, setSubtitlePosition] = useState<SubtitlePosition>(
    project.options?.subtitle_position || 'bottom'
  );
  const [allowExternalMultimodal, setAllowExternalMultimodal] = useState<boolean>(
    project.options?.allow_images ?? false
  );

  const formatTimecode = (seconds: number) => {
    const milliseconds = Math.max(0, Math.round(seconds * 1000));
    const total = Math.floor(milliseconds / 1000);
    const hrs = Math.floor(total / 3600);
    const mins = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const fraction = (milliseconds % 1000).toString().padStart(3, '0');
    const time = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${fraction}`;
    return hrs > 0 || videoDuration >= 3600
      ? `${hrs.toString().padStart(2, '0')}:${time}`
      : time;
  };

  const trackRef = useRef<HTMLDivElement | null>(null);
  const [draggingHandle, setDraggingHandle] = useState<'start' | 'end' | null>(null);

  const clampStart = (val: number, currentEnd: number = selectedEnd) => {
    const maxAllowed = Math.max(0, currentEnd - minimumInterval);
    return Math.max(0, Math.min(Number(val.toFixed(1)), maxAllowed));
  };

  const clampEnd = (val: number, currentStart: number = selectedStart) => {
    const minAllowed = currentStart + minimumInterval;
    return Math.max(minAllowed, Math.min(Number(val.toFixed(1)), videoDuration));
  };

  const handleTrackPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (videoDuration <= 0 || !trackRef.current) return;
    const rect = trackRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const clickTime = ratio * videoDuration;

    const distToStart = Math.abs(clickTime - selectedStart);
    const distToEnd = Math.abs(clickTime - selectedEnd);

    if (distToStart <= distToEnd) {
      const newStart = clampStart(clickTime, selectedEnd);
      setIntervalStart(newStart);
    } else {
      const newEnd = clampEnd(clickTime, selectedStart);
      setIntervalEnd(newEnd);
    }
  };

  const handleStartPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDraggingHandle('start');
  };

  const handleStartPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (draggingHandle !== 'start' || !trackRef.current || videoDuration <= 0) return;
    const rect = trackRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const time = ratio * videoDuration;
    setIntervalStart(clampStart(time, selectedEnd));
  };

  const handleStartPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (draggingHandle === 'start') {
      try {
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {}
      setDraggingHandle(null);
    }
  };

  const handleEndPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDraggingHandle('end');
  };

  const handleEndPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (draggingHandle !== 'end' || !trackRef.current || videoDuration <= 0) return;
    const rect = trackRef.current.getBoundingClientRect();
    if (rect.width <= 0) return;
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const time = ratio * videoDuration;
    setIntervalEnd(clampEnd(time, selectedStart));
  };

  const handleEndPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (draggingHandle === 'end') {
      try {
        (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
      } catch {}
      setDraggingHandle(null);
    }
  };

  const handleStartKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (videoDuration <= 0) return;
    let step = 0;
    if (e.key === 'ArrowLeft') step = e.shiftKey ? -10 : -1;
    else if (e.key === 'ArrowRight') step = e.shiftKey ? 10 : 1;
    else if (e.key === 'PageDown') step = -10;
    else if (e.key === 'PageUp') step = 10;
    else if (e.key === 'Home') {
      e.preventDefault();
      setIntervalStart(0);
      return;
    } else if (e.key === 'End') {
      e.preventDefault();
      setIntervalStart(clampStart(selectedEnd - minimumInterval, selectedEnd));
      return;
    }

    if (step !== 0) {
      e.preventDefault();
      setIntervalStart(clampStart(selectedStart + step, selectedEnd));
    }
  };

  const handleEndKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (videoDuration <= 0) return;
    let step = 0;
    if (e.key === 'ArrowLeft') step = e.shiftKey ? -10 : -1;
    else if (e.key === 'ArrowRight') step = e.shiftKey ? 10 : 1;
    else if (e.key === 'PageDown') step = -10;
    else if (e.key === 'PageUp') step = 10;
    else if (e.key === 'Home') {
      e.preventDefault();
      setIntervalEnd(clampEnd(selectedStart + minimumInterval, selectedStart));
      return;
    } else if (e.key === 'End') {
      e.preventDefault();
      setIntervalEnd(videoDuration);
      return;
    }

    if (step !== 0) {
      e.preventDefault();
      setIntervalEnd(clampEnd(selectedEnd + step, selectedStart));
    }
  };

  const handleSetWholeVideo = () => {
    setIntervalStart(0);
    setIntervalEnd(videoDuration);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isButtonDisabled) return;
    const finalOptions: Options = {
      clip_model: clipModel,
      genre: genre as ContentGenre,
      duration: durations[0] || 'Auto',
      durations,
      custom_min: customMin,
      custom_max: customMax,
      platform,
      format,
      auto_title: project.options?.auto_title ?? true,
      reframe: true,
      subtitles: true,
      subtitle_style: subtitleStyle,
      subtitle_size: subtitleSize,
      subtitle_position: subtitlePosition,
      request: prompt.trim(),
      start: selectedStart,
      end: selectedEnd,
      results: null,
      allow_images: allowExternalMultimodal,
    };
    onSubmit(finalOptions);
  };

  return (
    <div style={{ maxWidth: '1040px', margin: '0 auto' }}>
      {/* Cabeçalho do Estúdio */}
      <div style={{ marginBottom: '28px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
          <Badge variant="indigo" icon={<Sparkles size={12} />}>
            ESTÚDIO DE IA
          </Badge>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            Vídeo selecionado: <strong>{project.display_name || project.name}</strong>
          </span>
        </div>
        <h1 style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
          Configurar Geração de Cortes Inteligentes
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.92rem' }}>
          Selecione a plataforma alvo, estilo de legenda e critérios para a IA encontrar e pontuar os melhores momentos.
        </p>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {/* SEÇÃO 1: INTERVALO DO VÍDEO (ITEM 3 - BARRA DE CORTE INTERATIVA) */}
        <div className="card" style={{ border: '1px solid rgba(99, 102, 241, 0.3)', backgroundColor: 'var(--bg-card)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Clock size={18} color="var(--primary)" aria-hidden="true" />
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                1. Intervalo do Vídeo (Trecho a Analisar)
              </h2>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="badge badge-indigo" style={{ fontSize: '0.78rem' }}>
                Tamanho total: {videoDuration > 0 ? formatTimecode(videoDuration) : '--:--'}
              </span>
              {videoDuration > 0 && !useWholeVideo && (
                <Button type="button" variant="ghost" size="sm" icon={<RotateCcw size={13} />} onClick={handleSetWholeVideo}>
                  Vídeo Inteiro
                </Button>
              )}
            </div>
          </div>

          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            Arraste os marcadores ou clique na barra para delimitar o intervalo. Pelo teclado, use as setas (1 s), Shift + seta (10 s) e Home/End. O limite é a duração real do vídeo ({videoDuration > 0 ? formatTimecode(videoDuration) : '--:--'}).
          </p>

          {videoDuration <= 0 ? (
            <div
              style={{
                padding: '20px',
                backgroundColor: 'var(--bg-surface)',
                borderRadius: 'var(--radius-lg)',
                border: '1px dashed var(--border-default)',
                textAlign: 'center',
                color: 'var(--text-muted)',
                fontSize: '0.9rem',
              }}
            >
              Duração do vídeo indisponível ou metadados ainda carregando. Aguarde o término do processamento de metadados.
            </div>
          ) : (
            <div
              style={{
                padding: '16px',
                backgroundColor: 'var(--bg-surface)',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              {/* Header com os timestamps e duração selecionada */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '18px',
                  flexWrap: 'wrap',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Início:</span>
                  <span className="font-mono badge badge-indigo" style={{ fontSize: '0.85rem', fontWeight: 700 }}>
                    {formatTimecode(selectedStart)}
                  </span>
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginLeft: '8px' }}>Fim:</span>
                  <span className="font-mono badge badge-indigo" style={{ fontSize: '0.85rem', fontWeight: 700 }}>
                    {formatTimecode(selectedEnd)}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Duração selecionada:</span>
                  <span className="font-mono" style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--primary)' }}>
                    {formatTimecode(selectedEnd - selectedStart)}
                  </span>
                  <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                    ({Math.round(((selectedEnd - selectedStart) / videoDuration) * 100)}% do vídeo)
                  </span>
                </div>
              </div>

              {/* Pista Única e Interativa (Track + Handles) */}
              <div
                style={{
                  position: 'relative',
                  padding: '14px 0',
                  userSelect: 'none',
                  touchAction: 'none',
                }}
              >
                {/* Trilho base clicável */}
                <div
                  ref={trackRef}
                  onPointerDown={handleTrackPointerDown}
                  style={{
                    position: 'relative',
                    height: '36px',
                    borderRadius: 'var(--radius-md)',
                    backgroundColor: '#0a0d18',
                    border: '1px solid var(--border-default)',
                    cursor: 'pointer',
                    overflow: 'visible',
                    boxShadow: 'inset 0 2px 4px rgba(0, 0, 0, 0.4)',
                  }}
                >
                  {/* Segmento inativo à esquerda */}
                  <div
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: `${startPercent}%`,
                      backgroundColor: 'rgba(0, 0, 0, 0.65)',
                      backgroundImage:
                        'repeating-linear-gradient(45deg, transparent, transparent 8px, rgba(255, 255, 255, 0.03) 8px, rgba(255, 255, 255, 0.03) 16px)',
                      borderTopLeftRadius: 'var(--radius-md)',
                      borderBottomLeftRadius: 'var(--radius-md)',
                      pointerEvents: 'none',
                      transition: draggingHandle ? 'none' : 'width 0.1s ease-out',
                    }}
                  />

                  {/* Segmento Selecionado Ativo */}
                  <div
                    style={{
                      position: 'absolute',
                      left: `${startPercent}%`,
                      width: `${Math.max(0, endPercent - startPercent)}%`,
                      top: 0,
                      bottom: 0,
                      background:
                        'linear-gradient(90deg, rgba(99, 102, 241, 0.45) 0%, rgba(244, 63, 94, 0.45) 100%)',
                      borderTop: '2px solid var(--ai-indigo)',
                      borderBottom: '2px solid var(--primary)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      pointerEvents: 'none',
                      overflow: 'hidden',
                      transition:
                        draggingHandle ? 'none' : 'left 0.1s ease-out, width 0.1s ease-out',
                    }}
                  >
                    <span
                      style={{
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        color: '#ffffff',
                        letterSpacing: '0.04em',
                        textShadow: '0 1px 3px rgba(0,0,0,0.9)',
                        whiteSpace: 'nowrap',
                        padding: '0 6px',
                        opacity: endPercent - startPercent > 12 ? 1 : 0,
                        transition: 'opacity 0.15s ease-out',
                      }}
                    >
                      TRECHO ATIVO ({formatTimecode(selectedEnd - selectedStart)})
                    </span>
                  </div>

                  {/* Segmento inativo à direita */}
                  <div
                    style={{
                      position: 'absolute',
                      left: `${endPercent}%`,
                      right: 0,
                      top: 0,
                      bottom: 0,
                      backgroundColor: 'rgba(0, 0, 0, 0.65)',
                      backgroundImage:
                        'repeating-linear-gradient(45deg, transparent, transparent 8px, rgba(255, 255, 255, 0.03) 8px, rgba(255, 255, 255, 0.03) 16px)',
                      borderTopRightRadius: 'var(--radius-md)',
                      borderBottomRightRadius: 'var(--radius-md)',
                      pointerEvents: 'none',
                      transition: draggingHandle ? 'none' : 'left 0.1s ease-out',
                    }}
                  />

                  {/* Handle Início */}
                  <div
                    className="interval-range-handle"
                    role="slider"
                    tabIndex={0}
                    aria-label="Início do intervalo"
                    aria-valuemin={0}
                    aria-valuemax={Math.max(0, selectedEnd - minimumInterval)}
                    aria-valuenow={selectedStart}
                    aria-valuetext={formatTimecode(selectedStart)}
                    onPointerDown={handleStartPointerDown}
                    onPointerMove={handleStartPointerMove}
                    onPointerUp={handleStartPointerUp}
                    onPointerCancel={handleStartPointerUp}
                    onLostPointerCapture={() => setDraggingHandle(null)}
                    onKeyDown={handleStartKeyDown}
                    style={{
                      position: 'absolute',
                      left: `${startPercent}%`,
                      top: '50%',
                      transform: 'translate(-50%, -50%)',
                      width: '28px',
                      height: '46px',
                      borderRadius: '5px',
                      backgroundColor: 'var(--ai-indigo)',
                      border: '2px solid #ffffff',
                      boxShadow:
                        draggingHandle === 'start'
                          ? '0 0 0 4px rgba(129, 140, 248, 0.4), 0 4px 10px rgba(0, 0, 0, 0.6)'
                          : '0 2px 8px rgba(0, 0, 0, 0.5)',
                      cursor: 'ew-resize',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      zIndex: draggingHandle === 'start' ? 10 : 5,
                      touchAction: 'none',
                      outline: 'none',
                      outlineOffset: '2px',
                      transition:
                        draggingHandle ? 'box-shadow 0.15s ease' : 'left 0.1s ease-out, box-shadow 0.15s ease',
                    }}
                  >
                    {/* Ícone de grip (3 barras verticais) */}
                    <div style={{ display: 'flex', gap: '2px', alignItems: 'center' }}>
                      <div style={{ width: '2px', height: '14px', backgroundColor: 'rgba(255, 255, 255, 0.85)', borderRadius: '1px' }} />
                      <div style={{ width: '2px', height: '14px', backgroundColor: 'rgba(255, 255, 255, 0.85)', borderRadius: '1px' }} />
                    </div>
                  </div>

                  {/* Handle Fim */}
                  <div
                    className="interval-range-handle"
                    role="slider"
                    tabIndex={0}
                    aria-label="Fim do intervalo"
                    aria-valuemin={selectedStart + minimumInterval}
                    aria-valuemax={videoDuration}
                    aria-valuenow={selectedEnd}
                    aria-valuetext={formatTimecode(selectedEnd)}
                    onPointerDown={handleEndPointerDown}
                    onPointerMove={handleEndPointerMove}
                    onPointerUp={handleEndPointerUp}
                    onPointerCancel={handleEndPointerUp}
                    onLostPointerCapture={() => setDraggingHandle(null)}
                    onKeyDown={handleEndKeyDown}
                    style={{
                      position: 'absolute',
                      left: `${endPercent}%`,
                      top: '50%',
                      transform: 'translate(-50%, -50%)',
                      width: '28px',
                      height: '46px',
                      borderRadius: '5px',
                      backgroundColor: 'var(--primary)',
                      border: '2px solid #ffffff',
                      boxShadow:
                        draggingHandle === 'end'
                          ? '0 0 0 4px rgba(244, 63, 94, 0.4), 0 4px 10px rgba(0, 0, 0, 0.6)'
                          : '0 2px 8px rgba(0, 0, 0, 0.5)',
                      cursor: 'ew-resize',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      zIndex: draggingHandle === 'end' ? 10 : 5,
                      touchAction: 'none',
                      outline: 'none',
                      outlineOffset: '2px',
                      transition:
                        draggingHandle ? 'box-shadow 0.15s ease' : 'left 0.1s ease-out, box-shadow 0.15s ease',
                    }}
                  >
                    {/* Ícone de grip (3 barras verticais) */}
                    <div style={{ display: 'flex', gap: '2px', alignItems: 'center' }}>
                      <div style={{ width: '2px', height: '14px', backgroundColor: 'rgba(255, 255, 255, 0.85)', borderRadius: '1px' }} />
                      <div style={{ width: '2px', height: '14px', backgroundColor: 'rgba(255, 255, 255, 0.85)', borderRadius: '1px' }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Legendas de limites da régua */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '0.74rem',
                  color: 'var(--text-muted)',
                  marginTop: '4px',
                }}
              >
                <span>00:00 (Início)</span>
                <span>{formatTimecode(videoDuration)} (Fim)</span>
              </div>
            </div>
          )}
        </div>

        {/* SEÇÃO 2: Plataforma & Proporção de Tela */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <Smartphone size={18} color="var(--primary)" aria-hidden="true" />
            <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              2. Plataforma Alvo & Formato
            </h2>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '14px', marginBottom: '20px' }}>
            {PLATFORMS.map((plat) => (
              <button
                key={plat.id}
                type="button"
                onClick={() => {
                  setPlatform(plat.id);
                  setFormat(plat.defaultRatio);
                }}
                className={`card card-interactive ${platform === plat.id ? 'active' : ''}`}
                style={{
                  padding: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  border: platform === plat.id ? '2px solid var(--primary)' : '1px solid var(--border-default)',
                  background: platform === plat.id ? 'rgba(244, 63, 94, 0.08)' : 'var(--bg-surface)',
                  textAlign: 'left',
                }}
              >
                <div>
                  <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
                    {plat.name}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                    Otimizado para algoritmo vertical
                  </div>
                </div>
                {platform === plat.id && (
                  <div
                    style={{
                      width: '24px',
                      height: '24px',
                      borderRadius: 'var(--radius-full)',
                      background: 'var(--primary)',
                      color: '#ffffff',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Check size={14} />
                  </div>
                )}
              </button>
            ))}
          </div>

          {/* Formato de Proporção (Aspect Ratio) */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
            {FORMATS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFormat(f.id)}
                className="btn"
                style={{
                  justifyContent: 'flex-start',
                  padding: '10px 14px',
                  border: format === f.id ? '2px solid var(--ai-indigo)' : '1px solid var(--border-subtle)',
                  background: format === f.id ? 'rgba(99, 102, 241, 0.12)' : 'var(--bg-input)',
                  color: format === f.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                }}
              >
                <Layout size={16} color={format === f.id ? 'var(--ai-indigo)' : 'var(--text-muted)'} />
                <div style={{ textAlign: 'left' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>{f.label}</div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{f.desc}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* SEÇÃO 3: Duração dos Cortes */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Clock size={18} color="var(--primary)" aria-hidden="true" />
              <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                3. Duração Desejada dos Cortes
              </h2>
            </div>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              Selecione uma ou mais opções (Auto é exclusivo)
            </span>
          </div>

          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            Você pode marcar várias durações para que a IA gere cortes em tamanhos variados. Se escolher <strong>Auto (IA)</strong>, a duração ideal será calculada dinamicamente para cada momento.
          </p>

          {/* Duração Presets (Multi-seleção com Auto-exclusivo) */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px', marginBottom: '20px' }}>
            {DURATION_PRESETS.map((p) => {
              const isSelected = durations.includes(p.id);
              return (
                <button
                  key={p.id}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => toggleDuration(p.id)}
                  className={`card card-interactive ${isSelected ? 'active' : ''}`}
                  style={{
                    padding: '12px 14px',
                    textAlign: 'left',
                    position: 'relative',
                    border: isSelected ? '2px solid var(--primary)' : '1px solid var(--border-default)',
                    background: isSelected ? 'rgba(244, 63, 94, 0.08)' : 'var(--bg-surface)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px' }}>
                    <div style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                      {p.label}
                    </div>
                    {isSelected && (
                      <div
                        style={{
                          width: '18px',
                          height: '18px',
                          borderRadius: 'var(--radius-full)',
                          background: 'var(--primary)',
                          color: '#ffffff',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                        }}
                      >
                        <Check size={12} aria-hidden="true" />
                      </div>
                    )}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                    {p.desc}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Seletor Customizado de Min/Max se personalizado */}
          {durations.includes('personalizada') && (
            <div
              style={{
                display: 'flex',
                gap: '16px',
                padding: '16px',
                backgroundColor: 'var(--bg-input)',
                borderRadius: 'var(--radius-md)',
                marginBottom: '20px',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ flex: 1 }}>
                <label className="form-label">Duração Mínima (segundos)</label>
                <input
                  type="number"
                  min={5}
                  max={customMax - 1}
                  className="form-input"
                  value={customMin}
                  onChange={(e) => setCustomMin(Math.max(5, Number(e.target.value)))}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label className="form-label">Duração Máxima (segundos)</label>
                <input
                  type="number"
                  min={customMin + 1}
                  max={600}
                  className="form-input"
                  value={customMax}
                  onChange={(e) => setCustomMax(Math.max(customMin + 1, Number(e.target.value)))}
                />
              </div>
            </div>
          )}
        </div>

        {/* SEÇÃO 4: Inteligência, Modelo e Gênero */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <Layers size={18} color="var(--primary)" aria-hidden="true" />
            <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              4. Parâmetros de IA & Conteúdo
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '20px' }}>
            {/* Modelo de Clipe */}
            <div>
              <label className="form-label">
                Modelo de Detecção
                <span className="form-hint">Estratégia de corte</span>
              </label>
              <select
                className="form-select"
                aria-label="Modelo de detecção de cortes"
                value={clipModel}
                onChange={(e) => setClipModel(e.target.value as ClipModel)}
              >
                <option value="Auto">Auto (Recomendado — Híbrido)</option>
                <option value="Conversa / Talking Head">Conversa / Talking Head (Podcast & Foco em Rosto)</option>
                <option value="Multimodal / Clip Anything">Multimodal / Clip Anything (Visual & Ação)</option>
              </select>
            </div>

            {/* Gênero de Conteúdo */}
            <div>
              <label className="form-label">
                Gênero do Conteúdo
                <span className="form-hint">Orienta o ranking de retenção</span>
              </label>
              <select
                className="form-select"
                aria-label="Gênero do conteúdo do vídeo"
                value={genre}
                onChange={(e) => setGenre(e.target.value as ContentGenre)}
              >
                {GENRES.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </div>

            {/* Quantidade de Cortes Automática */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label className="form-label" style={{ margin: 0, fontWeight: 700 }}>
                  Quantidade de Cortes
                </label>
                <Badge variant="indigo" icon={<Sparkles size={11} />}>
                  Automático
                </Badge>
              </div>
              <div
                style={{
                  padding: '12px 14px',
                  backgroundColor: 'var(--bg-surface)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid rgba(99, 102, 241, 0.25)',
                  fontSize: '0.78rem',
                  color: 'var(--text-secondary)',
                  lineHeight: 1.4,
                }}
              >
                A IA gera automaticamente todos os momentos de alto potencial dentro do trecho selecionado, sem sobreposição nem repetição de cenas.
              </div>
            </div>
          </div>

          {/* Prompt Opcional / Sugestões */}
          <div className="form-group" style={{ marginBottom: '14px' }}>
            <label className="form-label">
              Instruções Personalizadas para a IA (Opcional)
              <span className="form-hint">Peça ganchos ou momentos específicos</span>
            </label>
            <textarea
              className="form-textarea"
              placeholder="Ex: Foque nos momentos em que o convidado conta histórias engraçadas ou revela surpresas..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={2}
            />

            {/* Chips de Sugestões de Prompt */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '8px' }}>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', alignSelf: 'center' }}>
                Sugestões rápidas:
              </span>
              {PROMPT_SUGGESTIONS.map((sug, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setPrompt(sug)}
                  className="badge badge-muted"
                  style={{ cursor: 'pointer', border: '1px solid var(--border-default)', transition: 'all 0.15s' }}
                >
                  {sug}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* SEÇÃO 5: Reframe & Estilo de Legendas */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
            <Type size={18} color="var(--primary)" aria-hidden="true" />
            <h2 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              5. Enquadramento Dinâmico & Legendas (Sempre Ativos)
            </h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '14px', marginBottom: '16px' }}>
            {/* Reframe Inteligente Sempre Ativo */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 16px',
                backgroundColor: 'var(--bg-surface)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid rgba(99, 102, 241, 0.3)',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                    Reframe Inteligente de Rosto
                  </div>
                  <Badge variant="emerald" icon={<Check size={11} />}>Ativo</Badge>
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                  Rastreia e mantém o locutor no centro vertical
                </div>
              </div>
            </div>

            {/* Legendas Queimadas Sempre Ativas */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 16px',
                backgroundColor: 'var(--bg-surface)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid rgba(99, 102, 241, 0.3)',
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                    Gerar Legendas Queimadas
                  </div>
                  <Badge variant="emerald" icon={<Check size={11} />}>Ativo</Badge>
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                  Legendas dinâmicas sincronizadas no estilo TikTok/Reels
                </div>
              </div>
            </div>
          </div>

          {/* Opções de Apresentação das Legendas */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '14px',
              padding: '16px',
              backgroundColor: 'var(--bg-input)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div>
              <label className="form-label" style={{ fontSize: '0.8rem' }}>Estilo de Legenda</label>
              <select
                className="form-select"
                aria-label="Estilo de apresentação das legendas"
                value={subtitleStyle}
                onChange={(e) => setSubtitleStyle(e.target.value as SubtitleStyle)}
              >
                <option value="highlight">Highlight Dinâmico (Karaoke Viral)</option>
                <option value="classic">Clássico (Texto Estático Limpo)</option>
              </select>
            </div>

            <div>
              <label className="form-label" style={{ fontSize: '0.8rem' }}>Posição na Tela</label>
              <select
                className="form-select"
                aria-label="Posição das legendas na tela"
                value={subtitlePosition}
                onChange={(e) => setSubtitlePosition(e.target.value as SubtitlePosition)}
              >
                <option value="bottom">Inferior (Padrão)</option>
                <option value="center">Centro</option>
                <option value="top">Superior</option>
              </select>
            </div>

            <div>
              <label className="form-label" style={{ fontSize: '0.8rem' }}>
                Tamanho da Fonte ({subtitleSize}px)
              </label>
              <input
                type="range"
                aria-label="Tamanho da fonte das legendas"
                min={28}
                max={72}
                step={2}
                value={subtitleSize}
                onChange={(e) => setSubtitleSize(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--primary)', marginTop: '8px' }}
              />
            </div>
          </div>
        </div>

        {/* BOTÃO PRINCIPAL DE EXECUÇÃO */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '16px',
            padding: '20px 24px',
            backgroundColor: 'var(--bg-card)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border-default)',
            boxShadow: 'var(--shadow-md)',
          }}
        >
          <div>
            <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
              Pronto para iniciar o pipeline
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              O processamento ocorrerá em segundo plano com Whisper local e análise de virality ranking.
            </div>
          </div>

          <Button
            type="submit"
            variant="ai"
            size="lg"
            icon={<Sparkles size={18} />}
            loading={isLoading || hasActiveJob}
            disabled={isButtonDisabled}
          >
            {hasActiveJob ? 'Processamento em Andamento...' : 'Gerar Cortes com IA'}
          </Button>
        </div>
      </form>
    </div>
  );
};
