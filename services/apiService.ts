import { AnalysisResponse, VideoType } from '../types';
import { API_BASE } from '../constants';

/**
 * Send a video to the backend for driver-behaviour + equipment analysis.
 * The Gemini key lives on the server; the browser only talks to our API.
 */
export async function analyzeVideo(file: File, camera: VideoType): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('file', file);
  form.append('camera', camera);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/analyze`, { method: 'POST', body: form });
  } catch (e) {
    throw new Error(
      `Could not reach the analysis backend at ${API_BASE}. Is it running? (uvicorn api:app --port 8000)`
    );
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(`Analysis failed: ${detail}`);
  }

  return (await res.json()) as AnalysisResponse;
}
