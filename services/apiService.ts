import { AnalysisResponse, VideoType } from '../types';
import { API_BASE, UPLOAD_MODE, BLOB_UPLOAD_ROUTE, BLOB_DELETE_ROUTE } from '../constants';

async function errorDetail(res: Response): Promise<string> {
  let detail = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (body?.detail) detail = body.detail;
    else if (body?.error) detail = body.error;
  } catch {
    /* non-JSON error body */
  }
  return detail;
}

/**
 * DIRECT mode — POST the video file straight to the backend.
 * Best for Cloud Run / any host that accepts large request bodies.
 */
async function analyzeDirect(file: File, camera: VideoType): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('file', file);
  form.append('camera', camera);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/analyze`, { method: 'POST', body: form });
  } catch {
    throw new Error(`Could not reach the analysis backend at ${API_BASE}. Is it running?`);
  }
  if (!res.ok) throw new Error(`Analysis failed: ${await errorDetail(res)}`);
  return (await res.json()) as AnalysisResponse;
}

/**
 * BLOB mode — upload the clip to Vercel Blob, send only the URL to the backend,
 * then DELETE the blob. Required on Vercel (4.5 MB function body cap). The blob is
 * transient: it is removed after analysis whether it succeeds or fails, so nothing
 * is kept.
 */
async function analyzeViaBlob(file: File, camera: VideoType): Promise<AnalysisResponse> {
  const { upload } = await import('@vercel/blob/client');
  const blob = await upload(file.name, file, {
    access: 'public',
    handleUploadUrl: BLOB_UPLOAD_ROUTE,
    contentType: file.type || undefined,
  });

  try {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/api/analyze-url`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ video_url: blob.url, camera }),
      });
    } catch {
      throw new Error(`Could not reach the analysis backend at ${API_BASE}. Is it running?`);
    }
    if (!res.ok) throw new Error(`Analysis failed: ${await errorDetail(res)}`);
    return (await res.json()) as AnalysisResponse;
  } finally {
    // Keep nothing — delete the uploaded blob (best-effort).
    try {
      await fetch(BLOB_DELETE_ROUTE, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ url: blob.url }),
      });
    } catch {
      /* best-effort cleanup; the blob is unguessable and can be lifecycle-purged too */
    }
  }
}

/** Analyze a video, using whichever ingestion mode is configured (VITE_UPLOAD_MODE). */
export async function analyzeVideo(file: File, camera: VideoType): Promise<AnalysisResponse> {
  return UPLOAD_MODE === 'blob' ? analyzeViaBlob(file, camera) : analyzeDirect(file, camera);
}
