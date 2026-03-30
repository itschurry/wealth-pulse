import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

type ToastTone = 'info' | 'success' | 'warning' | 'error';

interface ToastItem {
  id: string;
  title: string;
  description?: string;
  tone: ToastTone;
}

interface ToastContextValue {
  pushToast: (toast: Omit<ToastItem, 'id'>) => void;
}

const TOAST_LIMIT = 5;
const TOAST_DURATION_MS = 4200;

const ToastContext = createContext<ToastContextValue | null>(null);

function toneLabel(tone: ToastTone): string {
  if (tone === 'success') return '성공';
  if (tone === 'warning') return '경고';
  if (tone === 'error') return '오류';
  return '안내';
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback((toast: Omit<ToastItem, 'id'>) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const next: ToastItem = { id, ...toast };
    setToasts((prev) => [next, ...prev].slice(0, TOAST_LIMIT));
    window.setTimeout(() => {
      dismissToast(id);
    }, TOAST_DURATION_MS);
  }, [dismissToast]);

  const value = useMemo<ToastContextValue>(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-viewport" aria-live="polite" aria-atomic="true">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast-card is-${toast.tone}`} role="status">
            <div className="toast-card-head">
              <span className="toast-card-tone">{toneLabel(toast.tone)}</span>
              <button
                type="button"
                className="toast-card-close"
                aria-label="토스트 닫기"
                onClick={() => dismissToast(toast.id)}
              >
                x
              </button>
            </div>
            <div className="toast-card-title">{toast.title}</div>
            {toast.description && <div className="toast-card-description">{toast.description}</div>}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}
