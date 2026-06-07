export class InteractionRepository {
  constructor(pool) {
    this.pool = pool;
  }

  async createInteraction({
    discordUserId,
    coreUserId,
    discordUserName = null,
    discordUserGlobalName = null,
    discordUserTag = null,
    discordGuildId = null,
    discordGuildName = null,
    discordChannelId = null,
    discordChannelName = null,
    discordMessageId = null,
    commandName,
    userMessage,
    status = 'pending',
    metadata = {},
  }) {
    const result = await this.pool.query(
      `INSERT INTO discord_interactions (
         discord_user_id,
         core_user_id,
         discord_user_name,
         discord_user_global_name,
         discord_user_tag,
         discord_guild_id,
         discord_guild_name,
         discord_channel_id,
         discord_channel_name,
         discord_message_id,
         command_name,
         user_message,
         status,
         metadata,
         created_at,
         updated_at
       ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,NOW(),NOW())
       RETURNING id`,
      [
        discordUserId,
        coreUserId,
        discordUserName,
        discordUserGlobalName,
        discordUserTag,
        discordGuildId,
        discordGuildName,
        discordChannelId,
        discordChannelName,
        discordMessageId,
        commandName,
        userMessage,
        status,
        JSON.stringify(metadata),
      ],
    );

    return result.rows[0].id;
  }

  async markCoreRequest(id) {
    await this.pool.query(
      `UPDATE discord_interactions
       SET status = 'calling_core',
           core_request_at = NOW(),
           updated_at = NOW()
       WHERE id = $1`,
      [id],
    );
  }

  async markSuccess(id, { assistantMessage, metadata = {} }) {
    await this.pool.query(
      `UPDATE discord_interactions
       SET status = 'success',
           assistant_message = $2,
           core_response_at = NOW(),
           metadata = $3::jsonb,
           updated_at = NOW()
       WHERE id = $1`,
      [id, assistantMessage, JSON.stringify(metadata)],
    );
  }

  async markFailure(id, errorMessage, status = 'failed') {
    await this.pool.query(
      `UPDATE discord_interactions
       SET status = $2,
           error_message = $3,
           core_response_at = NOW(),
           updated_at = NOW()
       WHERE id = $1`,
      [id, status, errorMessage],
    );
  }

  async clearUserInteractions(coreUserId, preserveInteractionId = null) {
    if (preserveInteractionId === null) {
      await this.pool.query(
        'DELETE FROM discord_interactions WHERE core_user_id = $1',
        [coreUserId],
      );
      return;
    }

    await this.pool.query(
      'DELETE FROM discord_interactions WHERE core_user_id = $1 AND id <> $2',
      [coreUserId, preserveInteractionId],
    );
  }

  async createFromContext(context, { coreUserId, commandName, userMessage, status = 'pending', metadata = {} }) {
    const isInteraction = typeof context.editReply === 'function';
    const user = isInteraction ? context.user : context.author;
    const channel = context.channel;
    const guild = context.guild;

    return this.createInteraction({
      discordUserId: user.id,
      coreUserId,
      discordUserName: user.username,
      discordUserGlobalName: user.globalName ?? null,
      discordUserTag: user.tag ?? user.username,
      discordGuildId: context.guildId ?? null,
      discordGuildName: guild?.name ?? null,
      discordChannelId: context.channelId,
      discordChannelName: channel?.name ?? null,
      discordMessageId: context.id,
      commandName,
      userMessage,
      status,
      metadata,
    });
  }
}
