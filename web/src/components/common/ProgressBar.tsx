import React from 'react';

export interface ProgressBarProps {
  progress: number; // 0 a 1 ou 0 a 100
  label?: string;
  stage?: string;
  className?: string;
  variant?: 'primary' | 'ai' | 'success';
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  progress,
  label,
  stage,
  className = '',
  variant = 'primary',
}) => {
  const normalizedValue = progress <= 1.0 && progress > 0 ? Math.round(progress * 100) : Math.round(progress);
  const clampedValue = Math.min(100, Math.max(0, normalizedValue));

  const fillClass = {
    primary: 'progress-fill-primary',
    ai: 'progress-fill-ai',
    success: 'progress-fill-success',
  }[variant];

  return (
    <div className={`progress-container ${className}`.trim()} role="group" aria-label={label || 'Progresso'}>
      {(label || stage) && (
        <div className="progress-header">
          <span className="progress-stage">{stage || label}</span>
          <span className="progress-value font-mono">{clampedValue}%</span>
        </div>
      )}
      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={clampedValue}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label || stage || 'Progresso da operação'}
      >
        <div
          className={`progress-fill ${fillClass}`}
          style={{ width: `${clampedValue}%` }}
        />
      </div>
    </div>
  );
};
