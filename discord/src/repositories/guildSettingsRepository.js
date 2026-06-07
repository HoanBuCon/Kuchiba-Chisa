export class GuildSettingsRepository {
  constructor(pool) {
    this.pool = pool;
  }

  async setChisaChannel(guildId, channelId, setupByUserId) {
    await this.pool.query(
      `INSERT INTO guild_settings (discord_guild_id, chisa_channel_id, setup_by_user_id, updated_at)
       VALUES ($1, $2, $3, NOW())
       ON CONFLICT (chisa_channel_id)
       DO UPDATE SET setup_by_user_id = $3, updated_at = NOW()`,
      [guildId, channelId, setupByUserId]
    );
  }

  async disableChisaChannel(channelId) {
    await this.pool.query(
      `DELETE FROM guild_settings
       WHERE chisa_channel_id = $1`,
      [channelId]
    );
  }

  async disableAllChannels(guildId) {
    await this.pool.query(
      `DELETE FROM guild_settings
       WHERE discord_guild_id = $1`,
      [guildId]
    );
  }

  async getAllSettings() {
    const res = await this.pool.query('SELECT discord_guild_id, chisa_channel_id FROM guild_settings');
    return res.rows;
  }
}
