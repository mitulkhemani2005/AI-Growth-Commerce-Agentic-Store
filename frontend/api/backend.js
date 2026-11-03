// Keep browser traffic on the Vercel origin and bypass ngrok's HTML warning.
export default async function handler(request, response) {
  const incoming = new URL(request.url, 'http://nova.local');
  const route = request.query?.__nova_path || incoming.searchParams.get('__nova_path') || incoming.pathname.slice(1);
  let decoded;
  try {
    decoded = decodeURIComponent(route);
  } catch {
    return response.status(400).json({ detail: 'Invalid backend path.' });
  }
  if (!/^(api|static)\//.test(decoded) || /[\\?#]/.test(decoded) || decoded.split('/').some(part => part === '..' || part === '.')) {
    return response.status(400).json({ detail: 'Invalid backend path.' });
  }

  try {
    const base = process.env.NOVA_BACKEND_URL || process.env.VITE_API_BASE_URL || 'https://frugally-stoneware-paddle.ngrok-free.dev';
    const target = new URL(base);
    target.pathname = '/' + route;
    incoming.searchParams.delete('__nova_path');
    target.search = incoming.searchParams.toString();
    const headers = { 'ngrok-skip-browser-warning': 'true' };
    for (const name of ['authorization', 'content-type', 'accept']) {
      if (request.headers[name]) headers[name] = request.headers[name];
    }
    const options = { method: request.method, headers, signal: AbortSignal.timeout(115000), redirect: 'manual' };
    if (!['GET', 'HEAD'].includes(request.method) && request.body != null) {
      options.body = typeof request.body === 'string' || Buffer.isBuffer(request.body)
        ? request.body : JSON.stringify(request.body);
    }
    const upstream = await fetch(target, options);
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('Content-Type', upstream.headers.get('content-type') || 'application/octet-stream');
    return response.status(upstream.status).send(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    const timeout = ['TimeoutError', 'AbortError'].includes(error.name);
    return response.status(timeout ? 504 : 502).json({
      detail: timeout ? 'Nova backend request timed out.' : 'Nova backend is unreachable. Keep Uvicorn and ngrok running.',
    });
  }
}
