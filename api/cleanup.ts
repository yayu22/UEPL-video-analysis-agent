// Vercel Node function (only used in blob upload mode) — deletes a blob after the
// backend has analysed it, so uploaded videos are never kept. Best-effort: uses
// BLOB_READ_WRITE_TOKEN from the env automatically.
import { del } from '@vercel/blob';

export default async function handler(request: Request): Promise<Response> {
  try {
    const { url } = (await request.json()) as { url?: string };
    if (!url) {
      return new Response(JSON.stringify({ error: 'url required' }), {
        status: 400,
        headers: { 'content-type': 'application/json' },
      });
    }
    await del(url);
    return new Response(JSON.stringify({ deleted: true }), {
      headers: { 'content-type': 'application/json' },
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: (error as Error).message }), {
      status: 400,
      headers: { 'content-type': 'application/json' },
    });
  }
}
