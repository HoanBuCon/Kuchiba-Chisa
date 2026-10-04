import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { eraseGuildMembers, isCoreErasureCompleted } from '../src/security/guildErasure.js';

const silentLogger = { warn: () => {}, info: () => {} };

function fakeRepositories(coreUserIds) {
  const deleted = [];
  const pool = {
    query: async (sql, params) => {
      if (sql.startsWith('SELECT core_user_id')) {
        return { rows: coreUserIds.map((id) => ({ core_user_id: id })) };
      }
      if (sql.startsWith('DELETE')) {
        deleted.push({ sql, params });
        return { rowCount: 1 };
      }
      throw new Error(`unexpected SQL: ${sql}`);
    },
  };
  return { repositories: { users: { pool }, interactions: { pool } }, deleted };
}

function fakeCore({ failUser = null, pendingUser = null, communityStatus = 'success' } = {}) {
  const calls = [];
  return {
    calls,
    client: {
      clearCommunityMemory: async (args) => {
        calls.push({ type: 'community', args });
        if (communityStatus === 'throw') throw new Error('core down');
        return { status: communityStatus };
      },
      clearMemory: async (coreUserId, options) => {
        calls.push({ type: 'user', coreUserId, options });
        if (coreUserId === failUser) throw new Error('core 500');
        if (coreUserId === pendingUser) return { status: 'pending_retry' };
        return { status: 'ok' };
      },
    },
  };
}

test('mappings are deleted only after every erasure step completed', async () => {
  const { repositories, deleted } = fakeRepositories(['u1', 'u2']);
  const core = fakeCore();
  const result = await eraseGuildMembers({
    guildId: 'g1', includeCommunity: true, coreRagClient: core.client, repositories, logger: silentLogger,
  });
  assert.deepEqual(result, { complete: true, totalUsers: 2, failedSteps: 0 });
  assert.equal(core.calls.filter((c) => c.type === 'user').length, 2);
  assert.equal(deleted.length, 2);
  const mappingDelete = deleted.find((d) => d.sql.includes('discord_users'));
  // Scoped to the erased users, so members mapped mid-run keep their retry handle.
  assert.deepEqual(mappingDelete.params, ['g1', ['u1', 'u2']]);
});

test('a failed user erasure keeps the Discord mapping for retry', async () => {
  const { repositories, deleted } = fakeRepositories(['u1', 'u2', 'u3']);
  const core = fakeCore({ failUser: 'u2' });
  const result = await eraseGuildMembers({
    guildId: 'g1', includeCommunity: true, coreRagClient: core.client, repositories, logger: silentLogger,
  });
  assert.equal(result.complete, false);
  assert.equal(result.failedSteps, 1);
  // Partial-failure semantics preserved: remaining users are still attempted.
  assert.equal(core.calls.filter((c) => c.type === 'user').length, 3);
  assert.deepEqual(deleted, []);
});

test('pending_retry from Core is not treated as completed', async () => {
  const { repositories, deleted } = fakeRepositories(['u1']);
  const core = fakeCore({ pendingUser: 'u1' });
  const result = await eraseGuildMembers({
    guildId: 'g1', includeCommunity: false, coreRagClient: core.client, repositories, logger: silentLogger,
  });
  assert.equal(result.complete, false);
  assert.deepEqual(deleted, []);
});

test('community erasure failure blocks mapping deletion during nuke', async () => {
  const { repositories, deleted } = fakeRepositories(['u1']);
  const core = fakeCore({ communityStatus: 'throw' });
  const result = await eraseGuildMembers({
    guildId: 'g1', includeCommunity: true, coreRagClient: core.client, repositories, logger: silentLogger,
  });
  assert.equal(result.complete, false);
  assert.deepEqual(deleted, []);
});

test('completion status contract', () => {
  assert.equal(isCoreErasureCompleted({ status: 'ok' }), true);
  assert.equal(isCoreErasureCompleted({ status: 'success' }), true);
  assert.equal(isCoreErasureCompleted({ status: 'pending_retry' }), false);
  assert.equal(isCoreErasureCompleted(null), false);
});

test('clear command never deletes guild mappings outside the guarded helper', () => {
  const source = readFileSync(new URL('../src/commands/clear.js', import.meta.url), 'utf8');
  assert.equal(source.includes('DELETE FROM discord_users'), false);
  assert.equal(source.includes('.catch((err) => {\n            logger.warn({ err, coreUserId }'), false);
  const permissions = readFileSync(new URL('../src/utils/permissions.js', import.meta.url), 'utf8');
  assert.equal(/role\.name/.test(permissions), false);
});
