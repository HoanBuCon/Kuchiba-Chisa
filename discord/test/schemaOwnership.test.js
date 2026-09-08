import assert from 'node:assert/strict';
import test from 'node:test';

import { GuildSettingsRepository } from '../src/repositories/guildSettingsRepository.js';


test('guild settings repository uses migrated tables without runtime DDL', async () => {
  const calls = [];
  const pool = {
    async query(statement, parameters) {
      calls.push({ statement, parameters });
      return { rows: [] };
    },
  };
  const repository = new GuildSettingsRepository(pool);

  await repository.setChisaChannel('guild-1', 'channel-1', 'owner-1');
  await repository.setClearCutoff('guild-1', 1234);
  await repository.getAllSettings();
  await repository.getAllClearCutoffs();

  assert.equal(calls.length, 4);
  for (const { statement } of calls) {
    assert.doesNotMatch(statement, /\b(?:CREATE|ALTER|DROP)\s+(?:TABLE|INDEX)\b/i);
  }
});
