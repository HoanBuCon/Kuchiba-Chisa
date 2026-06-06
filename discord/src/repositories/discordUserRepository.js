import { randomUUID } from 'node:crypto';

export class DiscordUserRepository {
  constructor(pool) {
    this.pool = pool;
  }

  async ensureDiscordUser({
    discordUserId,
    discordUserName = null,
    discordUserGlobalName = null,
    discordUserTag = null,
  }) {
    const existing = await this.pool.query(
      'SELECT * FROM discord_users WHERE discord_user_id = $1 LIMIT 1',
      [discordUserId],
    );

    if (existing.rowCount > 0) {
      const current = existing.rows[0];
      const updated = await this.pool.query(
        `UPDATE discord_users
         SET discord_user_name = $2,
             discord_user_global_name = $3,
             discord_user_tag = $4,
             last_seen_at = NOW(),
             updated_at = NOW()
         WHERE discord_user_id = $1
         RETURNING *`,
        [discordUserId, discordUserName, discordUserGlobalName, discordUserTag],
      );
      return updated.rows[0] ?? current;
    }

    const coreUserId = randomUUID();
    const inserted = await this.pool.query(
      `INSERT INTO discord_users (
         discord_user_id,
         core_user_id,
         discord_user_name,
         discord_user_global_name,
         discord_user_tag,
         first_seen_at,
         last_seen_at,
         created_at,
         updated_at
       ) VALUES ($1, $2, $3, $4, $5, NOW(), NOW(), NOW(), NOW())
       RETURNING *`,
      [discordUserId, coreUserId, discordUserName, discordUserGlobalName, discordUserTag],
    );

    return inserted.rows[0];
  }

  async markCleared(coreUserId) {
    await this.pool.query(
      `UPDATE discord_users
       SET last_cleared_at = NOW(),
           updated_at = NOW()
       WHERE core_user_id = $1`,
      [coreUserId],
    );
  }
}
