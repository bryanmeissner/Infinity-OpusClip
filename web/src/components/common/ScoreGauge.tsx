import React from 'react';

export interface ScoreGaugeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

export const ScoreGauge: React.FC<ScoreGaugeProps> = ({
  score,
  size = 'md',
  showLabel = true,
}) => {
  const rounded = Math.round(Math.max(0, Math.min(100, score)));

  // Determina nível e cor semântica
  const isHigh = rounded >= 80;
  const isMed = rounded >= 50 && rounded < 80;

  const color = isHigh
    ? 'var(--emerald)'
    : isMed
    ? 'var(--amber)'
    : 'var(--rose)';

  const bgTrack = isHigh
    ? 'rgba(16, 185, 129, 0.15)'
    : isMed
    ? 'rgba(245, 158, 11, 0.15)'
    : 'rgba(244, 63, 94, 0.15)';

  const glowShadow = isHigh
    ? '0 0 16px rgba(16, 185, 129, 0.35)'
    : isMed
    ? '0 0 16px rgba(245, 158, 11, 0.3)'
    : '0 0 16px rgba(244, 63, 94, 0.25)';

  const dimension = size === 'sm' ? 44 : size === 'lg' ? 84 : 60;
  const strokeWidth = size === 'sm' ? 4 : size === 'lg' ? 7 : 5;
  const radius = (dimension - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (rounded / 100) * circumference;

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: size === 'sm' ? '8px' : '12px',
      }}
      role="meter"
      aria-valuenow={rounded}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Potencial estimado: ${rounded} de 100`}
    >
      <div
        style={{
          position: 'relative',
          width: `${dimension}px`,
          height: `${dimension}px`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <svg
          width={dimension}
          height={dimension}
          style={{ transform: 'rotate(-90deg)', overflow: 'visible' }}
        >
          {/* Track de fundo */}
          <circle
            cx={dimension / 2}
            cy={dimension / 2}
            r={radius}
            stroke={bgTrack}
            strokeWidth={strokeWidth}
            fill="none"
          />
          {/* Arco preenchido */}
          <circle
            cx={dimension / 2}
            cy={dimension / 2}
            r={radius}
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            fill="none"
            style={{
              transition: 'stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
              filter: size === 'lg' ? `drop-shadow(${glowShadow})` : undefined,
            }}
          />
        </svg>

        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            textAlign: 'center',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontWeight: 800,
              fontSize: size === 'sm' ? '0.85rem' : size === 'lg' ? '1.5rem' : '1.1rem',
              color: 'var(--text-primary)',
              lineHeight: 1,
            }}
          >
            {rounded}
          </span>
          {size === 'lg' && (
            <span
              style={{
                fontSize: '0.65rem',
                color: 'var(--text-muted)',
                fontWeight: 600,
                marginTop: '2px',
              }}
            >
              / 100
            </span>
          )}
        </div>
      </div>

      {showLabel && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <span
            style={{
              fontSize: size === 'sm' ? '0.75rem' : '0.85rem',
              fontWeight: 700,
              color: color,
              lineHeight: 1.2,
            }}
          >
            {isHigh ? 'Alto Potencial' : isMed ? 'Potencial Médio' : 'Potencial Moderado'}
          </span>
          <span
            style={{
              fontSize: '0.7rem',
              color: 'var(--text-muted)',
            }}
          >
            Estimado por IA
          </span>
        </div>
      )}
    </div>
  );
};
