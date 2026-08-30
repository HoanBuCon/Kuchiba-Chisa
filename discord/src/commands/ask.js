import { SlashCommandBuilder, EmbedBuilder, InteractionContextType } from 'discord.js';
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
  .setContexts([
    InteractionContextType.Guild,
    InteractionContextType.BotDM,
    InteractionContextType.PrivateChannel,
  ]);

function createNoticeEmbed({ title, description, color = '#ffb6c1' }) {
  return new EmbedBuilder()
    .setTitle(title)
    .setDescription(description)
    .setColor(color)
    .setTimestamp();
}

async function fetchRecentChannelMessages(channel, limit = 15) {
  if (!channel?.messages?.fetch) {
    return [];
  }
  try {
    const fetched = await channel.messages.fetch({ limit: limit * 2 });
    const sorted = Array.from(fetched.values()).sort((a, b) => a.createdTimestamp - b.createdTimestamp);
    
    // Check Temporal Clear Cutoff for this guild (messages sent on or before cutoff are discarded)
    const cutoff = (channel.guildId && channel.client?.services?.guildClearCutoffCache?.get(channel.guildId)) || 0;
    const prefixRunner = channel.client?.services?.prefixCommandRunner;

    return sorted
      .filter((m) => {
        // 1. Temporal Barrier: Exclude any messages sent at or before the clear cutoff timestamp
        if (cutoff > 0 && m.createdTimestamp <= cutoff) return false;
        
        // 2. Exclude system messages, webhooks, and third-party bots completely
        if (m.system || m.webhookId) return false;
        if (m.author?.bot && m.author.id !== channel.client?.user?.id) return false;

        // 3. Exclude rich embed messages (all Chisa command notices, embeds & administrative cards)
        if (m.embeds && m.embeds.length > 0) return false;

        // 4. Exclude command invocations (dynamic prefix runner check or slash interactions)
        if (prefixRunner && prefixRunner.isPrefixCommand(m)) return false;
        if (m.interaction || m.interactionMetadata) return false;

        const text = (m.cleanContent || m.content || '').trim();
        if (!text) return false;

        // 5. Exclude common bot command prefixes (c!, !, /, $, %, ++, ;;, -, ?, ., ~, &, >)
        const COMMON_BOT_PREFIXES = ['c!', '!', '/', '$', '%', '++', ';;', '-', '?', '.', '~', '&', '>'];
        const lower = text.toLowerCase();
        if (COMMON_BOT_PREFIXES.some((p) => lower.startsWith(p)) && text.length > 1 && !text.startsWith('...') && !text.startsWith('?!')) {
          return false;
        }

        return true;
      })
      .slice(-limit)
      .map((m) => {
        let text = m.cleanContent || m.content || '';
        // Strip out Chisa's appended emotion breakdown block from past messages
        text = text.replace(/\*\*\[(?:Trạng thái Cảm xúc|Emotion State)\]\*\*[\s\S]*/i, '').trim();
        return {
          message_id: m.id,
          speaker_id: m.author.id,
          speaker_name: m.member?.displayName || m.author.globalName || m.author.username,
          content: text,
          reply_to_speaker: m.reference ? m.mentions?.repliedUser?.username : null,
          reply_to_content: null,
          is_bot: m.author.bot,
          created_at: new Date(m.createdTimestamp).toISOString(),
        };
      })
      .filter((m) => m.content.length > 0);
  } catch {
    return [];
  }
}

export async function execute(client, interaction, discordUser) {
  const { logger, rateLimiter, repositories, coreRagClient } = client.services;
  const question = interaction.options.getString('message', true).trim();
  const rateKey = `${interaction.user.id}:ask`;
  const rate = rateLimiter.allow(rateKey);

  if (!rate.allowed) {
    const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
    const embed = createNoticeEmbed({
      title: '⏳ THAO TÁC QUÁ NHANH',
      description: `Bạn đang gửi câu hỏi quá nhanh. Hãy chờ khoảng **${waitSeconds}s** rồi thử lại nhé.`,
      color: '#e67e22',
    });
    await interaction.reply({ embeds: [embed], ephemeral: true });
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

    let result;
    const channelSetting = client.services.guildSettingsCache?.get(interaction.channelId);
    const isCommunityMode = interaction.guild && channelSetting?.mode === 'community';

    if (isCommunityMode) {
      const recentMessages = await fetchRecentChannelMessages(interaction.channel, 15);
      result = await coreRagClient.askCommunity({
        channelId: interaction.channelId,
        guildId: interaction.guildId,
        channelName: interaction.channel?.name || 'general',
        guildName: interaction.guild?.name || null,
        coreUserId: discordUser.core_user_id,
        username: interaction.member?.displayName || interaction.user.globalName || interaction.user.username,
        message: question,
        recentMessages,
      });
    } else {
      result = await coreRagClient.ask({
        coreUserId: discordUser.core_user_id,
        message: question,
        username: interaction.user.username,
        channelName: interaction.channel ? (interaction.channel.name || 'DM') : 'DM',
        guildName: interaction.guild ? interaction.guild.name : null,
      });
    }

    await repositories.interactions.markSuccess(interactionId, {
      assistantMessage: result.response,
      metadata: { emotions: result.emotions, source: 'core-rag' },
    });

    await replyWithChunks(interaction, result.response, result.emotions, client);
  } catch (error) {
    if (error.status === 429 && error.payload && error.payload.detail) {
      logger.warn({ userId: interaction.user.id, interactionId }, 'Discord /ask blocked by 429 user lock');
      await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE id = $1', [interactionId]);
      const embed = createNoticeEmbed({
        title: '🔒 HỆ THỐNG ĐANG BẬN',
        description: error.payload.detail,
        color: '#e67e22',
      });
      await interaction.editReply({ embeds: [embed] });
    } else {
      logger.error({ err: error, userId: interaction.user.id, interactionId }, 'Discord /ask failed');
      await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE id = $1', [interactionId]);
      const embed = createNoticeEmbed({
        title: '🌸 THÔNG BÁO TỪ CHISA',
        description: 'Xin lỗi Senpai, Chisa không thể trả lời lúc này. Hãy thử lại sau ít phút nhé.',
        color: '#e74c3c',
      });
      await interaction.editReply({ embeds: [embed] });
    }
  }
}

export async function executePrefix(client, message, question, discordUser) {
  const { logger, rateLimiter, repositories, coreRagClient } = client.services;
  const rateKey = `${message.author.id}:ask`;
  const rate = rateLimiter.allow(rateKey);

  if (!rate.allowed) {
    const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
    const embed = createNoticeEmbed({
      title: '⏳ THAO TÁC QUÁ NHANH',
      description: `Bạn đang gửi câu hỏi quá nhanh. Hãy chờ khoảng **${waitSeconds}s** rồi thử lại nhé.`,
      color: '#e67e22',
    });
    await message.reply({ embeds: [embed] });
    return;
  }

  if (!question) {
    const prefix = client.services.prefixCommandRunner?.prefix || 'c!';
    const embed = createNoticeEmbed({
      title: '💬 HƯỚNG DẪN DÙNG LỆNH ASK',
      description: `Dùng \`${prefix}ask <nội dung>\` để trò chuyện hoặc hỏi Chisa nhé Senpai.`,
      color: '#ffb6c1',
    });
    await message.reply({ embeds: [embed] });
    return;
  }

  await message.channel.sendTyping().catch(() => {});
  const typingInterval = setInterval(() => {
    message.channel.sendTyping().catch(() => {});
  }, 8000);

  const interactionId = await repositories.interactions.createFromContext(message, {
    coreUserId: discordUser.core_user_id,
    commandName: `${client.services.prefixCommandRunner?.prefix || 'c!'}ask`,
    userMessage: question,
    metadata: { source: 'discord', command: data.name, mode: 'prefix' },
  });

  try {
    await repositories.interactions.markCoreRequest(interactionId);

    let result;
    const channelSetting = client.services.guildSettingsCache?.get(message.channelId);
    const isCommunityMode = message.guild && channelSetting?.mode === 'community';

    if (isCommunityMode) {
      const recentMessages = await fetchRecentChannelMessages(message.channel, 15);
      result = await coreRagClient.askCommunity({
        channelId: message.channelId,
        guildId: message.guildId,
        channelName: message.channel?.name || 'general',
        guildName: message.guild?.name || null,
        coreUserId: discordUser.core_user_id,
        username: message.member?.displayName || message.author.globalName || message.author.username,
        message: question,
        recentMessages,
      });
    } else {
      result = await coreRagClient.ask({
        coreUserId: discordUser.core_user_id,
        message: question,
        username: message.author.username,
        channelName: message.channel ? (message.channel.name || 'DM') : 'DM',
        guildName: message.guild ? message.guild.name : null,
      });
    }

    await repositories.interactions.markSuccess(interactionId, {
      assistantMessage: result.response,
      metadata: { emotions: result.emotions, source: 'core-rag', mode: 'prefix' },
    });

    await replyWithChunks(message, result.response, result.emotions, client);
  } catch (error) {
    if (error.status === 429 && error.payload && error.payload.detail) {
      logger.warn({ userId: message.author.id, interactionId }, 'Discord prefix ask blocked by 429 user lock');
      await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE id = $1', [interactionId]);
      const embed = createNoticeEmbed({
        title: '🔒 HỆ THỐNG ĐANG BẬN',
        description: error.payload.detail,
        color: '#e67e22',
      });
      await message.reply({ embeds: [embed] });
    } else {
      logger.error({ err: error, userId: message.author.id, interactionId }, 'Discord prefix ask failed');
      await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE id = $1', [interactionId]);
      const embed = createNoticeEmbed({
        title: '🌸 THÔNG BÁO TỪ CHISA',
        description: 'Xin lỗi Senpai, Chisa không thể trả lời lúc này. Hãy thử lại sau ít phút nhé.',
        color: '#e74c3c',
      });
      await message.reply({ embeds: [embed] });
    }
  } finally {
    clearInterval(typingInterval);
  }
}
