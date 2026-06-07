import { randomUUID } from 'node:crypto';

export class DiscordUserRepository {
  constructor(pool) {
    this.pool = pool;
  }

  async ensureDiscordUser({
    discordUserId,
    discordGuildId = 'DM',
    discordUserName = null,
    discordUserGlobalName = null,
    discordUserTag = null,
  }) {
    const guildId = discordGuildId || 'DM';
    const existing = await this.pool.query(
      'SELECT * FROM discord_users WHERE discord_user_id = $1 AND discord_guild_id = $2 LIMIT 1',
      [discordUserId, guildId],
    );

    if (existing.rowCount > 0) {
      const current = existing.rows[0];
      const updated = await this.pool.query(
        `UPDATE discord_users
         SET discord_user_name = $3,
             discord_user_global_name = $4,
             discord_user_tag = $5,
             last_seen_at = NOW(),
             updated_at = NOW()
         WHERE discord_user_id = $1 AND discord_guild_id = $2
         RETURNING *`,
        [discordUserId, guildId, discordUserName, discordUserGlobalName, discordUserTag],
      );
      return updated.rows[0] ?? current;
    }

    const coreUserId = randomUUID();
    const inserted = await this.pool.query(
      `INSERT INTO discord_users (
         discord_user_id,
         discord_guild_id,
         core_user_id,
         discord_user_name,
         discord_user_global_name,
         discord_user_tag,
         first_seen_at,
         last_seen_at,
         created_at,
         updated_at
       ) VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW(), NOW(), NOW())
       RETURNING *`,
      [discordUserId, guildId, coreUserId, discordUserName, discordUserGlobalName, discordUserTag],
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
