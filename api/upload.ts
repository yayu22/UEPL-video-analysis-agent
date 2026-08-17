// Vercel Node function (only used in blob upload mode) — mints a short-lived client
// token so the browser can upload a video DIRECTLY to Vercel Blob, bypassing the
// 4.5 MB function body limit. Requires the BLOB_READ_WRITE_TOKEN env var, which
// Vercel adds automatically when you connect a Blob store to this project.
//
// This is the "framework=other" handler shape from the Vercel docs.
import { handleUpload, type HandleUploadBody } from '@vercel/blob/client';

export default async function handler(request: Request): Promise<Response> {
  const body = (await request.json()) as HandleUploadBody;
  try {
    const jsonResponse = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async () => ({
        allowedContentTypes: [
          'video/mp4', 'video/quicktime', 'video/webm', 'video/x-msvideo',
          'video/x-matroska', 'video/mpeg', 'video/3gpp', 'video/x-ms-wmv', 'video/x-flv',
        ],
        addRandomSuffix: true,
        maximumSizeInBytes: 600 * 1024 * 1024,
      }),
      // We delete the blob after analysis (see services/apiService.ts), so nothing
      // needs to happen here.
      onUploadCompleted: async () => { /* no-op */ },
    });
    return new Response(JSON.stringify(jsonResponse), {
      headers: { 'content-type': 'application/json' },
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: (error as Error).message }), {
      status: 400,
      headers: { 'content-type': 'application/json' },
    });
  }
}
