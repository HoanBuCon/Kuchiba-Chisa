import assert from 'node:assert/strict';
import test from 'node:test';

import { isGuildModeratorOrAdmin, parseModeratorRoleIds } from '../src/utils/permissions.js';

const member = ({ flags = [], roles = [] } = {}) => ({
  permissions: { has: (flag) => flags.includes(flag) },
  roles: {
    cache: {
      has: (id) => roles.some((role) => role.id === id),
      some: (fn) => roles.some(fn),
    },
  },
});

const ALLOWED_ROLE = '123456789012345678';

test('Administrator and ManageGuild permission flags grant moderation', () => {
  assert.equal(isGuildModeratorOrAdmin(member({ flags: ['Administrator'] }), { moderatorRoleIds: new Set() }), true);
  assert.equal(isGuildModeratorOrAdmin(member({ flags: ['ManageGuild'] }), { moderatorRoleIds: new Set() }), true);
});

test('role NAMES never grant moderation (B-3 regression)', () => {
  for (const name of ['Moderator', 'mod', 'Admin', 'Model', 'Modern Art', 'admin-wannabe']) {
    const candidate = member({ roles: [{ id: '999999999999999999', name }] });
    assert.equal(
      isGuildModeratorOrAdmin(candidate, { moderatorRoleIds: new Set() }),
      false,
      `role named "${name}" must not grant moderation`,
    );
  }
});

test('only explicitly allowlisted role IDs grant moderation', () => {
  const allowlist = new Set([ALLOWED_ROLE]);
  assert.equal(isGuildModeratorOrAdmin(member({ roles: [{ id: ALLOWED_ROLE, name: 'anything' }] }), { moderatorRoleIds: allowlist }), true);
  assert.equal(isGuildModeratorOrAdmin(member({ roles: [{ id: '222222222222222222', name: 'Moderator' }] }), { moderatorRoleIds: allowlist }), false);
});

test('missing member or permissions fails closed', () => {
  assert.equal(isGuildModeratorOrAdmin(null), false);
  assert.equal(isGuildModeratorOrAdmin({}, { moderatorRoleIds: new Set([ALLOWED_ROLE]) }), false);
});

test('role allowlist parser accepts only Discord snowflakes', () => {
  assert.deepEqual(
    [...parseModeratorRoleIds(` ${ALLOWED_ROLE}, mod, 12, ${ALLOWED_ROLE}x ,234567890123456789`)],
    [ALLOWED_ROLE, '234567890123456789'],
  );
  assert.equal(parseModeratorRoleIds('').size, 0);
  assert.equal(parseModeratorRoleIds(undefined).size, 0);
});
