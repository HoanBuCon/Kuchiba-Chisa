export class GuildSettingsRepository {
  constructor(pool) {
    this.pool = pool;
  }

  async setChisaChannel(guildId, channelId, setupByUserId, mode = 'private') {
    await this.pool.query(
      `INSERT INTO guild_settings (discord_guild_id, chisa_channel_id, setup_by_user_id, mode, updated_at)
       VALUES ($1, $2, $3, $4, NOW())
       ON CONFLICT (chisa_channel_id)
       DO UPDATE SET setup_by_user_id = $3, mode = $4, updated_at = NOW()`,
      [guildId, channelId, setupByUserId, mode || 'private']
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
    const res = await this.pool.query("SELECT discord_guild_id, chisa_channel_id, COALESCE(mode, 'private') AS mode FROM guild_settings");
    return res.rows;
  }
}
