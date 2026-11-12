import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'emerald' | 'amber' | 'rose' | 'indigo' | 'sky' | 'muted' | 'outline';
  icon?: React.ReactNode;
  className?: string;
  title?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'muted',
  icon,
  className = '',
  title,
}) => {
  const variantClass = {
    emerald: 'badge-emerald',
    amber: 'badge-amber',
    rose: 'badge-rose',
    indigo: 'badge-indigo',
    sky: 'badge-sky',
    muted: 'badge-muted',
    outline: 'badge-outline',
  }[variant];

  return (
    <span title={title} className={`badge ${variantClass} ${className}`.trim()}>
      {icon && <span className="badge-icon" aria-hidden="true">{icon}</span>}
      <span className="badge-text">{children}</span>
    </span>
  );
};
