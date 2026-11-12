import React from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
}

export interface ToastContainerProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const ToastContainer: React.FC<ToastContainerProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div className="toast-container" aria-live="polite">
      {toasts.map((toast) => {
        const isError = toast.type === 'error';
        const isSuccess = toast.type === 'success';

        const toastTypeClass = isError
          ? 'toast-error'
          : isSuccess
          ? 'toast-success'
          : 'toast-info';

        return (
          <div
            key={toast.id}
            role={isError ? 'alert' : 'status'}
            aria-live={isError ? 'assertive' : 'polite'}
            className={`toast-item ${toastTypeClass} animate-in-slide`}
          >
            <div className="toast-icon-wrap" aria-hidden="true">
              {isError && <AlertCircle size={18} color="var(--danger)" />}
              {isSuccess && <CheckCircle2 size={18} color="var(--success)" />}
              {!isError && !isSuccess && <Info size={18} color="var(--ai-indigo)" />}
            </div>
            <div className="toast-body">
              <p className="toast-message">{toast.message}</p>
            </div>
            <button
              onClick={() => onDismiss(toast.id)}
              className="toast-dismiss-btn"
              aria-label="Dispensar notificação"
            >
              <X size={15} aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
