import { SlashCommandBuilder } from 'discord.js';
import { DEFAULT_COMMANDS } from '../config/constants.js';
import { replyWithChunks } from '../utils/reply.js';

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

export async function execute(client, interaction, discordUser) {
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

  const interactionId = await repositories.interactions.createFromContext(interaction, {
    coreUserId: discordUser.core_user_id,
    commandName: data.name,
    userMessage: question,
    metadata: { source: 'discord', command: data.name },
  });

  try {
    await repositories.interactions.markCoreRequest(interactionId);

    const result = await coreRagClient.ask({
      coreUserId: discordUser.core_user_id,
      message: question,
      username: interaction.user.username,
      channelName: interaction.channel ? (interaction.channel.name || 'DM') : 'DM',
      guildName: interaction.guild ? interaction.guild.name : null,
    });

    await repositories.interactions.markSuccess(interactionId, {
      assistantMessage: result.response,
      metadata: { emotions: result.emotions, source: 'core-rag' },
    });

    await replyWithChunks(interaction, result.response, result.emotions, client);
  } catch (error) {
    logger.error({ err: error, userId: interaction.user.id, interactionId }, 'Discord /ask failed');
    await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE id = $1', [interactionId]);

    const message = 'Xin lỗi Senpai, Chisa không thể trả lời lúc này. Hãy thử lại sau ít phút.';
    await interaction.editReply({ content: message });
  }
}

export async function executePrefix(client, message, question, discordUser) {
  const { logger, rateLimiter, repositories, coreRagClient } = client.services;
  const rateKey = `${message.author.id}:ask`;
  const rate = rateLimiter.allow(rateKey);

  if (!rate.allowed) {
    const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
    await message.reply(`Bạn đang gửi quá nhanh. Hãy chờ khoảng ${waitSeconds}s rồi thử lại.`);
    return;
  }

  if (!question) {
    await message.reply(`Dùng ${client.services.prefixCommandRunner?.prefix || 'c!'}ask <nội dung> để hỏi Chisa.`);
    return;
  }

  await message.channel.sendTyping().catch(() => {});

  // Send thinking message placeholder
  let thinkingMsg = null;
  try {
    thinkingMsg = await message.channel.send('*Chisa đang suy nghĩ...*');
  } catch {
    // Non-critical: proceed without thinking message if it fails
  }

  const interactionId = await repositories.interactions.createFromContext(message, {
    coreUserId: discordUser.core_user_id,
    commandName: `${client.services.prefixCommandRunner?.prefix || 'c!'}ask`,
    userMessage: question,
    metadata: { source: 'discord', command: data.name, mode: 'prefix' },
  });

  try {
    await repositories.interactions.markCoreRequest(interactionId);

    const result = await coreRagClient.ask({
      coreUserId: discordUser.core_user_id,
      message: question,
      username: message.author.username,
      channelName: message.channel ? (message.channel.name || 'DM') : 'DM',
      guildName: message.guild ? message.guild.name : null,
    });

    await repositories.interactions.markSuccess(interactionId, {
      assistantMessage: result.response,
      metadata: { emotions: result.emotions, source: 'core-rag', mode: 'prefix' },
    });

    // Delete thinking message before sending the actual reply
    if (thinkingMsg) {
      await thinkingMsg.delete().catch(() => {});
    }

    await replyWithChunks(message, result.response, result.emotions, client);
  } catch (error) {
    logger.error({ err: error, userId: message.author.id, interactionId }, 'Discord prefix ask failed');
    await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE id = $1', [interactionId]);

    // Delete thinking message on error too
    if (thinkingMsg) {
      await thinkingMsg.delete().catch(() => {});
    }

    await message.reply('Xin lỗi Senpai, Chisa không thể trả lời lúc này. Hãy thử lại sau ít phút.');
  }
}
