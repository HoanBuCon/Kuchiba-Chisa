// Controlled-beta decision: Public Bot, no guild/channel allowlist. The bot must work in
// arbitrary guilds and in DMs, while privileged commands stay permission-gated.
import assert from 'node:assert/strict';
import test from 'node:test';

// An unrelated value proves no channel allowlist is consulted.
process.env.DISCORD_ALLOWED_CHANNEL_IDS = '111111111111111111';

const { execute: onMessage } = await import('../src/events/messageCreate.js');
const clear = await import('../src/commands/clear.js');

function fakeClient({ channelSettings = new Map() } = {}) {
  const asked = [];
  const mapped = [];
  return {
    asked,
    mapped,
    user: { id: '900000000000000001' },
    commands: new Map([
      ['ask', { executePrefix: async (_c, _m, question, user) => asked.push({ question, user }) }],
    ]),
    services: {
      prefixCommandRunner: {
        prefix: 'c!',
        handleMessage: async () => false,
        isPrefixCommand: () => false,
      },
      guildSettingsCache: channelSettings,
      repositories: {
        users: {
          ensureDiscordUser: async (args) => {
            mapped.push(args);
            return { core_user_id: 'core-user-1' };
          },
        },
      },
      logger: { error: () => {}, warn: () => {}, info: () => {} },
    },
  };
}

function fakeMessage({ guildId = null, channelId = '222222222222222222', content = 'chào Chisa' } = {}) {
  return {
    author: { id: '333333333333333333', bot: false, username: 'senpai', globalName: 'Senpai' },
    content,
    channelId,
    guildId,
    guild: guildId ? { members: { cache: new Map() } } : null,
    attachments: new Map(),
    mentions: { users: new Map() },
    reference: null,
  };
}

test('DMs from any Discord user are answered (no allowlist)', async () => {
  const client = fakeClient();
  await onMessage(client, fakeMessage());
  assert.equal(client.asked.length, 1);
  assert.equal(client.mapped[0].discordGuildId, 'DM');
});

test('a configured channel in an arbitrary guild is answered (no guild allowlist)', async () => {
  const channelId = '444444444444444444';
  const client = fakeClient({ channelSettings: new Map([[channelId, { mode: 'semi-private' }]]) });
  await onMessage(client, fakeMessage({ guildId: '555555555555555555', channelId }));
  assert.equal(client.asked.length, 1);
  assert.equal(client.mapped[0].discordGuildId, '555555555555555555');
});

test('unconfigured guild channels stay silent (existing setup model, not an allowlist)', async () => {
  const client = fakeClient();
  await onMessage(client, fakeMessage({ guildId: '555555555555555555' }));
  assert.equal(client.asked.length, 0);
});

test('Discord identity is per (user, guild) mapping, never a web account id', async () => {
  const client = fakeClient();
  await onMessage(client, fakeMessage());
  const mapping = client.mapped[0];
  assert.deepEqual(Object.keys(mapping).sort(), [
    'discordGuildId',
    'discordUserGlobalName',
    'discordUserId',
    'discordUserName',
    'discordUserTag',
  ]);
});

function fakeInteraction({ flags = [], scope = 'all', mode = 'private' } = {}) {
  const replies = [];
  return {
    replies,
    guildId: '555555555555555555',
    channelId: '444444444444444444',
    user: { id: '333333333333333333' },
    member: { permissions: { has: (flag) => flags.includes(flag) }, roles: { cache: new Map() } },
    options: { getString: (name) => ({ mode, scope })[name] ?? null },
    reply: async (payload) => replies.push(payload),
    deferReply: async () => {},
    editReply: async (payload) => replies.push(payload),
  };
}

test('server-wide /clear in an arbitrary guild is denied to ordinary members', async () => {
  let coreCalls = 0;
  const client = {
    services: {
      logger: { info: () => {}, warn: () => {}, error: () => {} },
      rateLimiter: { allow: () => ({ allowed: true }) },
      repositories: {},
      coreRagClient: new Proxy({}, { get: () => async () => { coreCalls += 1; return {}; } }),
    },
  };
  for (const mode of ['nuke', 'private']) {
    const interaction = fakeInteraction({ mode, scope: mode === 'nuke' ? 'self' : 'all' });
    await clear.execute(client, interaction, { core_user_id: 'core-user-1' });
    assert.equal(interaction.replies.length, 1);
    assert.equal(interaction.replies[0].ephemeral, true);
  }
  assert.equal(coreCalls, 0);
});
