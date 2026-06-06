import { SlashCommandBuilder } from 'discord.js';
import { DEFAULT_COMMANDS } from '../config/constants.js';

export const data = new SlashCommandBuilder()
  .setName(DEFAULT_COMMANDS.clear)
  .setDescription('Xóa memory của Chisa cho chính bạn')
  .setDMPermission(false);

export async function execute(client, interaction) {
  const { logger, rateLimiter, repositories, coreRagClient } = client.services;
  const rateKey = `${interaction.user.id}:clear`;
  const rate = rateLimiter.allow(rateKey);

  if (!rate.allowed) {
    const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
    await interaction.reply({
      content: `Bạn vừa dùng /clear quá nhanh. Hãy chờ khoảng ${waitSeconds}s rồi thử lại.`,
      ephemeral: true,
    });
    return;
  }

  await interaction.deferReply({ ephemeral: true });

  const discordUser = await repositories.users.ensureDiscordUser({
    discordUserId: interaction.user.id,
    discordUserName: interaction.user.username,
    discordUserGlobalName: interaction.user.globalName ?? null,
    discordUserTag: interaction.user.tag ?? interaction.user.username,
  });

  const interactionId = await repositories.interactions.createInteraction({
    discordUserId: interaction.user.id,
    coreUserId: discordUser.core_user_id,
    discordUserName: interaction.user.username,
    discordUserGlobalName: interaction.user.globalName ?? null,
    discordUserTag: interaction.user.tag ?? interaction.user.username,
    discordGuildId: interaction.guildId ?? null,
    discordGuildName: interaction.guild?.name ?? null,
    discordChannelId: interaction.channelId,
    discordChannelName: interaction.channel?.name ?? null,
    discordMessageId: interaction.id,
    commandName: data.name,
    userMessage: '/clear',
    status: 'clearing',
    metadata: {
      source: 'discord',
      command: data.name,
    },
  });

  try {
    await coreRagClient.clearMemory(discordUser.core_user_id);
    await repositories.interactions.clearUserInteractions(discordUser.core_user_id, interactionId);
    await repositories.users.markCleared(discordUser.core_user_id);
    await repositories.interactions.markSuccess(interactionId, {
      assistantMessage: 'Memory cleared',
      metadata: {
        source: 'core-rag',
        command: data.name,
      },
    });

    logger.info({ userId: interaction.user.id, coreUserId: discordUser.core_user_id }, 'Discord memory cleared');
    await interaction.editReply({
      content: 'Memory của bạn đã được xóa. Chisa sẽ bắt đầu lại từ đầu trong lần trò chuyện tiếp theo.',
    });
  } catch (error) {
    logger.error({ err: error, userId: interaction.user.id }, 'Discord /clear failed');
    await repositories.interactions.markFailure(interactionId, error instanceof Error ? error.message : String(error));
    await interaction.editReply({
      content: 'Không thể xóa memory lúc này. Hãy thử lại sau.',
    });
  }
}
