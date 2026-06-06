import { SlashCommandBuilder } from 'discord.js';
import { DEFAULT_COMMANDS } from '../config/constants.js';
import { splitDiscordMessage } from '../utils/reply.js';

export const data = new SlashCommandBuilder()
  .setName(DEFAULT_COMMANDS.ask)
  .setDescription('Gửi một câu hỏi tới Chisa')
  .addStringOption((option) =>
    option
      .setName('message')
      .setDescription('Nội dung muốn hỏi Chisa')
      .setRequired(true),
  )
  .setDMPermission(false);

export async function execute(client, interaction) {
  const { logger, rateLimiter, repositories, coreRagClient } = client.services;
  const question = interaction.options.getString('message', true).trim();
  const rateKey = `${interaction.user.id}:ask`;
  const rate = rateLimiter.allow(rateKey);

  if (!rate.allowed) {
    const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
    await interaction.reply({
      content: `Bạn đang gửi quá nhanh. Hãy chờ khoảng ${waitSeconds}s rồi thử lại.`,
      ephemeral: true,
    });
    return;
  }

  await interaction.deferReply();

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
    userMessage: question,
    metadata: {
      source: 'discord',
      command: data.name,
    },
  });

  try {
    await repositories.interactions.markCoreRequest(interactionId);

    const result = await coreRagClient.ask({
      coreUserId: discordUser.core_user_id,
      message: question,
    });

    await repositories.interactions.markSuccess(interactionId, {
      assistantMessage: result.response,
      metadata: {
        emotions: result.emotions,
        source: 'core-rag',
      },
    });

    const chunks = splitDiscordMessage(result.response, client.services.config.reply.maxChars);
    await interaction.editReply({ content: chunks[0] || 'Chisa chưa tạo được phản hồi.' });

    for (let index = 1; index < chunks.length; index += 1) {
      await interaction.followUp({ content: chunks[index] });
    }
  } catch (error) {
    logger.error({ err: error, userId: interaction.user.id, interactionId }, 'Discord /ask failed');
    await repositories.interactions.markFailure(interactionId, error instanceof Error ? error.message : String(error));

    const message = 'Xin lỗi, Chisa không thể trả lời lúc này. Hãy thử lại sau ít phút.';
    if (interaction.deferred || interaction.replied) {
      await interaction.editReply({ content: message });
    } else {
      await interaction.reply({ content: message, ephemeral: true });
    }
  }
}
