import React, { useState, useRef, useEffect } from 'react';
import {
  Play,
  Pause,
  RotateCcw,
  Save,
  Video,
  Download,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  X,
  Sparkles,
  Scissors,
  Type,
  Layout,
  Clock,
  Trash2,
  Volume2,
  Maximize2,
  Sliders,
  Check,
  Eye,
  Settings,
  ZoomIn,
  User,
} from 'lucide-react';
import type {
  Candidate,
  ClipFormat,
  Edit,
  Project,
  RemoveRange,
  SubtitlePosition,
  SubtitleStyle,
  Word,
} from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import { ScoreGauge } from '../common/ScoreGauge';
import { api } from '../../api/client';
 export interface ClipEditorProps {
   project: Project;
   candidate: Candidate;
   onSaveCandidate: (candidateId: string, edit: Edit) => Promise<void>;
   onRenderCandidate: (candidateId: string) => Promise<void>;
   onExportCandidate: (candidateId: string) => void;
   onDeleteCandidate: (candidateId: string) => Promise<void>;
   isRendering?: boolean;
 }

interface FaceBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface TrackSample {
  time: number;
  boxes: FaceBox[];
}

function mergeRanges(ranges: RemoveRange[], start: number, end: number): RemoveRange[] {
  const result: RemoveRange[] = [];
  for (const range of ranges
    .map((r) => ({ start: Math.max(start, r.start), end: Math.min(end, r.end) }))
    .filter((r) => r.end > r.start)
    .sort((a, b) => a.start - b.start)) {
    const previous = result[result.length - 1];
    if (previous && range.start <= previous.end) previous.end = Math.max(previous.end, range.end);
    else result.push({ ...range });
  }
  return result;
}

export const ClipEditor: React.FC<ClipEditorProps> = ({
  project,
  candidate,
  onSaveCandidate,
  onRenderCandidate,
  onExportCandidate,
  onDeleteCandidate,
  isRendering = false,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  // Estados de Reprodução
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(candidate.edit?.start ?? candidate.start);
  const isRendered = Boolean(candidate.rendered);
  const [previewMode, setPreviewMode] = useState<'simulation' | 'rendered'>(
    isRendered ? 'rendered' : 'simulation'
  );

  // Aba ativa do inspetor lateral: 'transcript' | 'subtitles' | 'range' | 'meta'
  const [inspectorTab, setInspectorTab] = useState<'transcript' | 'subtitles' | 'range' | 'meta'>('transcript');

  // Estados de Edição do Corte
  const [title, setTitle] = useState(candidate.edit?.title || candidate.title);
  const [start, setStart] = useState(candidate.edit?.start ?? candidate.start);
  const [end, setEnd] = useState(candidate.edit?.end ?? candidate.end);
  const [format, setFormat] = useState<ClipFormat>(candidate.edit?.format || '9:16');
  const reframe = true;
  const [autoZoom, setAutoZoom] = useState<boolean>(candidate.edit?.auto_zoom ?? true);
  const [zoomLevel, setZoomLevel] = useState<number>(candidate.edit?.zoom_level ?? 1.25);
  const [cropX, setCropX] = useState<number | null>(candidate.edit?.crop_x ?? null);
  const [tracks, setTracks] = useState<TrackSample[]>([]);
  // Legendas
  const subtitles = true;
  const [subtitleStyle, setSubtitleStyle] = useState<SubtitleStyle>(
    candidate.edit?.subtitle_style || 'highlight'
  );
  const [subtitleSize, setSubtitleSize] = useState<number>(candidate.edit?.subtitle_size || 48);
  const [subtitlePosition, setSubtitlePosition] = useState<SubtitlePosition>(
    candidate.edit?.subtitle_position || 'bottom'
  );

  // Trechos Excluídos e Palavras
  const [removeRanges, setRemoveRanges] = useState<RemoveRange[]>(
    candidate.edit?.remove_ranges || []
  );
  const [words, setWords] = useState<Word[]>(candidate.edit?.words ?? candidate.words ?? []);

  // Notificações e Salvamento
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [activeWordIndex, setActiveWordIndex] = useState<number | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [wordFilter, setWordFilter] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  // Carrega palavras completas da timeline se necessário
  useEffect(() => {
    let disposed = false;
    api.getTimeline(project.id)
      .then((timeline) => {
        if (disposed) return;
        if (timeline.tracks) {
          setTracks(timeline.tracks);
        }
        setWords((current) => [
          ...current,
          ...timeline.words.filter((word) => word.end <= start || word.start >= end),
        ].sort((a, b) => a.start - b.start));
      })
      .catch(() => {
        if (!disposed) setEditError('Não foi possível carregar dados da timeline.');
      });
    return () => {
      disposed = true;
    };
  }, [candidate.id, project.id, start, end]);

  const sourceWidth = Number(project.metadata.display_width) || project.metadata.width;
  const sourceHeight = Number(project.metadata.display_height) || project.metadata.height;
  const sourceRatio = sourceWidth / sourceHeight;
  const targetRatio = format === '16:9' ? 16 / 9 : (format === '1:1' ? 1 : 9 / 16);
  const cropW = Math.min(1, targetRatio / sourceRatio);
  const cropH = Math.min(1, sourceRatio / targetRatio);

  // Cálculo de rastreamento do sujeito/grupo e auto-zoom no tempo atual
  const focusState = React.useMemo(() => {
    if (!tracks || tracks.length === 0) {
      return { x: 0.5, y: 0.45, zoom: 1.0, hasFace: false, isGroup: false };
    }
    let closest: TrackSample | null = null;
    let minDiff = Infinity;
    for (const t of tracks) {
      const diff = Math.abs(Number(t.time) - currentTime);
      if (diff < minDiff && diff <= 2.5) {
        minDiff = diff;
        closest = t;
      }
    }
    if (!closest || !closest.boxes || closest.boxes.length === 0) {
      return { x: 0.5, y: 0.45, zoom: 1.0, hasFace: false, isGroup: false };
    }
    const boxes = closest.boxes;
    const xMin = Math.min(...boxes.map((b: FaceBox) => b.x));
    const xMax = Math.max(...boxes.map((b: FaceBox) => b.x + b.w));
    const yMin = Math.min(...boxes.map((b: FaceBox) => b.y));
    const yMax = Math.max(...boxes.map((b: FaceBox) => b.y + b.h));
    const groupW = xMax - xMin;
    const groupH = yMax - yMin;

    const groupZoomLimit = Math.min(zoomLevel, 1.05, cropW / (groupW + 0.06),
      0.7 * cropH / (groupH + 0.06));

    let fx: number;
    let fy: number;
    let fdim: number;
    let isGroup = false;
    let safeZoomMax = zoomLevel;

    if (boxes.length >= 2 && groupZoomLimit >= 1) {
      // O grupo precisa caber na largura e altura reais do recorte.
      fx = (xMin + xMax) / 2;
      fy = (yMin + yMax) / 2;
      fdim = Math.max(groupW, groupH);
      isGroup = true;
      safeZoomMax = groupZoomLimit;
    } else {
      // Sujeito individual ou grupo que não cabe no recorte
      const primary = boxes.reduce((prev: FaceBox, curr: FaceBox) =>
        (curr.w * curr.h > prev.w * prev.h ? curr : prev), boxes[0]);
      fx = primary.x + primary.w / 2;
      fy = primary.y + primary.h / 2;
      fdim = Math.max(primary.w, primary.h);
      if (boxes.length >= 2) {
        safeZoomMax = 1.0;
      }
    }

    const clampedX = Math.min(0.85, Math.max(0.15, fx));
    const clampedY = Math.min(0.85, Math.max(0.15, fy));
    const z = reframe && autoZoom
      ? 1.0 + (safeZoomMax - 1.0) * Math.min(1, Math.max(0, (0.26 - fdim) / 0.16))
      : 1.0;

    return { x: clampedX, y: clampedY, zoom: z, hasFace: true, isGroup };
  }, [tracks, currentTime, format, reframe, autoZoom, zoomLevel, cropW, cropH]);

  const activeFocusX = cropX !== null ? cropX : focusState.x;
  const activeFocusY = cropX !== null ? 0.45 : focusState.y;
  const activeZoom = cropX !== null ? 1.0 : focusState.zoom;

  // CSS object-position measures available overflow, not source coordinates.
  const previewPositionX = cropW < 1
    ? Math.min(1, Math.max(0, (activeFocusX - cropW / 2) / (1 - cropW))) : 0.5;
  const previewPositionY = cropH < 1
    ? Math.min(1, Math.max(0, (activeFocusY - 0.35 * cropH) / (1 - cropH))) : 0.5;
  const clipWords = words.filter((word) => word.start >= start && word.end <= end);
  const normalizedRanges = mergeRanges(removeRanges, start, end);

  const editPayload: Edit = {
    start,
    end,
    title: title.trim().slice(0, 240) || 'Corte',
    format,
    reframe,
    auto_zoom: autoZoom,
    zoom_level: zoomLevel,
    subtitles,
    subtitle_style: subtitleStyle,
    subtitle_size: subtitleSize,
    subtitle_position: subtitlePosition,
    crop_x: cropX,
    remove_ranges: normalizedRanges,
    words: clipWords,
  };
  // Edições salvas antes de auto_zoom/zoom_level existirem usam os padrões do backend.
  const saved = candidate.edit
    ? { ...candidate.edit, reframe: true, subtitles: true, auto_zoom: candidate.edit.auto_zoom ?? true, zoom_level: candidate.edit.zoom_level ?? 1.25 }
    : null;
  const isDirty =
    !saved ||
    Object.entries(editPayload).some(
      ([key, value]) => JSON.stringify(value) !== JSON.stringify(saved[key as keyof Edit])
    );

  const showRendered = previewMode === 'rendered' && isRendered && !isDirty;

  // Mapeamento de tempo para pular cortes
  const kept: RemoveRange[] = [];
  let cursor = start;
  for (const range of normalizedRanges) {
    if (range.start > cursor) kept.push({ start: cursor, end: range.start });
    cursor = range.end;
  }
  if (cursor < end) kept.push({ start: cursor, end });

  const outputTime = (srcTime: number) =>
    kept.reduce((sum, range) => sum + Math.max(0, Math.min(srcTime, range.end) - range.start), 0);

  const sourceTime = (outTime: number) => {
    let remaining = outTime;
    for (const range of kept) {
      if (remaining < range.end - range.start) return range.start + remaining;
      remaining -= range.end - range.start;
    }
    return end;
  };

  const rawDuration = Math.max(0, end - start);
  const excludedDuration = normalizedRanges.reduce((acc, r) => acc + r.end - r.start, 0);
  const netDuration = Math.max(0, rawDuration - excludedDuration);

  // Atualização de tempo do player
  const handleTimeUpdate = () => {
    if (!videoRef.current) return;
    const t = showRendered ? sourceTime(videoRef.current.currentTime) : videoRef.current.currentTime;
    setCurrentTime(t);

    if (!showRendered) {
      for (const range of normalizedRanges) {
        if (t >= range.start && t < range.end) {
          videoRef.current.currentTime = range.end;
          return;
        }
      }

      if (t >= end) {
        videoRef.current.pause();
        setIsPlaying(false);
        videoRef.current.currentTime = start;
      }
    }

    const foundIdx = clipWords.findIndex((w) => t >= w.start && t < w.end);
    setActiveWordIndex(foundIdx >= 0 ? foundIdx : null);
  };

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      const t = showRendered ? sourceTime(videoRef.current.currentTime) : videoRef.current.currentTime;
      if (t >= end || t < start) videoRef.current.currentTime = showRendered ? 0 : start;
      videoRef.current.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
    }
  };

  const handleSeek = (newTime: number) => {
    if (!videoRef.current) return;
    const boundedTime = Math.max(start, Math.min(end, newTime));
    videoRef.current.currentTime = showRendered ? outputTime(boundedTime) : boundedTime;
    setCurrentTime(boundedTime);
  };

  const handleCutWord = (w: Word) => {
    const isAlreadyCut = normalizedRanges.some((r) => w.start >= r.start && w.end <= r.end);
    if (isAlreadyCut) {
      // Restaura a palavra
      setRemoveRanges(removeRanges.filter((r) => !(w.start >= r.start && w.end <= r.end)));
    } else {
      // Corta a palavra
      setRemoveRanges(mergeRanges([...removeRanges, { start: w.start, end: w.end }], start, end));
    }
  };

  const handleSave = async (): Promise<boolean> => {
    setEditError(null);
    if (
      !Number.isFinite(start) ||
      !Number.isFinite(end) ||
      start < (project.options.start ?? 0) ||
      end > (project.options.end ?? project.metadata.duration ?? end) ||
      end <= start ||
      netDuration <= 0
    ) {
      setEditError('Defina um intervalo válido dentro da análise e mantenha algum conteúdo no corte.');
      return false;
    }
    setIsSaving(true);
    setSaveSuccess(false);
    try {
      await onSaveCandidate(candidate.id, editPayload);
      setRemoveRanges(normalizedRanges);
      setPreviewMode('simulation');
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      return true;
    } catch (error) {
      setEditError(error instanceof Error ? error.message : 'Falha ao salvar edição.');
      return false;
    } finally {
      setIsSaving(false);
    }
  };

  const handleRender = async () => {
    if (isDirty && !(await handleSave())) return;
    await onRenderCandidate(candidate.id);
    setPreviewMode('rendered');
  };

  const formatTimecode = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 10);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms}`;
  };

  // Palavras ativas para o preview de legendas dinâmicas
  const currentWordsSubtitle = clipWords.filter(
    (w) => w.start >= currentTime - 1.2 && w.end <= currentTime + 1.2
  );

  return (
    <div style={{ maxWidth: '1280px', margin: '0 auto' }}>
      {/* BARRA SUPERIOR DO ESTÚDIO */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px',
          marginBottom: '24px',
          paddingBottom: '16px',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <Badge variant="indigo" icon={<Scissors size={12} />}>
              ESTÚDIO DE CORTE
            </Badge>
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Projeto: <strong>{project.display_name || project.name}</strong>
            </span>
            {isDirty && (
              <Badge variant="amber" icon={<AlertTriangle size={11} />}>
                Alterações não salvas
              </Badge>
            )}
            {saveSuccess && (
              <Badge variant="emerald" icon={<CheckCircle2 size={11} />}>
                Salvo com sucesso!
              </Badge>
            )}
          </div>

          <h1
            style={{
              fontSize: '1.6rem',
              fontWeight: 800,
              color: 'var(--text-primary)',
              letterSpacing: '-0.02em',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {title}
          </h1>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <ScoreGauge score={candidate.score} size="sm" showLabel={true} />
        </div>
      </div>

      {editError && (
        <div
          style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-md)',
            padding: '12px 16px',
            color: '#fca5a5',
            fontSize: '0.88rem',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <AlertTriangle size={18} color="var(--danger)" />
          <span>{editError}</span>
        </div>
      )}

      {/* GRID DO ESTÚDIO: 2 COLUNAS */}
      <div className="editor-grid">
        {/* COLUNA 1: PLAYER DE VÍDEO VERTICAL (9:16) */}
        <div className="editor-player-column">
          {/* Seletor de Modo de Visualização */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: 'var(--bg-surface)',
              padding: '6px 12px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
              marginBottom: '4px',
            }}
          >
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>
              Modo de Exibição:
            </span>

            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                type="button"
                onClick={() => setPreviewMode('simulation')}
                className={`btn btn-sm ${previewMode === 'simulation' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: '0.75rem', padding: '4px 8px', minHeight: '28px' }}
              >
                Simulação Rápida
              </button>

              <button
                type="button"
                onClick={() => setPreviewMode('rendered')}
                disabled={!isRendered}
                className={`btn btn-sm ${previewMode === 'rendered' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: '0.75rem', padding: '4px 8px', minHeight: '28px' }}
                title={!isRendered ? 'Renderize o corte para ver o vídeo final' : undefined}
              >
                Vídeo Renderizado
              </button>
            </div>
          </div>

          {/* MOLDURA DO VÍDEO CONFORME FORMATO SELECIONADO */}
          <div
            className="clip-video-frame"
            style={{
              position: 'relative',
              overflow: 'hidden',
              aspectRatio: format === '16:9' ? '16 / 9' : (format === '1:1' ? '1 / 1' : '9 / 16'),
              maxWidth: format === '16:9' ? '100%' : (format === '1:1' ? '460px' : '320px'),
              margin: '0 auto',
            }}
          >
            <video
              ref={videoRef}
              src={
                showRendered
                  ? api.getCandidateVideoUrl(project.id, candidate.id)
                  : `${api.getSourceUrl(project.id)}#t=${start},${end}`
              }
              onLoadedMetadata={() => {
                if (!showRendered && videoRef.current) {
                  if (videoRef.current.currentTime < start || videoRef.current.currentTime > end) {
                    videoRef.current.currentTime = start;
                  }
                }
              }}
              onTimeUpdate={handleTimeUpdate}
              onEnded={() => {
                setIsPlaying(false);
                if (videoRef.current) videoRef.current.currentTime = start;
              }}
              playsInline
              style={{
                width: '100%',
                height: '100%',
                objectFit: showRendered || !reframe ? 'contain' : 'cover',
                objectPosition: showRendered || !reframe
                  ? 'center'
                  : `${previewPositionX * 100}% ${previewPositionY * 100}%`,
                transform: showRendered ? 'none' : `scale(${activeZoom})`,
                transformOrigin: '50% 35%',
                transition: 'transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), object-position 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
                backgroundColor: '#000000',
              }}
            />

            {/* BADGE INDICADOR DE AUTO-ZOOM E FOCO NA PESSOA EM SIMULAÇÃO */}
            {!showRendered && reframe && (
              <div
                style={{
                  position: 'absolute',
                  top: '12px',
                  left: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: 'rgba(15, 23, 42, 0.75)',
                  backdropFilter: 'blur(6px)',
                  padding: '4px 8px',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  fontSize: '0.72rem',
                  color: '#ffffff',
                  pointerEvents: 'none',
                  zIndex: 3,
                }}
              >
                {focusState.hasFace ? (
                  <>
                    <User size={12} color="#10b981" />
                    <span>
                      {focusState.isGroup ? 'Grupo Detectado' : 'Rosto Detectado'}
                      {autoZoom && activeZoom > 1.01 ? ` · Zoom ${activeZoom.toFixed(2)}x` : ' · Seguro'}
                    </span>
                  </>
                ) : (
                  <>
                    <User size={12} color="#94a3b8" />
                    <span>Enquadramento Neutro</span>
                  </>
                )}
              </div>
            )}
            {/* OVERLAY DE LEGENDAS EM SIMULAÇÃO */}
            {!showRendered && subtitles && (
              <div
                style={{
                  position: 'absolute',
                  left: '12px',
                  right: '12px',
                  bottom: subtitlePosition === 'bottom' ? '18%' : subtitlePosition === 'center' ? '45%' : '15%',
                  textAlign: 'center',
                  pointerEvents: 'none',
                  textShadow: '0 2px 8px rgba(0,0,0,0.9), 0 0 4px #000000',
                  lineHeight: 1.3,
                }}
              >
                <div
                  style={{
                    display: 'inline-block',
                    padding: '6px 12px',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: 'rgba(0, 0, 0, 0.65)',
                    backdropFilter: 'blur(4px)',
                    fontSize: `${Math.max(14, Math.round(subtitleSize * 0.35))}px`,
                    fontWeight: 800,
                  }}
                >
                  {currentWordsSubtitle.length > 0 ? (
                    currentWordsSubtitle.map((w, idx) => {
                      const isActive = currentTime >= w.start && currentTime <= w.end;
                      return (
                        <span
                          key={idx}
                          style={{
                            color: isActive && subtitleStyle === 'highlight' ? 'var(--primary)' : '#ffffff',
                            transform: isActive ? 'scale(1.08)' : 'none',
                            display: 'inline-block',
                            margin: '0 3px',
                            transition: 'all 0.1s ease',
                          }}
                        >
                          {w.word}
                        </span>
                      );
                    })
                  ) : (
                    <span style={{ color: 'rgba(255, 255, 255, 0.4)', fontStyle: 'italic', fontSize: '0.8rem' }}>
                      [Prévia de Legendas]
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* CONTROLES DE REPRODUÇÃO E TIMECODE */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
              backgroundColor: 'var(--bg-surface)',
              padding: '14px 18px',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            {/* Scrubber / Barra de Progresso */}
            <input
              type="range"
              min={start}
              max={end}
              step={0.1}
              value={currentTime}
              onChange={(e) => handleSeek(Number(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--primary)', cursor: 'pointer' }}
              aria-label="Posição de reprodução no vídeo"
            />

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Button
                  variant="primary"
                  size="sm"
                  icon={isPlaying ? <Pause size={16} /> : <Play size={16} />}
                  onClick={togglePlay}
                  aria-label={isPlaying ? 'Pausar vídeo' : 'Reproduzir vídeo'}
                >
                  {isPlaying ? 'Pausar' : 'Reproduzir'}
                </Button>

                <button
                  type="button"
                  onClick={() => handleSeek(start)}
                  className="btn btn-ghost btn-sm"
                  style={{ padding: '6px', minWidth: '32px' }}
                  title="Reiniciar corte do início"
                  aria-label="Reiniciar do início do corte"
                >
                  <RotateCcw size={15} />
                </button>
              </div>

              <div className="font-mono" style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--text-primary)', fontWeight: 700 }}>
                  {formatTimecode(currentTime - start)}
                </span>{' '}
                / <span>{formatTimecode(netDuration)}</span>
              </div>
            </div>
          </div>

          {/* CONTROLE DE ENQUADRAMENTO MANUAL (CROP X) */}
          <div
            style={{
              padding: '14px 18px',
              backgroundColor: 'var(--bg-surface)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                Enquadramento Horizontal:
              </span>
              <button
                type="button"
                onClick={() => setCropX(cropX === null ? 0.5 : null)}
                className={`badge ${cropX === null ? 'badge-indigo' : 'badge-muted'}`}
                style={{ cursor: 'pointer', border: 'none' }}
              >
                {cropX === null ? 'Auto Rastreamento (IA)' : 'Posição Manual'}
              </button>
            </div>

            {cropX !== null && (
              <div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={cropX}
                  onChange={(e) => setCropX(Number(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--ai-indigo)' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  <span>Esquerda (0.0)</span>
                  <span>Centro (0.5)</span>
                  <span>Direita (1.0)</span>
                </div>
              </div>
            )}
          </div>

          {/* CONTROLE DE AUTO-ZOOM E FOCO EM PESSOAS (ITEM 4) */}
          <div
            style={{
              padding: '14px 18px',
              backgroundColor: 'var(--bg-surface)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <ZoomIn size={15} color="var(--primary)" />
                <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Auto-Zoom & Foco nas Pessoas:
                </span>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.78rem' }}>
                <span>{autoZoom ? 'Ativado' : 'Desativado'}</span>
                <input
                  type="checkbox"
                  checked={autoZoom}
                  onChange={(e) => setAutoZoom(e.target.checked)}
                  style={{ width: '16px', height: '16px', accentColor: 'var(--primary)', cursor: 'pointer' }}
                />
              </label>
            </div>

            {autoZoom && (
              <div>
                <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
                  {[
                    { label: 'Suave (1.15x)', val: 1.15 },
                    { label: 'Dinâmico (1.25x)', val: 1.25 },
                    { label: 'Intenso (1.40x)', val: 1.40 },
                  ].map((lvl) => (
                    <button
                      key={lvl.val}
                      type="button"
                      onClick={() => setZoomLevel(lvl.val)}
                      className={`btn btn-sm ${zoomLevel === lvl.val ? 'btn-primary' : 'btn-ghost'}`}
                      style={{ fontSize: '0.72rem', padding: '3px 8px', flex: 1 }}
                    >
                      {lvl.label}
                    </button>
                  ))}
                </div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Aplica zoom inteligente automático mantendo o foco nas pessoas e nos momentos-chave do clipe.
                </div>
              </div>
            )}
          </div>
        </div>

        {/* COLUNA 2: INSPETOR E PAINEL DE EDIÇÃO */}
        <div className="editor-controls-column">
          {/* ABAS DO INSPETOR */}
          <div
            style={{
              display: 'flex',
              gap: '6px',
              borderBottom: '1px solid var(--border-subtle)',
              paddingBottom: '8px',
            }}
          >
            <button
              type="button"
              onClick={() => setInspectorTab('transcript')}
              className={`btn btn-sm ${inspectorTab === 'transcript' ? 'btn-primary' : 'btn-ghost'}`}
            >
              <Type size={14} />
              Transcrição & Palavras ({clipWords.length})
            </button>

            <button
              type="button"
              onClick={() => setInspectorTab('subtitles')}
              className={`btn btn-sm ${inspectorTab === 'subtitles' ? 'btn-primary' : 'btn-ghost'}`}
            >
              <Sparkles size={14} />
              Legendas & Estilo
            </button>

            <button
              type="button"
              onClick={() => setInspectorTab('range')}
              className={`btn btn-sm ${inspectorTab === 'range' ? 'btn-primary' : 'btn-ghost'}`}
            >
              <Clock size={14} />
              Intervalo & Duração
            </button>

            <button
              type="button"
              onClick={() => setInspectorTab('meta')}
              className={`btn btn-sm ${inspectorTab === 'meta' ? 'btn-primary' : 'btn-ghost'}`}
            >
              <Settings size={14} />
              Metadados
            </button>
          </div>

          {/* CONTEÚDO DA ABA 1: TRANSCRIÇÃO & CORTE DE PALAVRAS */}
          {inspectorTab === 'transcript' && (
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <div>
                  <h2 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    Edição por Palavra (Word-Level Editing)
                  </h2>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Clique para pular o vídeo até a palavra. Clique no botão de corte para remover hesitações ou silêncios.
                  </p>
                </div>

                {normalizedRanges.length > 0 && (
                  <Badge variant="rose" icon={<Scissors size={11} />}>
                    {normalizedRanges.length} trechos removidos
                  </Badge>
                )}
              </div>

              {/* Caixa de Palavras Interativas */}
              <div className="words-transcript-box" style={{ minHeight: '260px' }}>
                {clipWords.length > 0 ? (
                  clipWords.map((word, idx) => {
                    const isCut = normalizedRanges.some((r) => word.start >= r.start && word.end <= r.end);
                    const isSpeakingNow = currentTime >= word.start && currentTime <= word.end;

                    return (
                      <span
                        key={idx}
                        tabIndex={0}
                        role="button"
                        aria-label={`Palavra: ${word.word}. Pressione Enter para pular ou Espaço para cortar.`}
                        className={`word-chip ${isSpeakingNow ? 'active-spoken' : ''} ${isCut ? 'removed' : ''}`}
                        onClick={() => handleSeek(word.start)}
                        onDoubleClick={() => handleCutWord(word)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            handleSeek(word.start);
                          } else if (e.key === ' ') {
                            e.preventDefault();
                            handleCutWord(word);
                          }
                        }}
                        title={`Timestamp: ${formatTimecode(word.start)} • Enter para pular • Espaço para remover/restaurar`}
                      >
                        {word.word}
                        {isCut && <span style={{ fontSize: '0.65rem', marginLeft: '3px', color: 'var(--danger)' }}>✕</span>}
                      </span>
                    );
                  })
                ) : (
                  <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px 0' }}>
                    Nenhuma palavra transcrita neste trecho.
                  </p>
                )}
              </div>

              {/* Lista de Trechos Removidos */}
              {normalizedRanges.length > 0 && (
                <div style={{ marginTop: '16px' }}>
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                    Trechos Excluídos do Vídeo:
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {normalizedRanges.map((r, i) => (
                      <div
                        key={i}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          backgroundColor: 'rgba(239, 68, 68, 0.1)',
                          border: '1px solid rgba(239, 68, 68, 0.25)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '4px 10px',
                          fontSize: '0.78rem',
                          color: '#fca5a5',
                        }}
                      >
                        <span className="font-mono">{formatTimecode(r.start)} → {formatTimecode(r.end)}</span>
                        <button
                          type="button"
                          onClick={() => setRemoveRanges(removeRanges.filter((_, idx) => idx !== i))}
                          style={{ background: 'transparent', border: 'none', color: '#fca5a5', cursor: 'pointer' }}
                          title="Restaurar trecho"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* CONTEÚDO DA ABA 2: LEGENDAS & ESTILO */}
          {inspectorTab === 'subtitles' && (
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <div>
                  <h2 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    Personalização de Legendas
                  </h2>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Ajuste animação, escala e posicionamento das legendas queimadas.
                  </p>
                </div>

                <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  Legendas queimadas sempre ativas nos cortes gerados
                </span>
              </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {/* Estilo Visual */}
                  <div>
                    <label className="form-label">Estilo de Apresentação</label>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                      <button
                        type="button"
                        onClick={() => setSubtitleStyle('highlight')}
                        className={`card card-interactive ${subtitleStyle === 'highlight' ? 'active' : ''}`}
                        style={{
                          padding: '12px',
                          border: subtitleStyle === 'highlight' ? '2px solid var(--primary)' : '1px solid var(--border-default)',
                          background: subtitleStyle === 'highlight' ? 'rgba(244, 63, 94, 0.08)' : 'var(--bg-input)',
                        }}
                      >
                        <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>Highlight Karaoke</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Palavra ativa salta em destaque</div>
                      </button>

                      <button
                        type="button"
                        onClick={() => setSubtitleStyle('classic')}
                        className={`card card-interactive ${subtitleStyle === 'classic' ? 'active' : ''}`}
                        style={{
                          padding: '12px',
                          border: subtitleStyle === 'classic' ? '2px solid var(--primary)' : '1px solid var(--border-default)',
                          background: subtitleStyle === 'classic' ? 'rgba(244, 63, 94, 0.08)' : 'var(--bg-input)',
                        }}
                      >
                        <div style={{ fontWeight: 700, fontSize: '0.88rem' }}>Clássico</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Linha inteira com cor padrão</div>
                      </button>
                    </div>
                  </div>

                  {/* Posição na Tela */}
                  <div>
                    <label className="form-label">Posição na Tela</label>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
                      {(['bottom', 'center', 'top'] as SubtitlePosition[]).map((pos) => (
                        <button
                          key={pos}
                          type="button"
                          onClick={() => setSubtitlePosition(pos)}
                          className={`btn btn-sm ${subtitlePosition === pos ? 'btn-primary' : 'btn-secondary'}`}
                        >
                          {pos === 'bottom' ? 'Inferior' : pos === 'center' ? 'Centro' : 'Superior'}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Tamanho da Fonte */}
                  <div>
                    <label className="form-label">
                      Tamanho da Fonte: <span className="font-mono">{subtitleSize}px</span>
                    </label>
                    <input
                      type="range"
                      min={28}
                      max={72}
                      step={2}
                      value={subtitleSize}
                      onChange={(e) => setSubtitleSize(Number(e.target.value))}
                      style={{ width: '100%', accentColor: 'var(--primary)' }}
                    />
                  </div>
                </div>
            </div>
          )}

          {/* CONTEÚDO DA ABA 3: INTERVALO & DURAÇÃO */}
          {inspectorTab === 'range' && (
            <div className="card">
              <h2 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
                Ajuste Fino de Início e Fim
              </h2>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
                Expanda ou encurte os limites do corte dentro do vídeo analisado.
              </p>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                <div>
                  <label className="form-label">Início ({formatTimecode(start)})</label>
                  <input
                    type="range"
                    min={project.options.start ?? 0}
                    max={end - 0.5}
                    step={0.1}
                    value={start}
                    onChange={(e) => setStart(Number(e.target.value))}
                    style={{ width: '100%', accentColor: 'var(--primary)' }}
                  />
                </div>

                <div>
                  <label className="form-label">Fim ({formatTimecode(end)})</label>
                  <input
                    type="range"
                    min={start + 0.5}
                    max={project.options.end ?? project.metadata.duration ?? end}
                    step={0.1}
                    value={end}
                    onChange={(e) => setEnd(Number(e.target.value))}
                    style={{ width: '100%', accentColor: 'var(--primary)' }}
                  />
                </div>
              </div>

              {/* Formato de Tela */}
              <div>
                <label className="form-label">Proporção de Corte</label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
                  {(['9:16', '1:1', '16:9'] as ClipFormat[]).map((fmt) => (
                    <button
                      key={fmt}
                      type="button"
                      onClick={() => setFormat(fmt)}
                      className={`btn btn-sm ${format === fmt ? 'btn-primary' : 'btn-secondary'}`}
                    >
                      {fmt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* CONTEÚDO DA ABA 4: METADADOS */}
          {inspectorTab === 'meta' && (
            <div className="card">
              <h2 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '16px' }}>
                Título & Identificação do Corte
              </h2>

              <div className="form-group">
                <label className="form-label">Título do Clipe</label>
                <input
                  type="text"
                  className="form-input"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={240}
                />
              </div>

              {candidate.summary && (
                <div style={{ marginTop: '12px' }}>
                  <label className="form-label">Gancho / Resumo Detectado (Hook)</label>
                  <div
                    style={{
                      padding: '10px 14px',
                      backgroundColor: 'var(--bg-input)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.85rem',
                      fontStyle: 'italic',
                      color: 'var(--text-secondary)',
                    }}
                  >
                    "{candidate.summary}"
                  </div>
                </div>
              )}
            </div>
          )}

          {/* BARRA FIXADA DE AÇÕES DO EDITOR */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '12px',
              padding: '16px 20px',
              backgroundColor: 'var(--bg-surface)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border-default)',
              boxShadow: 'var(--shadow-md)',
              marginTop: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Button
                variant="secondary"
                icon={<Save size={16} />}
                loading={isSaving}
                onClick={handleSave}
                disabled={!isDirty}
              >
                Salvar Edições
              </Button>

              <Button
                variant="primary"
                icon={isRendering ? <Loader2 className="animate-spin" size={16} /> : <Video size={16} />}
                loading={isRendering}
                onClick={handleRender}
                title="Renderizar corte com FFmpeg"
              >
                Renderizar Vídeo
              </Button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {isRendered && (
                <Button
                  variant="ai"
                  icon={<Download size={16} />}
                  onClick={() => onExportCandidate(candidate.id)}
                >
                  Baixar MP4
                </Button>
              )}

              {showDeleteConfirm ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Button
                    variant="danger"
                    size="sm"
                    loading={isDeleting}
                    onClick={async () => {
                      setIsDeleting(true);
                      try {
                        await onDeleteCandidate(candidate.id);
                      } finally {
                        setIsDeleting(false);
                        setShowDeleteConfirm(false);
                      }
                    }}
                  >
                    Confirmar
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowDeleteConfirm(false)}
                  >
                    Cancelar
                  </Button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowDeleteConfirm(true)}
                  className="btn btn-ghost btn-sm"
                  style={{ padding: '6px', minWidth: '32px', color: 'var(--text-muted)' }}
                  title="Excluir este corte"
                  aria-label="Excluir este corte"
                >
                  <Trash2 size={16} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
