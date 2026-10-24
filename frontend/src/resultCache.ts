// Personalized results and session tokens stay in memory, never browser storage.
type Entry = { value: unknown; expires: number; retainUntil: number };
const entries = new Map<string, Entry>();
const pending = new Map<string, Promise<unknown>>();
const limit = 80;

export function resultKey(scope: string | null, kind: string, inputs: unknown) {
  return JSON.stringify([scope, kind, inputs]);
}
export function cachedResult<T>(key: string): T | null {
  const entry = entries.get(key);
  if (!entry || entry.expires <= Date.now()) {
    if (entry && entry.retainUntil <= Date.now()) entries.delete(key);
    return null;
  }
  return entry.value as T;
}
export function lastResult<T>(key: string): T | null {
  const entry = entries.get(key);
  if (!entry || entry.retainUntil <= Date.now()) { entries.delete(key); return null; }
  return entry.value as T;
}
export function rememberResult<T>(key: string, value: T, ttl = 3600000): T {
  entries.delete(key);
  entries.set(key, { value, expires: Date.now() + ttl, retainUntil: Date.now() + Math.max(ttl, 3600000) });
  while (entries.size > limit) entries.delete(entries.keys().next().value!);
  return value;
}
export function clearResults() { entries.clear(); pending.clear(); generation++; }
let generation = 0;
export async function reuseResult<T>(key: string, load: () => Promise<T>, ttl: number | ((value: T) => number) = 3600000): Promise<T> {
  const cached = cachedResult<T>(key);
  if (cached !== null) return cached;
  const existing = pending.get(key);
  if (existing) return existing as Promise<T>;
  const started = generation;
  const work = load().then(value => {
    if (started === generation) rememberResult(key, value, typeof ttl === 'function' ? ttl(value) : ttl);
    return value;
  });
  pending.set(key, work);
  try { return await work; }
  finally { if (pending.get(key) === work) pending.delete(key); }
}
