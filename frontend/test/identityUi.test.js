import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  loginProviders,
  linkableProviders,
  unlinkIdentity,
  unlinkErrorMessage,
  oauthRedirectNotice,
} from '../src/auth.js';
import { entityImage, streamTurn, turnNotice } from '../src/chatV2.js';

test('Discord login is offered only when the server enables it', () => {
  assert.deepEqual(loginProviders({ google: true, discord: false }).map((p) => p.id), ['google']);
  assert.deepEqual(loginProviders({ google: true, discord: true }).map((p) => p.id), ['google', 'discord']);
  assert.deepEqual(loginProviders({ google: false }).map((p) => p.id), []);
  assert.deepEqual(loginProviders(null), []);
});

test('only enabled and not yet linked providers can be linked', () => {
  const caps = { google: true, discord: true };
  assert.deepEqual(linkableProviders(caps, ['google']).map((p) => p.id), ['discord']);
  assert.deepEqual(linkableProviders({ google: true, discord: false }, ['google']), []);
});

test('unlink sends the bearer token and the client header', async () => {
  let seen;
  const summary = { email: 'a@b.c', providers: ['google'] };
  const result = await unlinkIdentity('tok', 'discord', async (url, init) => {
    seen = { url, init };
    return new Response(JSON.stringify(summary), { status: 200 });
  });
  assert.match(seen.url, /\/auth\/identities\/discord$/);
  assert.equal(seen.init.method, 'DELETE');
  assert.equal(seen.init.headers.authorization, 'Bearer tok');
  assert.equal(seen.init.headers['X-Chisa-Client'], 'web');
  assert.deepEqual(result, summary);
});

test('unlinking the last login method shows a Vietnamese error', async () => {
  const fetchImpl = async () =>
    new Response(JSON.stringify({ detail: 'Cannot unlink' }), { status: 409 });
  await assert.rejects(
    () => unlinkIdentity('tok', 'google', fetchImpl),
    (error) => {
      assert.equal(error.status, 409);
      assert.match(error.message, /phương thức đăng nhập cuối/);
      return true;
    },
  );
});

test('unlink errors map to Vietnamese messages by status', () => {
  assert.match(unlinkErrorMessage(404, 'discord'), /chưa được liên kết/);
  assert.match(unlinkErrorMessage(401), /đăng nhập lại/);
  assert.match(unlinkErrorMessage(500), /Không thể huỷ liên kết/);
});

test('OAuth redirect names the provider and keeps error text provider neutral', () => {
  assert.match(oauthRedirectNotice({ auth: 'discord' }).text, /Discord/);
  assert.equal(oauthRedirectNotice({ auth: 'discord' }).type, 'success');
  const error = oauthRedirectNotice({ auth_error: 'link_required' });
  assert.equal(error.type, 'error');
  assert.doesNotMatch(error.text, /Google/);
  assert.equal(oauthRedirectNotice({}), null);
});

test('turnNotice reads the mode downgrade notice from turn.started', () => {
  assert.equal(turnNotice({ notice: 'Em trả lời bằng Advanced nhé.' }), 'Em trả lời bằng Advanced nhé.');
  assert.equal(turnNotice({ notice: null }), null);
  assert.equal(turnNotice({ notice: '   ' }), null);
  assert.equal(turnNotice(undefined), null);
});

test('streamTurn passes the whole turn.started payload including notice', async () => {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(c) {
      c.enqueue(encoder.encode('event: turn.started\ndata: {"thread_id":"t","notice":"N"}\n\n'));
      c.enqueue(encoder.encode('event: turn.completed\ndata: {"response":"x","citations":[]}\n\n'));
      c.close();
    },
  });
  const started = [];
  await streamTurn({
    base: '/api/v2',
    accessToken: 't',
    body: {},
    onStarted: (d) => started.push(d),
    fetchImpl: async () => new Response(body, { status: 200 }),
  });
  assert.equal(turnNotice(started[0]), 'N');
});

const IMAGE = {
  url: '/api/v2/images/abc?expires=1&sig=s',
  original_url: '/api/v2/images/abc?expires=1&sig=s2&original=1',
  source_page: 'https://wutheringwaves.fandom.com/wiki/File:Chisa.png',
  attribution: 'Ảnh thuộc về Kuro Games.',
};

test('entityImage exposes display url, original link, source page and attribution', () => {
  assert.deepEqual(entityImage(IMAGE, '/api/v2'), {
    src: IMAGE.url,
    originalHref: IMAGE.original_url,
    sourceHref: IMAGE.source_page,
    attribution: IMAGE.attribution,
  });
});

test('entityImage resolves server paths against an absolute API base', () => {
  const image = entityImage(IMAGE, 'https://api.example.test/api/v2');
  assert.equal(image.src, `https://api.example.test${IMAGE.url}`);
  assert.equal(image.originalHref, `https://api.example.test${IMAGE.original_url}`);
});

test('entityImage rejects missing images and non-web schemes', () => {
  assert.equal(entityImage(null, '/api/v2'), null);
  assert.equal(entityImage({ ...IMAGE, url: 'javascript:alert(1)' }, '/api/v2'), null);
  assert.equal(entityImage({ ...IMAGE, original_url: 'data:text/html,x' }, '/api/v2'), null);
  assert.equal(entityImage({ ...IMAGE, source_page: 'javascript:x' }, '/api/v2').sourceHref, null);
});
