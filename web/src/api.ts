import { useEffect, useState } from 'react';

export class ApiError extends Error {
  constructor(message: string, public status = 0) { super(message); }
}

export async function requestJSON<T>(url: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try { response = await fetch(url, {cache: 'no-store', ...options}); }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('Cannot reach the local service. Check that it is running, then retry.');
  }
  let body;
  try { body = await response.json(); }
  catch { throw new ApiError('The local service returned an unreadable response. Check that the API and report files are available.', response.status); }
  if (!response.ok) throw new ApiError(typeof body.detail === 'string' ? body.detail : 'The request could not be completed.', response.status);
  return body as T;
}

export function useResource<T>(url: string | null, revision = 0) {
  const [state, setState] = useState<{url: string | null; revision: number; data: T | null; error: string | null; loading: boolean}>(
    {url: null, revision: -1, data: null, error: null, loading: false});
  useEffect(() => {
    const controller = new AbortController();
    setState({url, revision, data: null, error: null, loading: !!url});
    if (url) requestJSON<T>(url, {signal: controller.signal}).then(
      data => { if (!controller.signal.aborted) setState({url, revision, data, error: null, loading: false}); },
      error => { if (!controller.signal.aborted) setState({url, revision, data: null, error: error.message, loading: false}); },
    );
    return () => controller.abort();
  }, [url, revision]);
  // Do not render a previous station's data while a new effect starts.
  return state.url === url && state.revision === revision ? state : {data: null, error: null, loading: !!url};
}

export const query = (path: string, values: {[key: string]: string}) => `/api/${path}?${new URLSearchParams(values)}`;
