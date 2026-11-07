// Chat through /api/v2: stays behind its flag, is idempotent, and leaves v1-only messages alone.
import assert from 'node:assert/strict';
import test from 'node:test';

const { CoreRagClient, discordTurnId, parseTurnEvents } = await import(
  '../src/services/coreRagClient.js'
);

const sse = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
const COMPLETED = sse('turn.completed', { response: 'Dạ Senpai.', emotions: { joy: 0.5 } });

function clientWith(body, { enabled = true } = {}) {
  const client = new CoreRagClient();
  client.chatV2Enabled = enabled;
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    return new Response(body, { status: 200 });
  };
  return { client, calls, restore: () => { globalThis.fetch = original; } };
}

const ASK = { coreUserId: 'u1', guildId: 'g1', channelId: 'c1', message: 'Chào em', username: 'n' };

test('the same Discord message always gets the same valid turn id', () => {
  const id = discordTurnId('123456');

  assert.equal(id, discordTurnId('123456'));
  assert.notEqual(id, discordTurnId('123457'));
  assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test('a message without an id still gets a valid unique turn id', () => {
  assert.notEqual(discordTurnId(null), discordTurnId(null));
});

test('turn events are parsed across LF and CRLF', () => {
  const events = parseTurnEvents(`event: token\r\ndata: {"delta":"a"}\r\n\r\n${COMPLETED}`);

  assert.deepEqual(events.map((item) => item.event), ['token', 'turn.completed']);
});

test('with the flag on, a plain message goes to v2 and returns the final reply', async (t) => {
  const { client, calls, restore } = clientWith(COMPLETED);
  t.after(restore);

  const result = await client.ask({ ...ASK, messageId: '42' });

  assert.match(calls[0].url, /\/api\/v2\/chat\/turns$/);
  assert.equal(calls[0].body.turn_id, discordTurnId('42'));
  assert.equal(result.response, 'Dạ Senpai.');
  assert.deepEqual(result.emotions, { joy: 0.5 });
});

test('with the flag off, messages stay on v1', async (t) => {
  const { client, calls, restore } = clientWith('{"response":"v1"}', { enabled: false });
  t.after(restore);

  const result = await client.ask(ASK);

  assert.match(calls[0].url, /\/api\/v1\/chat$/);
  assert.equal(result.response, 'v1');
});

test('messages with images or a reply reference stay on v1', () => {
  const client = new CoreRagClient();
  client.chatV2Enabled = true;

  assert.equal(client.usesChatV2({ images: ['a.png'] }), false);
  assert.equal(client.usesChatV2({ isEphemeralReference: true }), false);
  assert.equal(client.usesChatV2({}), true);
});

test('a failed turn returns its voice constant', async (t) => {
  const { client, restore } = clientWith(sse('turn.failed', { code: 'LLMError', message: 'Hic.' }));
  t.after(restore);

  assert.equal((await client.ask(ASK)).response, 'Hic.');
});

test('a stream with no final event throws', async (t) => {
  const { client, restore } = clientWith(sse('token', { delta: 'x' }));
  t.after(restore);

  await assert.rejects(client.ask(ASK), /without a final event/);
});
