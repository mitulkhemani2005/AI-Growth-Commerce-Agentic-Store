import { test } from 'node:test';
import assert from 'node:assert/strict';
import handler from '../api/backend.js';

function response() {
  return {
    headers: {},
    setHeader(k, v) { this.headers[k] = v; },
    status(code) { this.code = code; return this; },
    send(body) { this.body = body; return this; },
    json(body) { this.body = body; return this; },
  };
}

test('proxy preserves queries and owner tokens and skips the ngrok browser warning', async t => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url.pathname, '/api/cart');
    assert.equal(url.search, '?user_id=user_alex');
    assert.equal(options.headers['ngrok-skip-browser-warning'], 'true');
    assert.equal(options.headers.authorization, 'Bearer owner-token');
    return Response.json({ items: [] });
  });
  const res = response();
  await handler({ url: '/api/cart?user_id=user_alex', query: { __nova_path: 'api/cart' }, method: 'GET', headers: { authorization: 'Bearer owner-token' } }, res);
  assert.equal(res.code, 200);
  assert.deepEqual(JSON.parse(res.body), { items: [] });
});

test('proxy forwards checkout JSON and backend validation failures', async t => {
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), { quantity: -1 });
    return Response.json({ detail: 'Invalid quantity' }, { status: 422 });
  });
  const res = response();
  await handler({ url: '/api/cart/add', method: 'POST', headers: { 'content-type': 'application/json' }, body: { quantity: -1 } }, res);
  assert.equal(res.code, 422);
});

test('proxy preserves binary image responses', async t => {
  const bytes = Uint8Array.of(0, 127, 255);
  t.mock.method(globalThis, 'fetch', async () => new Response(bytes, { headers: { 'content-type': 'image/png' } }));
  const res = response();
  await handler({ url: '/api/backend?__nova_path=static/images/item.png', method: 'GET', headers: {} }, res);
  assert.equal(res.headers['Content-Type'], 'image/png');
  assert.deepEqual([...res.body], [...bytes]);
});

test('proxy reports tunnel failures and rejects paths outside API/assets', async t => {
  let called = false;
  t.mock.method(globalThis, 'fetch', async () => { called = true; throw new Error('offline'); });
  const rejected = response();
  await handler({ url: '/api/backend?__nova_path=api/%2e%2e/secret', method: 'GET', headers: {} }, rejected);
  assert.equal(rejected.code, 400);
  assert.equal(called, false);
  const offline = response();
  await handler({ url: '/api/health', method: 'GET', headers: {} }, offline);
  assert.equal(offline.code, 502);
  assert.match(offline.body.detail, /unreachable/);
});
