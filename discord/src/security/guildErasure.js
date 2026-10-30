// Guild-wide erasure coordination for `/clear ... scope:all` and `nuke` (B-3).
//
// The Discord mapping (`discord_users`: Discord user ↔ Core user ID) is the only
// handle that lets an operator retry a Core erasure later. It is therefore removed
// only after EVERY mandatory Core erasure step acknowledged completion. Any failure
// or `pending_retry` keeps the mapping (and interaction records) so the command can
// be safely re-run; nothing is reported as fully cleared when it was not.

const COMPLETED_STATUSES = new Set(['ok', 'success', 'completed']);

export function isCoreErasureCompleted(payload) {
  return Boolean(payload && COMPLETED_STATUSES.has(String(payload.status ?? '').toLowerCase()));
}

async function runStep(step, logger, logContext, failures) {
  try {
    const payload = await step();
    if (!isCoreErasureCompleted(payload)) {
      failures.push(logContext.step);
      logger.warn({ ...logContext, status: payload?.status ?? null }, 'Core erasure not completed');
    }
  } catch (err) {
    failures.push(logContext.step);
    logger.warn({ ...logContext, err }, 'Core erasure step failed');
  }
}

/**
 * Erase Core memory for every mapped member of a guild (and optionally the guild's
 * community memory), deleting local mappings only when all steps completed.
 *
 * @returns {Promise<{complete: boolean, totalUsers: number, failedSteps: number}>}
 */
export async function eraseGuildMembers({
  guildId,
  includeCommunity,
  coreRagClient,
  repositories,
  logger,
}) {
  const failures = [];

  if (includeCommunity) {
    await runStep(
      () => coreRagClient.clearCommunityMemory({ guildId, scope: 'all' }),
      logger,
      { guildId, step: 'community' },
      failures,
    );
  }

  const res = await repositories.users.pool.query(
    'SELECT core_user_id FROM discord_users WHERE discord_guild_id = $1',
    [guildId],
  );
  const coreUserIds = res.rows.map((row) => row.core_user_id);
  for (const coreUserId of coreUserIds) {
    await runStep(
      () => coreRagClient.clearMemory(coreUserId, { guildId, scopes: ['chat:clear:any'] }),
      logger,
      { guildId, coreUserId, step: 'user' },
      failures,
    );
  }

  const complete = failures.length === 0;
  if (complete) {
    await repositories.interactions.pool.query(
      'DELETE FROM discord_interactions WHERE discord_guild_id = $1',
      [guildId],
    );
    // Only the mappings whose Core memory was erased above; a member mapped while
    // this ran keeps its mapping (and thus its retry handle).
    await repositories.users.pool.query(
      'DELETE FROM discord_users WHERE discord_guild_id = $1 AND core_user_id = ANY($2::uuid[])',
      [guildId, coreUserIds],
    );
  } else {
    logger.warn(
      { guildId, failedSteps: failures.length, totalUsers: coreUserIds.length },
      'Guild erasure incomplete; Discord mappings retained for retry',
    );
  }

  return { complete, totalUsers: coreUserIds.length, failedSteps: failures.length };
}
