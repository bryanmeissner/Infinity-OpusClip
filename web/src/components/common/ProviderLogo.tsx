import React from 'react';
import type { ProviderKind } from '../../types';

export interface ProviderLogoProps {
  kind: ProviderKind | string;
  size?: number;
  className?: string;
}

export const ProviderLogo: React.FC<ProviderLogoProps> = ({ kind, size = 20, className = '' }) => {
  const normalizedKind = kind.toLowerCase();

  if (normalizedKind === 'openai') {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Logo da OpenAI"
        role="img"
      >
        <path
          d="M21.5 10.5C21.4 7.5 19.3 5.4 16.3 5.3C15.9 3.5 14.5 2.1 12.6 1.8C10.7 1.5 8.8 2.3 7.7 3.8C6.1 3.5 4.5 4.3 3.7 5.7C2.9 7.1 3 8.9 4 10.1C3.1 11.5 3.1 13.3 3.9 14.7C4.7 16.1 6.3 16.9 7.9 16.6C8.7 18 10.3 18.9 12 18.9C12.3 18.9 12.7 18.9 13 18.8C13.8 20.2 15.3 21.1 17 21.1C19.2 21.1 21.1 19.5 21.5 17.3C22.6 15.3 22.4 12.7 21.5 10.5ZM12 17.4C10.7 17.4 9.5 16.7 8.9 15.6L10.3 14.8C10.6 15.4 11.3 15.8 12 15.8C13.3 15.8 14.3 14.7 14.3 13.5V10.2L12.9 11C12.8 11.1 12.7 11.1 12.6 11.1C12.2 11.1 11.9 10.8 11.9 10.4V8.5L9.6 9.8C9.2 10 8.7 10.1 8.3 10C7.7 9.8 7.3 9.4 7 8.9C6.4 7.8 6.8 6.5 7.9 5.9C8.3 5.7 8.7 5.6 9.2 5.6C9.9 5.6 10.6 6 11 6.6L12.4 9.1L14.7 7.8C15.3 7.4 16.1 7.4 16.8 7.8C17.4 8.2 17.8 8.8 17.8 9.5C17.8 9.7 17.8 9.9 17.7 10.1L15.4 11.4V14C15.4 15.9 13.9 17.4 12 17.4Z"
          fill="currentColor"
        />
      </svg>
    );
  }

  if (normalizedKind === 'gemini') {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Logo do Google Gemini"
        role="img"
      >
        <path
          d="M12 2C12 7.52285 16.4772 12 22 12C16.4772 12 12 16.4772 12 22C12 16.4772 7.52285 12 2 12C7.52285 12 12 7.52285 12 2Z"
          fill="url(#gemini-gradient)"
        />
        <defs>
          <linearGradient id="gemini-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
            <stop stopColor="#4E82EE" />
            <stop offset="0.5" stopColor="#9B72CF" />
            <stop offset="1" stopColor="#D96570" />
          </linearGradient>
        </defs>
      </svg>
    );
  }

  if (normalizedKind === 'anthropic') {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label="Logo do Anthropic Claude"
        role="img"
      >
        <path
          d="M13.78 3.5L18.42 16.5H15.02L14.07 13.74H9.93L8.98 16.5H5.58L10.22 3.5H13.78ZM12 7.54L10.82 10.96H13.18L12 7.54Z"
          fill="#D97757"
        />
      </svg>
    );
  }
  if (normalizedKind === 'glm') {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        className={className}
        aria-label="Logo Zhipu AI GLM"
        role="img"
      >
        <defs>
          <linearGradient id="glmGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3B82F6" />
            <stop offset="50%" stopColor="#6366F1" />
            <stop offset="100%" stopColor="#8B5CF6" />
          </linearGradient>
        </defs>
        <path
          d="M12 2L3 7v10l9 5 9-5V7l-9-5zm0 3.3l6.5 3.6-2.8 1.6L12 8.7l-3.7 1.8-2.8-1.6L12 5.3zm-7 4.7l6 3.3v6.7L5 16.7V10zm14 6.7l-6 3.3v-6.7l6-3.3v6.7z"
          fill="url(#glmGradient)"
        />
      </svg>
    );
  }
  if (normalizedKind === 'omp') {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        aria-label="Conta logada via OMP"
        role="img"
      >
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" />
      </svg>
    );
  }
  if (normalizedKind === 'openrouter') {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
      >
        <path
          d="M12 2L3 7V17L12 22L21 17V7L12 2Z"
          stroke="#6366f1"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M12 6L16.5 8.5V13.5L12 16L7.5 13.5V8.5L12 6Z"
          fill="#6366f1"
          fillOpacity="0.25"
          stroke="#818cf8"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <circle cx="12" cy="11" r="2.2" fill="#a855f7" />
        <path
          d="M12 2V6M12 16V22M3 7L7.5 8.5M16.5 8.5L21 7M3 17L7.5 13.5M16.5 13.5L21 17"
          stroke="#6366f1"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  // Compatible / Ollama / Local
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-label="Logo Local / OpenAI Compatible"
      role="img"
    >
      <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
      <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
      <line x1="6" y1="6" x2="6.01" y2="6" />
      <line x1="6" y1="18" x2="6.01" y2="18" />
      <circle cx="17" cy="6" r="1" />
      <circle cx="17" cy="18" r="1" />
    </svg>
  );
};
