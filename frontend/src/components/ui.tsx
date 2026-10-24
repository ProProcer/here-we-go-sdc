import { t } from '../i18n';
import type { ReactNode } from 'react';

const paths = {
  panelClose: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16m7-11-3 3 3 3" /></>,
  panelOpen: <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16m4-11 3 3-3 3" /></>,
  chevron: <path d="m6 9 6 6 6-6" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  flag: <><path d="M5 21V3m0 1c5-4 9 4 14 0v10c-5 4-9-4-14 0" /></>,
  upload: <path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5" />,
  skills: <><rect x="4" y="3" width="16" height="18" rx="4" /><path d="m8 9 2 2 5-5M8 16h8" /></>,
  career: <><rect x="3" y="7" width="18" height="14" rx="4" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12a21 21 0 0 0 18 0M12 12v3" /></>,
  path: <><circle cx="6" cy="5" r="2" /><circle cx="18" cy="19" r="2" /><path d="M8 5h7a4 4 0 0 1 0 8H9a3 3 0 0 0 0 6h7" /></>,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  check: <path d="m5 12 4 4L19 6" />,
  book: <path d="M12 5C8 2 4 3 3 4v16c3-2 6-1 9 1 3-2 6-3 9-1V4c-1-1-5-2-9 1Zm0 0v16" />,
  spark: <path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3Z" />,
};
export type IconName = keyof typeof paths;
export function Icon({ name }: { name: IconName }) { return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">{t(paths[name])}</svg>; }
export function Chip({ children, kind = '' }: { children: ReactNode; kind?: string }) { return <span className={`chip ${kind}`}>{t(children)}</span>; }
export function Disclosure({ title, children, id, className = '', help = false, onToggle }: { title: string; children: ReactNode; id?: string; className?: string; help?: boolean; onToggle?: (open: boolean) => void }) {
  return <details id={id} className={`disclosure ${help ? 'help-disclosure' : ''} ${className}`} onToggle={event => onToggle?.(event.currentTarget.open)}><summary>{t(title)} {help ? <span className="help-mark" aria-hidden="true">?</span> : <Icon name="chevron" />}</summary><div className="disclosure-content">{t(children)}</div></details>;
}
export function EmptyState({ title, children, symbol = 'spark', compact = false, action }: { title: string; children: ReactNode; symbol?: IconName; compact?: boolean; action?: ReactNode }) {
  return <div className={`empty-state ${compact ? 'compact' : ''}`}><span className="empty-symbol"><Icon name={symbol} /></span><h3>{t(title)}</h3><p>{t(children)}</p>{t(action)}</div>;
}
export function ExternalLink({ url, children, button = false }: { url: string; children: ReactNode; button?: boolean }) {
  try { if (new URL(url).protocol === 'https:') return <a className={button ? 'button secondary source-button' : undefined} href={url} target="_blank" rel="noopener noreferrer">{t(children)} ↗</a>; } catch { /* Render untrusted/invalid URLs as plain text. */ }
  return <>{t(children)}</>;
}
export const percent = (value: number | null) => value == null ? 'Not available' : `${(value * 100).toFixed(1)}%`;
export const date = (value: string | null | undefined) => value ? value.slice(0, 10) : 'Not recorded';
