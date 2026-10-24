import { useSyncExternalStore } from 'react';
import catalogue from './locales.json';

export type Language = 'en' | 'ms' | 'zh';
const storageKey = 'ikiguy-language';
const supported = (value: unknown): value is Language => value === 'en' || value === 'ms' || value === 'zh';
let language: Language = 'en';
try { const saved = localStorage.getItem(storageKey); if (supported(saved)) language = saved; } catch { /* Storage may be disabled. */ }
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
export const getLanguage = () => language;
export const useLanguage = () => useSyncExternalStore(subscribe, getLanguage, () => 'en' as Language);
export function setLanguage(value: Language) {
  if (!supported(value)) return;
  language = value;
  document.documentElement.lang = value === 'zh' ? 'zh-Hans' : value;
  try { localStorage.setItem(storageKey, value); } catch { /* Language still works for this visit. */ }
  listeners.forEach(listener => listener());
}
document.documentElement.lang = language === 'zh' ? 'zh-Hans' : language;

// Only displayed strings are localized. IDs, form values, URLs and API payloads stay canonical.
export function t<T>(value: T): T {
  if (typeof value !== 'string' || language === 'en') return value;
  const text = value.replace(/\s+/g, ' ').trim();
  const rows = catalogue as Record<string, { ms: string; zh: string }>;
  let translated = rows[text]?.[language];
  if (!translated) {
    const numbers: string[] = [];
    const template = text.replace(/\d+(?:\.\d+)?/g, number => `{${numbers.push(number) - 1}}`);
    translated = rows[template]?.[language]?.replace(/\{(\d+)\}/g, (_, index) => numbers[Number(index)] || '');
  }
  if (!translated) return value;
  return (value.match(/^\s*/)?.[0] + translated + value.match(/\s*$/)?.[0]) as T;
}
