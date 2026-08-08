/**
 * NONPROFIT.SI — Anthropic proxy.
 *
 * Runs on Vercel Edge and Netlify Functions v2. The API key stays on the
 * server: it is read from the ANTHROPIC_API_KEY environment variable and
 * never reaches the browser.
 *
 * Set it in Vercel:  Settings -> Environment Variables -> ANTHROPIC_API_KEY
 * Then redeploy.
 */

export const config = { runtime: 'edge' };

const MODEL = 'claude-sonnet-5';
const MAX_TOKENS_CEILING = 2048;

export default async function handler(req) {
  // Health probe used by the client to decide proxy vs. local-key mode.
  if (req.method === 'OPTIONS' || req.method === 'HEAD') {
    return new Response(null, { status: 204, headers: { allow: 'POST, OPTIONS' } });
  }
  if (req.method !== 'POST') {
    return new Response('Method not allowed', { status: 405, headers: { allow: 'POST, OPTIONS' } });
  }

  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) {
    return new Response(
      'ANTHROPIC_API_KEY is not set on this deployment. Add it in your host’s environment variables and redeploy.',
      { status: 500 }
    );
  }

  let payload;
  try {
    payload = await req.json();
  } catch {
    return new Response('Malformed JSON body', { status: 400 });
  }

  const { messages, system } = payload || {};
  if (!Array.isArray(messages) || messages.length === 0) {
    return new Response('messages[] is required', { status: 400 });
  }

  const max_tokens = Math.min(Number(payload.max_tokens) || 1400, MAX_TOKENS_CEILING);

  // Only forward the fields we expect. Nothing from the client selects a model.
  const clean = messages.slice(-20).map((m) => ({
    role: m.role === 'assistant' ? 'assistant' : 'user',
    content: String(m.content ?? '').slice(0, 8000),
  }));

  let upstream;
  try {
    upstream = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens,
        system: typeof system === 'string' ? system.slice(0, 12000) : undefined,
        messages: clean,
        stream: true,
      }),
    });
  } catch (err) {
    return new Response('Upstream unreachable: ' + (err?.message || 'network error'), { status: 502 });
  }

  if (!upstream.ok) {
    const detail = await upstream.text().catch(() => '');
    return new Response(detail.slice(0, 500) || `Anthropic returned ${upstream.status}`, {
      status: upstream.status,
    });
  }

  return new Response(upstream.body, {
    headers: {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-cache, no-transform',
      connection: 'keep-alive',
      'x-accel-buffering': 'no',
    },
  });
}
