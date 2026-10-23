export const apiUrl = (path: string) => `/api/v2${path}`;

// Tokens stay in memory in App, never in localStorage or cookies.
export async function request<T>(path: string, token: string | null, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 210000);
  try {
    const headers = new Headers(options.headers);
    if (token) headers.set('X-Session-ID', token);
    const response = await fetch(apiUrl(path), { ...options, headers, signal: controller.signal });
    const payload = response.status === 204 ? null : await response.json();
    if (!response.ok) {
      const detail = payload?.detail;
      throw new Error(typeof detail === 'string' ? detail : detail?.message || "That didn't go through. Please try again.");
    }
    return payload as T;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw new Error('This is taking longer than expected. Try a smaller file or try again.');
    if (error instanceof TypeError) throw new Error("We couldn't reach the app. Check your connection and try again.");
    throw error;
  } finally { window.clearTimeout(timer); }
}
export const json = (method: string, body: unknown): RequestInit => ({
  method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});
