import { test } from 'node:test';
import assert from 'node:assert/strict';
import { api } from '../src/api/client.js';

test('uses same-origin URLs and deduplicates concurrent reads', async () => {
  let calls = 0;
  globalThis.fetch = async (url) => {
    calls++;
    assert.equal(url, '/api/inventory');
    await new Promise(resolve => setTimeout(resolve, 5));
    return Response.json({ products: [] });
  };
  const results = await Promise.all([api.getInventory(), api.getInventory()]);
  assert.equal(calls, 1);
  assert.deepEqual(results[0], { products: [] });
});

test('encodes customer IDs and sends autopay as a JSON body', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/payment/agent-autopay');
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), { user_id: 'user one&two', shipping_address: 'Test address' });
    return Response.json({ success: true });
  };
  assert.equal((await api.agentAutonomousPay('user one&two', 'Test address')).success, true);
});

test('formats FastAPI validation errors as readable messages', async () => {
  globalThis.fetch = async () => Response.json({ detail: [{ loc: ['body', 'quantity'], msg: 'Must be positive' }] }, { status: 422 });
  await assert.rejects(api.addToCart('test', 'prod_001', -1), /quantity: Must be positive/);
});

test('does not cache failed requests', async () => {
  globalThis.fetch = async () => Response.json({ detail: 'Unavailable' }, { status: 503 });
  await assert.rejects(api.getHealth(), /Unavailable/);
  globalThis.fetch = async () => Response.json({ status: 'ok' });
  assert.equal((await api.getHealth()).status, 'ok');
});

test('reports an HTML warning page instead of treating it as API data', async () => {
  globalThis.fetch = async () => new Response('<html>ngrok warning</html>', { headers: { 'content-type': 'text/html' } });
  await assert.rejects(api.getHealth(), /non-JSON response/);
});
