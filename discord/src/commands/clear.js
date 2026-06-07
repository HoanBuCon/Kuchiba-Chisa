import { SlashCommandBuilder } from 'discord.js';
import { DEFAULT_COMMANDS } from '../config/constants.js';
import { isGuildModeratorOrAdmin } from '../utils/permissions.js';

export const data = new SlashCommandBuilder()
  .setName(DEFAULT_COMMANDS.clear)
  .setDescription('Xóa memory của Chisa')
  .addStringOption((option) =>
    option
      .setName('scope')
      .setDescription('Chọn phạm vi xóa memory')
      .setRequired(false)
      .addChoices(
        { name: 'Chỉ bản thân (self)', value: 'self' },
        { name: 'Toàn bộ Server (all) - Yêu cầu quyền Admin/Mod', value: 'all' },
      ),
  )
  .setDMPermission(false);

export async function execute(client, interaction, discordUser) {
  const { logger, rateLimiter, repositories, coreRagClient } = client.services;
  const scope = interaction.options.getString('scope') || 'self';
  const guildId = interaction.guildId || 'DM';

  if (scope === 'all') {
    if (!isGuildModeratorOrAdmin(interaction.member)) {
      await interaction.reply({
        content: 'Chỉ Admin hoặc Moderator mới có quyền xóa memory toàn bộ Server.',
        ephemeral: true,
      });
      return;
    }
  }

  const rateKey = `${interaction.user.id}:clear:${scope}`;
  const rate = rateLimiter.allow(rateKey);

  if (!rate.allowed) {
    const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
    await interaction.reply({
      content: `Bạn vừa thực hiện quá nhanh. Hãy chờ khoảng ${waitSeconds}s rồi thử lại.`,
      ephemeral: true,
    });
    return;
  }

  await interaction.deferReply({ ephemeral: true });

  if (scope === 'all') {
    try {
      const res = await repositories.users.pool.query(
        'SELECT core_user_id FROM discord_users WHERE discord_guild_id = $1',
        [guildId]
      );
      const coreUserIds = res.rows.map((row) => row.core_user_id);

      logger.info({ guildId, userCount: coreUserIds.length }, 'Starting server-wide memory clear');
      for (const coreUserId of coreUserIds) {
        await coreRagClient.clearMemory(coreUserId).catch((err) => {
          logger.warn({ err, coreUserId }, 'Failed to clear memory for user in server clear');
        });
      }

      await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE discord_guild_id = $1', [guildId]);
      await repositories.users.pool.query('DELETE FROM discord_users WHERE discord_guild_id = $1', [guildId]);

      logger.info({ guildId }, 'Discord server-wide memory cleared successfully');
      await interaction.editReply({
        content: 'Đã xóa toàn bộ memory của Chisa đối với tất cả thành viên trong Server này.',
      });
    } catch (error) {
      logger.error({ err: error, guildId }, 'Discord server clear failed');
      await interaction.editReply({
        content: 'Không thể xóa memory Server lúc này. Hãy thử lại sau.',
      });
    }
    return;
  }

  // Scope: self
  const interactionId = await repositories.interactions.createFromContext(interaction, {
    coreUserId: discordUser.core_user_id,
    commandName: data.name,
    userMessage: `/clear scope:self`,
    status: 'clearing',
    metadata: { source: 'discord', command: data.name },
  });

  try {
    await coreRagClient.clearMemory(discordUser.core_user_id);
    await repositories.interactions.clearUserInteractions(discordUser.core_user_id, interactionId);
    await repositories.users.markCleared(discordUser.core_user_id);
    await repositories.interactions.markSuccess(interactionId, {
      assistantMessage: 'Memory cleared',
      metadata: { source: 'core-rag', command: data.name },
    });

    logger.info({ userId: interaction.user.id, coreUserId: discordUser.core_user_id }, 'Discord user memory cleared');
    await interaction.editReply({
      content: 'Memory của bạn trên server này đã được xóa. Chisa sẽ bắt đầu lại từ đầu trong lần trò chuyện tiếp theo.',
    });
  } catch (error) {
    logger.error({ err: error, userId: interaction.user.id }, 'Discord /clear self failed');
    await repositories.interactions.markFailure(interactionId, error instanceof Error ? error.message : String(error));
    await interaction.editReply({
      content: 'Không thể xóa memory lúc này. Hãy thử lại sau.',
    });
  }
}

export async function executePrefix(client, message, argsText, discordUser) {
  const { logger, rateLimiter, repositories, coreRagClient } = client.services;
  const args = argsText ? argsText.trim().split(/\s+/) : [];
  const scope = args[0]?.toLowerCase() === 'all' ? 'all' : 'self';
  const guildId = message.guildId || 'DM';

  if (scope === 'all') {
    if (!isGuildModeratorOrAdmin(message.member)) {
      await message.reply('Chỉ Admin hoặc Moderator mới có quyền xóa memory toàn bộ Server.');
      return;
    }
  }

  const rateKey = `${message.author.id}:clear:${scope}`;
  const rate = rateLimiter.allow(rateKey);

  if (!rate.allowed) {
    const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
    await message.reply(`Bạn vừa dùng clear quá nhanh. Hãy chờ khoảng ${waitSeconds}s rồi thử lại.`);
    return;
  }

  await message.channel.sendTyping().catch(() => {});

  if (scope === 'all') {
    try {
      const res = await repositories.users.pool.query(
        'SELECT core_user_id FROM discord_users WHERE discord_guild_id = $1',
        [guildId]
      );
      const coreUserIds = res.rows.map((row) => row.core_user_id);

      logger.info({ guildId, userCount: coreUserIds.length }, 'Starting server-wide prefix memory clear');
      for (const coreUserId of coreUserIds) {
        await coreRagClient.clearMemory(coreUserId).catch((err) => {
          logger.warn({ err, coreUserId }, 'Failed to clear user memory during prefix server clear');
        });
      }

      await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE discord_guild_id = $1', [guildId]);
      await repositories.users.pool.query('DELETE FROM discord_users WHERE discord_guild_id = $1', [guildId]);

      logger.info({ guildId }, 'Discord prefix server-wide memory cleared');
      await message.reply('Đã xóa toàn bộ memory của Chisa đối với tất cả thành viên trong Server này.');
    } catch (error) {
      logger.error({ err: error, guildId }, 'Discord prefix server clear failed');
      await message.reply('Không thể xóa memory Server lúc này. Hãy thử lại sau.');
    }
    return;
  }

  // Scope: self
  const interactionId = await repositories.interactions.createFromContext(message, {
    coreUserId: discordUser.core_user_id,
    commandName: `${client.services.prefixCommandRunner?.prefix || 'c!'}clear`,
    userMessage: `${client.services.prefixCommandRunner?.prefix || 'c!'}clear self`,
    status: 'clearing',
    metadata: { source: 'discord', command: data.name, mode: 'prefix' },
  });

  try {
    await coreRagClient.clearMemory(discordUser.core_user_id);
    await repositories.interactions.clearUserInteractions(discordUser.core_user_id, interactionId);
    await repositories.users.markCleared(discordUser.core_user_id);
    await repositories.interactions.markSuccess(interactionId, {
      assistantMessage: 'Memory cleared',
      metadata: { source: 'core-rag', command: data.name, mode: 'prefix' },
    });

    logger.info({ userId: message.author.id, coreUserId: discordUser.core_user_id }, 'Discord prefix memory cleared');
    await message.reply('Memory của bạn trên server này đã được xóa. Chisa sẽ bắt đầu lại từ đầu trong lần trò chuyện tiếp theo.');
  } catch (error) {
    logger.error({ err: error, userId: message.author.id }, 'Discord prefix clear failed');
    await repositories.interactions.markFailure(interactionId, error instanceof Error ? error.message : String(error));
    await message.reply('Không thể xóa memory lúc này. Hãy thử lại sau.');
  }
}
