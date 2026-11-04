import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  citationLinks,
  newTurnBody,
  parseSseChunk,
  streamTurn,
  threadApi,
  threadTitle,
  toConversations,
  turnsToMessages,
} from '../src/chatV2.js';

function sseResponse(...parts) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      parts.forEach((part) => controller.enqueue(encoder.encode(part)));
      controller.close();
    },
  });
  return new Response(body, { status: 200 });
}

const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

test('parseSseChunk reads the event name and its JSON', () => {
  assert.deepEqual(parseSseChunk('event: token\ndata: {"delta":"Chào"}'), {
    event: 'token',
    data: { delta: 'Chào' },
  });
});

test('streamTurn follows a turn across chunk boundaries', async () => {
  const completed = event('turn.completed', { response: 'Chào Senpai.', citations: [] });
  const started = [];
  const tokens = [];

  const result = await streamTurn({
    base: '/api/v2',
    accessToken: 't',
    body: {},
    onStarted: (data) => started.push(data.thread_id),
    onToken: (delta) => tokens.push(delta),
    fetchImpl: async () =>
      sseResponse(
        event('turn.started', { thread_id: 'th-1' }),
        event('token', { delta: 'Chào ' }),
        completed.slice(0, 10),
        completed.slice(10),
      ),
  });

  assert.deepEqual(started, ['th-1']);
  assert.deepEqual(tokens, ['Chào ']);
  assert.equal(result.response, 'Chào Senpai.');
});

test('a failed turn resolves with the voice constant', async () => {
  const result = await streamTurn({
    base: '/api/v2',
    accessToken: 't',
    body: {},
    fetchImpl: async () => sseResponse(event('turn.failed', { code: 'LLMError', message: 'Hic.' })),
  });

  assert.equal(result.response, 'Hic.');
  assert.equal(result.status, 'failed');
});

test('a stream with no final event and an HTTP error both throw', async () => {
  const run = (fetchImpl) => streamTurn({ base: '', accessToken: 't', body: {}, fetchImpl });

  await assert.rejects(run(async () => sseResponse(event('token', { delta: 'x' }))));
  await assert.rejects(run(async () => new Response('no', { status: 429 })), /429/);
});

test('every turn gets its own id and only a known thread is sent', () => {
  const first = newTurnBody('a', null);
  const second = newTurnBody('a', 'th-1');

  assert.notEqual(first.turn_id, second.turn_id);
  assert.equal('thread_id' in first, false);
  assert.equal(second.thread_id, 'th-1');
});

test('threadApi sends the token and handles an empty delete response', async () => {
  const calls = [];
  const api = threadApi('/api/v2', 'secret', async (url, options) => {
    calls.push([url, options.method, options.headers.authorization]);
    return new Response(null, { status: 204 });
  });

  assert.equal(await api.remove('th-1'), null);
  assert.deepEqual(calls, [['/api/v2/threads/th-1', 'DELETE', 'Bearer secret']]);
});

test('threadApi rejects on an error status', async () => {
  const api = threadApi('/api/v2', 't', async () => new Response('{}', { status: 404 }));

  await assert.rejects(api.turns('th-1'), /404/);
});

test('thread titles are short and untitled threads get the fallback', () => {
  assert.equal(threadTitle('ngắn'), 'ngắn');
  assert.equal(threadTitle('x'.repeat(30)), `${'x'.repeat(22)}...`);
  assert.deepEqual(toConversations([{ id: 'a', title: null }], 'Mới'), [{ id: 'a', title: 'Mới' }]);
});

test('turns become messages, and an empty thread shows the greeting', () => {
  const greeting = { role: 'chisa', content: 'Chào' };
  const citations = [{ title_or_url: 'https://w/P' }];

  assert.deepEqual(turnsToMessages([], greeting), [greeting]);
  assert.deepEqual(turnsToMessages([{ question: 'Q', answer: 'A', citations }], greeting), [
    { role: 'user', content: 'Q' },
    { role: 'chisa', content: 'A', citations },
  ]);
});

test('citation links are unique, readable and only ever web pages', () => {
  const links = citationLinks([
    { title_or_url: 'https://wutheringwaves.fandom.com/wiki/Tacet_Field' },
    { title_or_url: 'https://wutheringwaves.fandom.com/wiki/Tacet_Field' },
    { title_or_url: 'javascript:alert(1)' },
    { title_or_url: 'kb:v1:quests:1' },
  ]);

  assert.deepEqual(links, [
    {
      href: 'https://wutheringwaves.fandom.com/wiki/Tacet_Field',
      label: 'Tacet Field',
    },
  ]);
  assert.deepEqual(citationLinks(undefined), []);
});
