import { SlashCommandBuilder, InteractionContextType } from 'discord.js';
import { DEFAULT_COMMANDS } from '../config/constants.js';
import { isGuildModeratorOrAdmin } from '../utils/permissions.js';

export const data = new SlashCommandBuilder()
  .setName(DEFAULT_COMMANDS.clear)
  .setDescription('Xóa memory và làm mới ngữ cảnh trò chuyện của Chisa')
  .addStringOption((option) =>
    option
      .setName('mode')
      .setDescription('Chọn phân loại bộ nhớ cần xóa (community / private / nuke)')
      .setRequired(false)
      .addChoices(
        { name: '🌐 Community (Ký ức Cộng đồng, Sự kiện Server & Topic Kênh)', value: 'community' },
        { name: '🔒 Private (Ký ức Cá nhân, Lịch sử chat riêng & Cảm xúc)', value: 'private' },
        { name: '☢️ NUKE (Xóa TOÀN BỘ Ký ức Community + Private của TẤT CẢ Member - Yêu cầu Admin/Mod)', value: 'nuke' },
      ),
  )
  .addStringOption((option) =>
    option
      .setName('scope')
      .setDescription('Chọn phạm vi thành viên áp dụng (self / all)')
      .setRequired(false)
      .addChoices(
        { name: '👤 Chỉ bản thân (self)', value: 'self' },
        { name: '👥 Toàn bộ Server (all) - Yêu cầu quyền Admin/Mod', value: 'all' },
      ),
  )
  .setContexts([
    InteractionContextType.Guild,
    InteractionContextType.BotDM,
    InteractionContextType.PrivateChannel,
  ]);

export async function execute(client, interaction, discordUser) {
  const { logger, rateLimiter, repositories, coreRagClient } = client.services;
  const rawMode = interaction.options.getString('mode');
  const rawScope = interaction.options.getString('scope');

  const mode = rawMode || 'private';
  const scope = rawScope || 'self';
  const guildId = interaction.guildId || 'DM';
  const isDM = !interaction.guildId;

  // ── 1. Kiểm tra Quyền Hạn & Môi Trường ───────────────────────
  if (isDM) {
    if (mode === 'community' || mode === 'nuke' || scope === 'all') {
      await interaction.reply({
        content:
          `❌ Tùy chọn **${mode === 'nuke' ? 'mode: nuke' : mode === 'community' ? 'mode: community' : 'scope: all'}** chỉ áp dụng khi quản lý Server Discord.\n\n` +
          'Trong không gian trò chuyện riêng (DM), Senpai có thể làm mới cuộc trò chuyện bằng lệnh:\n' +
          '👉 `/clear mode:private scope:self` (hoặc gõ `c!clear`)',
        ephemeral: true,
      });
      return;
    }
  } else {
    const requiresAdmin = mode === 'nuke' || scope === 'all';
    if (requiresAdmin && !isGuildModeratorOrAdmin(interaction.member)) {
      await interaction.reply({
        content: `🚫 **Yêu Cầu Quyền Quản Trị:** Chỉ **Administrator** hoặc **Moderator** của Server mới có quyền xóa ${mode === 'nuke' ? 'toàn bộ ký ức Server (NUKE)' : 'ký ức phạm vi toàn bộ Server (all)'}.`,
        ephemeral: true,
      });
      return;
    }
  }

  // ── 2. Rate Limiting ──────────────────────────────────────────
  const rateKey = `${interaction.user.id}:clear:${mode}:${scope}`;
  const rate = rateLimiter.allow(rateKey);

  if (!rate.allowed) {
    const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
    await interaction.reply({
      content: `⏳ Bạn vừa thực hiện lệnh xóa quá nhanh. Hãy chờ khoảng ${waitSeconds}s rồi thử lại nhé.`,
      ephemeral: true,
    });
    return;
  }

  await interaction.deferReply({ ephemeral: true });

  const interactionId = await repositories.interactions.createFromContext(interaction, {
    coreUserId: discordUser.core_user_id,
    commandName: data.name,
    userMessage: `/clear mode:${mode} scope:${scope}`,
    status: 'clearing',
    metadata: { source: 'discord', command: data.name, mode, scope },
  });

  try {
    // ── CASE 1: MODE NUKE (Quick-clear toàn bộ Server) ───────────
    if (mode === 'nuke') {
      logger.info({ guildId, adminId: interaction.user.id }, 'Initiating NUKE server memory clear');

      // 1. Establish Temporal Clear Cutoff (Barrier so past messages are ignored)
      const cutoffTimestamp = Date.now();
      if (client.services.guildClearCutoffCache) {
        client.services.guildClearCutoffCache.set(guildId, cutoffTimestamp);
      }
      await repositories.guildSettings.setClearCutoff(guildId, cutoffTimestamp).catch((err) => {
        logger.warn({ err, guildId }, 'Failed to persist clear cutoff to database');
      });

      // 2. Clear Community Memory
      await coreRagClient.clearCommunityMemory({ guildId, scope: 'all' }).catch((err) => {
        logger.warn({ err, guildId }, 'Failed to clear community memory during NUKE');
      });

      // 3. Clear Private Memory for all users in the guild
      const res = await repositories.users.pool.query(
        'SELECT core_user_id FROM discord_users WHERE discord_guild_id = $1',
        [guildId]
      );
      const coreUserIds = res.rows.map((row) => row.core_user_id);
      for (const coreUserId of coreUserIds) {
        await coreRagClient.clearMemory(coreUserId).catch((err) => {
          logger.warn({ err, coreUserId }, 'Failed to clear user memory during NUKE');
        });
      }

      await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE discord_guild_id = $1', [guildId]);
      await repositories.users.pool.query('DELETE FROM discord_users WHERE discord_guild_id = $1', [guildId]);

      await repositories.interactions.markSuccess(interactionId, {
        assistantMessage: 'Server nuke completed',
        metadata: { mode: 'nuke', scope: 'all', cutoffTimestamp },
      });

      await interaction.editReply({
        content:
          '☢️ **NUKE SERVER THÀNH CÔNG!**\n' +
          '• Toàn bộ **Ký ức Cộng đồng** (Sự kiện Server, Văn hóa chung, Mạch tóm tắt kênh) đã được dọn sạch.\n' +
          '• Toàn bộ **Ký ức Cá nhân & Chỉ số Cảm xúc** của **TẤT CẢ THÀNH VIÊN** trong Server đã được reset về mặc định.\n' +
          '• **Mốc Thời Gian Ngắt (Cutoff)** đã được thiết lập: Chisa sẽ không đọc lại bất kỳ tin nhắn nào được gửi trước thời điểm này!\n' +
          '• Chisa sẽ xem toàn bộ Server như một không gian hoàn toàn mới!',
      });
      return;
    }

    // ── CASE 2: MODE COMMUNITY ────────────────────────────────────
    if (mode === 'community') {
      if (scope === 'all') {
        logger.info({ guildId }, 'Clearing all community memory for server');

        // Establish Temporal Clear Cutoff
        const cutoffTimestamp = Date.now();
        if (client.services.guildClearCutoffCache) {
          client.services.guildClearCutoffCache.set(guildId, cutoffTimestamp);
        }
        await repositories.guildSettings.setClearCutoff(guildId, cutoffTimestamp).catch((err) => {
          logger.warn({ err, guildId }, 'Failed to persist clear cutoff to database');
        });

        await coreRagClient.clearCommunityMemory({ guildId, scope: 'all' });

        await repositories.interactions.markSuccess(interactionId, {
          assistantMessage: 'Community memory cleared for all',
          metadata: { mode: 'community', scope: 'all', cutoffTimestamp },
        });

        await interaction.editReply({
          content:
            '🏛️ **ĐÃ XÓA TOÀN BỘ KÝ ỨC CỘNG ĐỒNG CỦA SERVER!**\n' +
            '• Tri thức sự kiện & văn hóa phòng chat trên Qdrant (`guild_memories`) đã được xóa sạch.\n' +
            '• Mạch tóm tắt chủ đề các kênh (`topic_summary`) và Khí sắc chung (`ambient_mood`) đã được đặt lại từ đầu.\n' +
            '• **Mốc Thời Gian Ngắt (Cutoff)** đã được thiết lập: Chisa sẽ không đọc lại các tin nhắn cũ trước thời điểm này.\n' +
            '*(Ký ức trò chuyện riêng tư của từng thành viên vẫn được bảo lưu an toàn)*',
        });
      } else {
        // scope === 'self'
        logger.info({ guildId, userId: interaction.user.id }, 'Clearing self community memory');
        await coreRagClient.clearCommunityMemory({
          guildId,
          channelId: interaction.channelId,
          coreUserId: discordUser.core_user_id,
          scope: 'self',
        });

        await repositories.interactions.markSuccess(interactionId, {
          assistantMessage: 'Community memory cleared for self',
          metadata: { mode: 'community', scope: 'self' },
        });

        await interaction.editReply({
          content:
            '🌱 **ĐÃ XÓA KÝ ỨC CỘNG ĐỒNG CỦA RIÊNG BẠN!**\n' +
            'Chisa đã quên các tương tác và dữ kiện cộng đồng của bạn trong Server này. Khi bạn chat trong các kênh cộng đồng, Chisa sẽ bắt nhịp lại như thành viên mới.',
        });
      }
      return;
    }

    // ── CASE 3: MODE PRIVATE (Ký ức cá nhân) ──────────────────────
    if (mode === 'private') {
      if (scope === 'all') {
        logger.info({ guildId }, 'Clearing private memory for all guild members');
        const res = await repositories.users.pool.query(
          'SELECT core_user_id FROM discord_users WHERE discord_guild_id = $1',
          [guildId]
        );
        const coreUserIds = res.rows.map((row) => row.core_user_id);
        for (const coreUserId of coreUserIds) {
          await coreRagClient.clearMemory(coreUserId).catch((err) => {
            logger.warn({ err, coreUserId }, 'Failed to clear user private memory in all clear');
          });
        }

        await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE discord_guild_id = $1', [guildId]);
        await repositories.users.pool.query('DELETE FROM discord_users WHERE discord_guild_id = $1', [guildId]);

        await repositories.interactions.markSuccess(interactionId, {
          assistantMessage: 'Private memory cleared for all',
          metadata: { mode: 'private', scope: 'all' },
        });

        await interaction.editReply({
          content:
            '🔒 **ĐÃ XÓA TOÀN BỘ KÝ ỨC CÁ NHÂN CỦA TẤT CẢ THÀNH VIÊN TRONG SERVER!**\n' +
            'Lịch sử trò chuyện riêng tư và điểm tình cảm (Trust, Attachment) của toàn bộ thành viên đã được làm mới từ đầu.\n' +
            '*(Ký ức sự kiện chung của Server vẫn được giữ nguyên)*',
        });
      } else {
        // scope === 'self'
        logger.info({ userId: interaction.user.id, coreUserId: discordUser.core_user_id }, 'Clearing self private memory');
        await coreRagClient.clearMemory(discordUser.core_user_id);
        await repositories.interactions.clearUserInteractions(discordUser.core_user_id, interactionId);
        await repositories.users.markCleared(discordUser.core_user_id);

        await repositories.interactions.markSuccess(interactionId, {
          assistantMessage: 'Private memory cleared for self',
          metadata: { mode: 'private', scope: 'self' },
        });

        const successMsg = isDM
          ? '🌸 **ĐÃ XÓA KÝ ỨC TRÒ CHUYỆN RIÊNG (DM)!**\nLịch sử chat và điểm tình cảm của bạn với Chisa đã được làm mới từ đầu.'
          : '🌸 **ĐÃ XÓA KÝ ỨC CÁ NHÂN CỦA BẠN!**\nLịch sử trò chuyện riêng tư, kỷ niệm cá nhân và chỉ số gắn kết với Chisa đã được làm mới hoàn toàn.';

        await interaction.editReply({ content: successMsg });
      }
    }
  } catch (error) {
    logger.error({ err: error, userId: interaction.user.id, mode, scope }, 'Discord /clear execution failed');
    await repositories.interactions.markFailure(interactionId, error instanceof Error ? error.message : String(error));
    await interaction.editReply({
      content: '❌ Không thể xóa memory lúc này do có lỗi phát sinh. Hãy thử lại sau ít phút.',
    });
  }
}

export async function executePrefix(client, message, argsText, discordUser) {
  const { logger, rateLimiter, repositories, coreRagClient } = client.services;
  const args = argsText ? argsText.trim().split(/\s+/).map((a) => a.toLowerCase()) : [];

  let mode = 'private';
  let scope = 'self';

  // Parse arguments: c!clear [mode/nuke] [scope]
  if (args.includes('nuke')) {
    mode = 'nuke';
    scope = 'all';
  } else if (args.includes('community')) {
    mode = 'community';
    scope = args.includes('all') ? 'all' : 'self';
  } else if (args.includes('private')) {
    mode = 'private';
    scope = args.includes('all') ? 'all' : 'self';
  } else if (args.includes('all')) {
    scope = 'all';
  }

  const guildId = message.guildId || 'DM';
  const isDM = !message.guildId;
  const requiresAdmin = mode === 'nuke' || scope === 'all';

  // ── 1. Kiểm tra Quyền Hạn & Môi Trường ───────────────────────
  if (isDM) {
    if (mode === 'community' || mode === 'nuke' || scope === 'all') {
      await message.reply(
        `❌ Tùy chọn **${mode === 'nuke' ? 'nuke' : mode === 'community' ? 'community' : 'all'}** chỉ áp dụng khi quản lý Server Discord.\n\n` +
        'Trong không gian trò chuyện riêng (DM), Senpai có thể làm mới cuộc trò chuyện bằng lệnh:\n' +
        '👉 `c!clear` (hoặc `/clear mode:private scope:self`)'
      );
      return;
    }
  } else {
    if (requiresAdmin && !isGuildModeratorOrAdmin(message.member)) {
      await message.reply(
        `🚫 **Yêu Cầu Quyền Quản Trị:** Chỉ **Administrator** hoặc **Moderator** của Server mới có quyền xóa ${
          mode === 'nuke' ? 'toàn bộ ký ức Server (NUKE)' : 'ký ức phạm vi toàn bộ Server (all)'
        }.`
      );
      return;
    }
  }

  // ── 2. Rate Limiting ──────────────────────────────────────────
  const rateKey = `${message.author.id}:clear:${mode}:${scope}`;
  const rate = rateLimiter.allow(rateKey);

  if (!rate.allowed) {
    const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
    await message.reply(`⏳ Bạn vừa dùng clear quá nhanh. Hãy chờ khoảng ${waitSeconds}s rồi thử lại nhé.`);
    return;
  }

  await message.channel.sendTyping().catch(() => {});

  const interactionId = await repositories.interactions.createFromContext(message, {
    coreUserId: discordUser.core_user_id,
    commandName: `${client.services.prefixCommandRunner?.prefix || 'c!'}clear`,
    userMessage: `${client.services.prefixCommandRunner?.prefix || 'c!'}clear ${mode} ${scope}`,
    status: 'clearing',
    metadata: { source: 'discord', command: data.name, mode, scope, isPrefix: true },
  });

  try {
    // ── CASE 1: NUKE ──────────────────────────────────────────────
    if (mode === 'nuke') {
      logger.info({ guildId, adminId: message.author.id }, 'Prefix NUKE server clear');

      // 1. Establish Temporal Clear Cutoff
      const cutoffTimestamp = Date.now();
      if (client.services.guildClearCutoffCache) {
        client.services.guildClearCutoffCache.set(guildId, cutoffTimestamp);
      }
      await repositories.guildSettings.setClearCutoff(guildId, cutoffTimestamp).catch((err) => {
        logger.warn({ err, guildId }, 'Failed to persist clear cutoff to database in prefix NUKE');
      });

      // 2. Clear Community Memory
      await coreRagClient.clearCommunityMemory({ guildId, scope: 'all' }).catch((err) => {
        logger.warn({ err, guildId }, 'Failed community clear during prefix NUKE');
      });

      const res = await repositories.users.pool.query(
        'SELECT core_user_id FROM discord_users WHERE discord_guild_id = $1',
        [guildId]
      );
      const coreUserIds = res.rows.map((row) => row.core_user_id);
      for (const coreUserId of coreUserIds) {
        await coreRagClient.clearMemory(coreUserId).catch((err) => {
          logger.warn({ err, coreUserId }, 'Failed user clear during prefix NUKE');
        });
      }

      await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE discord_guild_id = $1', [guildId]);
      await repositories.users.pool.query('DELETE FROM discord_users WHERE discord_guild_id = $1', [guildId]);

      await repositories.interactions.markSuccess(interactionId, {
        assistantMessage: 'Prefix NUKE completed',
        metadata: { mode: 'nuke', scope: 'all', cutoffTimestamp },
      });

      await message.reply(
        '☢️ **NUKE SERVER THÀNH CÔNG!**\n' +
        '• Toàn bộ **Ký ức Cộng đồng** (Sự kiện Server, Văn hóa chung, Mạch tóm tắt kênh) đã được dọn sạch.\n' +
        '• Toàn bộ **Ký ức Cá nhân & Chỉ số Cảm xúc** của **TẤT CẢ THÀNH VIÊN** trong Server đã được reset về mặc định.\n' +
        '• **Mốc Thời Gian Ngắt (Cutoff)** đã được thiết lập: Chisa sẽ không đọc lại bất kỳ tin nhắn nào được gửi trước thời điểm này!\n' +
        '• Chisa sẽ xem toàn bộ Server như một không gian hoàn toàn mới!'
      );
      return;
    }

    // ── CASE 2: COMMUNITY ─────────────────────────────────────────
    if (mode === 'community') {
      if (scope === 'all') {
        logger.info({ guildId }, 'Prefix clearing all community memory');

        // Establish Temporal Clear Cutoff
        const cutoffTimestamp = Date.now();
        if (client.services.guildClearCutoffCache) {
          client.services.guildClearCutoffCache.set(guildId, cutoffTimestamp);
        }
        await repositories.guildSettings.setClearCutoff(guildId, cutoffTimestamp).catch((err) => {
          logger.warn({ err, guildId }, 'Failed to persist clear cutoff to database in prefix community clear');
        });

        await coreRagClient.clearCommunityMemory({ guildId, scope: 'all' });

        await repositories.interactions.markSuccess(interactionId, {
          assistantMessage: 'Prefix community cleared for all',
          metadata: { mode: 'community', scope: 'all', cutoffTimestamp },
        });

        await message.reply(
          '🏛️ **ĐÃ XÓA TOÀN BỘ KÝ ỨC CỘNG ĐỒNG CỦA SERVER!**\n' +
          '• Tri thức sự kiện & văn hóa phòng chat trên Qdrant (`guild_memories`) đã được xóa sạch.\n' +
          '• Mạch tóm tắt chủ đề các kênh (`topic_summary`) và Khí sắc chung (`ambient_mood`) đã được đặt lại từ đầu.\n' +
          '• **Mốc Thời Gian Ngắt (Cutoff)** đã được thiết lập: Chisa sẽ không đọc lại các tin nhắn cũ trước thời điểm này.\n' +
          '*(Ký ức trò chuyện riêng tư của từng thành viên vẫn được bảo lưu an toàn)*'
        );
      } else {
        logger.info({ guildId, userId: message.author.id }, 'Prefix clearing self community memory');
        await coreRagClient.clearCommunityMemory({
          guildId,
          channelId: message.channelId,
          coreUserId: discordUser.core_user_id,
          scope: 'self',
        });

        await repositories.interactions.markSuccess(interactionId, {
          assistantMessage: 'Prefix community cleared for self',
          metadata: { mode: 'community', scope: 'self' },
        });

        await message.reply(
          '🌱 **ĐÃ XÓA KÝ ỨC CỘNG ĐỒNG CỦA RIÊNG BẠN!**\n' +
          'Chisa đã quên các tương tác và dữ kiện cộng đồng của bạn trong Server này. Khi bạn chat trong các kênh cộng đồng, Chisa sẽ bắt nhịp lại như thành viên mới.'
        );
      }
      return;
    }

    // ── CASE 3: PRIVATE ───────────────────────────────────────────
    if (mode === 'private') {
      if (scope === 'all') {
        logger.info({ guildId }, 'Prefix clearing private memory for all');
        const res = await repositories.users.pool.query(
          'SELECT core_user_id FROM discord_users WHERE discord_guild_id = $1',
          [guildId]
        );
        const coreUserIds = res.rows.map((row) => row.core_user_id);
        for (const coreUserId of coreUserIds) {
          await coreRagClient.clearMemory(coreUserId).catch((err) => {
            logger.warn({ err, coreUserId }, 'Failed user clear in prefix private all');
          });
        }

        await repositories.interactions.pool.query('DELETE FROM discord_interactions WHERE discord_guild_id = $1', [guildId]);
        await repositories.users.pool.query('DELETE FROM discord_users WHERE discord_guild_id = $1', [guildId]);

        await repositories.interactions.markSuccess(interactionId, {
          assistantMessage: 'Prefix private cleared for all',
          metadata: { mode: 'private', scope: 'all' },
        });

        await message.reply(
          '🔒 **ĐÃ XÓA TOÀN BỘ KÝ ỨC CÁ NHÂN CỦA TẤT CẢ THÀNH VIÊN TRONG SERVER!**\n' +
          'Lịch sử trò chuyện riêng tư và điểm tình cảm (Trust, Attachment) của toàn bộ thành viên đã được làm mới từ đầu.\n' +
          '*(Ký ức sự kiện chung của Server vẫn được giữ nguyên)*'
        );
      } else {
        logger.info({ userId: message.author.id, coreUserId: discordUser.core_user_id }, 'Prefix clearing self private memory');
        await coreRagClient.clearMemory(discordUser.core_user_id);
        await repositories.interactions.clearUserInteractions(discordUser.core_user_id, interactionId);
        await repositories.users.markCleared(discordUser.core_user_id);

        await repositories.interactions.markSuccess(interactionId, {
          assistantMessage: 'Prefix private cleared for self',
          metadata: { mode: 'private', scope: 'self' },
        });

        const successMsg = isDM
          ? '🌸 **ĐÃ XÓA KÝ ỨC TRÒ CHUYỆN RIÊNG (DM)!**\nLịch sử chat và điểm tình cảm của bạn với Chisa đã được làm mới từ đầu.'
          : '🌸 **ĐÃ XÓA KÝ ỨC CÁ NHÂN CỦA BẠN!**\nLịch sử trò chuyện riêng tư, kỷ niệm cá nhân và chỉ số gắn kết với Chisa đã được làm mới hoàn toàn.';

        await message.reply(successMsg);
      }
    }
  } catch (error) {
    logger.error({ err: error, userId: message.author.id, mode, scope }, 'Discord prefix clear failed');
    await repositories.interactions.markFailure(interactionId, error instanceof Error ? error.message : String(error));
    await message.reply('❌ Không thể xóa memory lúc này do có lỗi phát sinh. Hãy thử lại sau ít phút.');
  }
}
