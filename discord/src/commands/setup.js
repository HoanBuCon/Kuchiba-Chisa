import { SlashCommandBuilder, EmbedBuilder, InteractionContextType } from 'discord.js';
import { isGuildModeratorOrAdmin } from '../utils/permissions.js';

export const data = new SlashCommandBuilder()
  .setName('setup')
  .setDescription('Thiết lập kênh trò chuyện trực tiếp với Chisa')
  .addStringOption((option) =>
    option
      .setName('action')
      .setDescription('Hành động muốn thực hiện (mặc định là enable)')
      .setRequired(false)
      .addChoices(
        { name: 'Kích hoạt cho kênh (enable)', value: 'enable' },
        { name: 'Hủy kích hoạt cho kênh (disable)', value: 'disable' },
        { name: 'Xem danh sách các kênh (list)', value: 'list' },
      ),
  )
  .addStringOption((option) =>
    option
      .setName('mode')
      .setDescription('Chế độ: community (cộng đồng), semi-private (liên thông), private (cô lập)')
      .setRequired(false)
      .addChoices(
        { name: 'Cộng đồng / Nhóm (community)', value: 'community' },
        { name: 'Riêng tư liên thông Server (semi-private)', value: 'semi-private' },
        { name: 'Riêng tư cô lập tuyệt đối (private)', value: 'private' },
      ),
  )
  .addChannelOption((option) =>
    option
      .setName('channel')
      .setDescription('Kênh muốn thiết lập/hủy thiết lập (mặc định là kênh hiện tại)')
      .setRequired(false),
  )
  .addBooleanOption((option) =>
    option
      .setName('all')
      .setDescription('Hủy kích hoạt cho tất cả các kênh (chỉ dùng với action disable)')
      .setRequired(false),
  )
  .setContexts([
    InteractionContextType.Guild,
    InteractionContextType.BotDM,
    InteractionContextType.PrivateChannel,
  ]);

function formatModeName(mode) {
  if (mode === 'community') return 'Cộng đồng (Community)';
  if (mode === 'private') return 'Riêng tư cô lập (Private)';
  return 'Riêng tư liên thông (Semi-Private)';
}

function createNoticeEmbed({ title, description, color = '#ffb6c1' }) {
  return new EmbedBuilder()
    .setTitle(title)
    .setDescription(description)
    .setColor(color)
    .setTimestamp();
}

function createSetupEmbed(client, channelName, mode = 'semi-private') {
  if (mode === 'community') {
    return new EmbedBuilder()
      .setTitle('🌸 Cổng Kết Nối Cộng Đồng Chisa (Community Mode) 🌸')
      .setDescription(`Kênh **${channelName}** đã được thiết lập ở chế độ **Chat Cộng Đồng (Community)**!`)
      .addFields(
        { 
          name: '👥 Điều kiện Phản hồi Cộng đồng', 
          value: 'Trong kênh cộng đồng, Chisa chỉ phản hồi khi bạn **Mention (@Chisa)** hoặc **Reply (Trả lời)** vào tin nhắn của Chisa. Em ấy sẽ tự động nắm bắt 15 tin nhắn gần nhất của phòng để trả lời đúng ngữ cảnh của cả nhóm.'
        },
        { 
          name: '🤫 Tắt tự động phản hồi / Dùng lệnh Bot khác', 
          value: 'Nếu muốn gửi tin nhắn thường hoặc dùng lệnh prefix bot khác trong kênh này mà **không muốn Chisa trả lời**, hãy thêm tiền tố `!` hoặc `c!` ở đầu tin nhắn (Ví dụ: `!Chào mọi người`, `c!help`, `!play ...`).' 
        }
      )
      .setColor('#7289da')
      .setThumbnail(client.user.displayAvatarURL())
      .setTimestamp();
  }

  if (mode === 'semi-private') {
    return new EmbedBuilder()
      .setTitle('🌸 Cổng Trò Chuyện 1-1 Liên Thông Server (Semi-Private Mode) 🌸')
      .setDescription(`Kênh **${channelName}** đã được thiết lập ở chế độ **Riêng tư Liên thông (Semi-Private)**!`)
      .addFields(
        { 
          name: '💬 Trò chuyện 1-1 không cần lệnh', 
          value: 'Bạn có thể nhắn tin trực tiếp trong kênh này và Chisa sẽ trò chuyện 1-1 với bạn mà không cần dùng lệnh `/ask` hay prefix `c!ask`.' 
        },
        { 
          name: '🔗 Đồng bộ Ký ức & Bối cảnh Server', 
          value: 'Kênh này chia sẻ chung ký ức, cảm xúc và nhận thức về các sự kiện diễn ra ở kênh Community trong cùng Server.' 
        },
        { 
          name: '🤫 Tắt tự động phản hồi', 
          value: 'Thêm tiền tố `!` hoặc `c!` ở đầu tin nhắn nếu không muốn Chisa trả lời.' 
        }
      )
      .setColor('#ff9ff3')
      .setThumbnail(client.user.displayAvatarURL())
      .setTimestamp();
  }

  // Mode: private (isolated)
  return new EmbedBuilder()
    .setTitle('🌸 Cổng Kết Nối Cô Lập Tuyệt Đối (Private Mode) 🌸')
    .setDescription(`Kênh **${channelName}** đã được thiết lập ở chế độ **Riêng tư Cô lập Tuyệt đối (Private)**!`)
    .addFields(
      { 
        name: '🔒 Không gian 1-1 Cô lập Tuyệt đối', 
        value: 'Kênh này hoạt động như một thế giới riêng tư hoàn toàn tách biệt với các kênh khác trong server.' 
      },
      { 
        name: '🤫 Tắt tự động phản hồi', 
        value: 'Thêm tiền tố `!` hoặc `c!` ở đầu tin nhắn nếu không muốn Chisa trả lời.' 
      }
    )
    .setColor('#a29bfe')
    .setThumbnail(client.user.displayAvatarURL())
    .setTimestamp();
}

function parseChannelIds(channelArgs) {
  const channelIds = [];
  const invalidArgs = [];

  for (const arg of channelArgs) {
    const match = arg.match(/^<#(\d+)>$/) || arg.match(/^(\d+)$/);
    if (match) {
      channelIds.push(match[1]);
    } else {
      invalidArgs.push(arg);
    }
  }

  return { channelIds: [...new Set(channelIds)], invalidArgs };
}

async function disableAll(client, guildId) {
  const { logger, repositories, guildSettingsCache } = client.services;
  
  try {
    const disabledChannelIds = await repositories.guildSettings.disableAllChisaChannels(guildId);
    for (const channelId of disabledChannelIds) {
      guildSettingsCache.delete(channelId);
      try {
        const chan = await client.channels.fetch(channelId);
        if (chan?.isTextBased()) {
          const embed = createNoticeEmbed({
            title: '🌸 CỔNG KẾT NỐI ĐÃ ĐƯỢC HỦY',
            description: 'Cổng kết nối trực tiếp với Chisa tại kênh này đã được hủy.',
            color: '#95a5a6',
          });
          await chan.send({ embeds: [embed] });
        }
      } catch (err) {
        logger.warn({ err, channelId }, 'Failed to send disabled notification to channel');
      }
    }

    return {
      replyText: disabledChannelIds.length > 0
        ? `Đã hủy kích hoạt thành công toàn bộ **${disabledChannelIds.length}** cổng kết nối tại Server này.`
        : 'Server này hiện không có cổng kết nối nào đang kích hoạt.',
      disabled: disabledChannelIds
    };
  } catch (error) {
    logger.error({ err: error, guildId }, 'Failed to disable all channels');
    return {
      replyText: 'Gặp lỗi trong quá trình hủy kích hoạt tất cả các kênh.',
      disabled: []
    };
  }
}

async function disableChannels(client, guildId, channelIds) {
  const { logger, repositories, guildSettingsCache } = client.services;
  
  const disabled = [];
  const alreadyDisabled = [];
  const failed = [];

  for (const channelId of channelIds) {
    if (!guildSettingsCache.has(channelId)) {
      alreadyDisabled.push(channelId);
      continue;
    }

    try {
      await repositories.guildSettings.disableChisaChannel(channelId);
      guildSettingsCache.delete(channelId);
      disabled.push(channelId);
      
      try {
        const chan = await client.channels.fetch(channelId);
        if (chan?.isTextBased()) {
          const embed = createNoticeEmbed({
            title: '🌸 CỔNG KẾT NỐI ĐÃ ĐƯỢC HỦY',
            description: 'Cổng kết nối trực tiếp với Chisa tại kênh này đã được hủy.',
            color: '#95a5a6',
          });
          await chan.send({ embeds: [embed] });
        }
      } catch (err) {
        logger.warn({ err, channelId }, 'Failed to send disabled notification to target channel');
      }
    } catch (error) {
      logger.error({ err: error, guildId, channelId }, 'Failed to disable channel');
      failed.push(channelId);
    }
  }

  let replyText = '';
  if (disabled.length > 0) {
    replyText += `Đã hủy kích hoạt cổng kết nối trực tiếp tại các kênh:\n${disabled.map(id => `- <#${id}>`).join('\n')}\n`;
  }
  if (alreadyDisabled.length > 0) {
    replyText += `Các kênh sau đã không hoạt động từ trước:\n${alreadyDisabled.map(id => `- <#${id}>`).join('\n')}\n`;
  }
  if (failed.length > 0) {
    replyText += `Gặp lỗi khi hủy kích hoạt các kênh:\n${failed.map(id => `- <#${id}>`).join('\n')}\n`;
  }

  return { replyText: replyText.trim(), disabled };
}

async function enableChannels(client, guildId, channelIds, triggeredByUserId, mode = 'semi-private') {
  const { logger, repositories, guildSettingsCache } = client.services;

  const enabled = [];
  const alreadyEnabled = [];
  const updatedMode = [];
  const failed = [];
  const invalid = [];

  for (const channelId of channelIds) {
    const existing = guildSettingsCache.get(channelId);
    const existingMode = typeof existing === 'object' ? existing.mode : 'private';

    if (existing && existingMode === mode) {
      alreadyEnabled.push({ id: channelId, mode });
      continue;
    }

    try {
      const channel = await client.channels.fetch(channelId);
      if (!channel || !channel.isTextBased()) {
        invalid.push(channelId);
        continue;
      }

      await repositories.guildSettings.setChisaChannel(guildId, channelId, triggeredByUserId, mode);
      guildSettingsCache.set(channelId, { guildId, mode });

      if (existing) {
        updatedMode.push({ id: channelId, mode });
      } else {
        enabled.push({ id: channelId, mode });
      }

      const embed = createSetupEmbed(client, channel.name, mode);
      await channel.send({ embeds: [embed] });
    } catch (error) {
      logger.error({ err: error, guildId, channelId }, 'Failed to enable channel');
      failed.push(channelId);
    }
  }

  let replyText = '';
  if (enabled.length > 0) {
    replyText += `Đã thiết lập thành công cổng kết nối tại các kênh:\n${enabled.map(item => `- <#${item.id}> (Chế độ: **${formatModeName(item.mode)}**)`).join('\n')}\n`;
  }
  if (updatedMode.length > 0) {
    replyText += `Đã cập nhật chế độ thành công tại các kênh:\n${updatedMode.map(item => `- <#${item.id}> (Chế độ mới: **${formatModeName(item.mode)}**)`).join('\n')}\n`;
  }
  if (alreadyEnabled.length > 0) {
    replyText += `Các kênh sau đã đang hoạt động đúng chế độ này rồi ạ:\n${alreadyEnabled.map(item => `- <#${item.id}> (Chế độ: **${formatModeName(item.mode)}**)`).join('\n')}\n`;
  }
  if (invalid.length > 0) {
    replyText += `Các kênh sau không hợp lệ hoặc không phải là kênh chat chữ:\n${invalid.map(id => `- <#${id}>`).join('\n')}\n`;
  }
  if (failed.length > 0) {
    replyText += `Gặp lỗi khi thiết lập các kênh:\n${failed.map(id => `- <#${id}>`).join('\n')}\n`;
  }

  return { replyText: replyText.trim(), enabled, updatedMode };
}

export async function execute(client, interaction) {
  if (!interaction.guildId) {
    const embed = createNoticeEmbed({
      title: '💬 TIN NHẮN RIÊNG (DM) VỚI CHISA LUÔN SẴN SÀNG',
      description:
        'Không gian trò chuyện trực tiếp (DM) đã được mặc định kích hoạt sẵn ở chế độ **Riêng tư 1-1 (Private Mode)**. Senpai có thể nhắn tin trực tiếp với em bất cứ lúc nào mà không cần dùng lệnh `/setup` nhé ~\n\n' +
        '*(Lệnh `/setup` chỉ dùng để chỉ định và quản lý các kênh kết nối trong Server Discord)*',
      color: '#ffb6c1',
    });
    await interaction.reply({ embeds: [embed], ephemeral: true });
    return;
  }

  if (!isGuildModeratorOrAdmin(interaction.member)) {
    const embed = createNoticeEmbed({
      title: '🚫 YÊU CẦU QUYỀN QUẢN TRỊ',
      description: 'Chỉ Admin hoặc Moderator mới có quyền sử dụng lệnh này.',
      color: '#e67e22',
    });
    await interaction.reply({ embeds: [embed], ephemeral: true });
    return;
  }

  const action = interaction.options.getString('action') || 'enable';
  const mode = interaction.options.getString('mode') || 'semi-private';
  const allOption = interaction.options.getBoolean('all') || false;
  const guildId = interaction.guildId;

  // Action: list
  if (action === 'list') {
    const { guildSettingsCache } = client.services;
    const activeChannels = [];
    for (const [chanId, setting] of guildSettingsCache.entries()) {
      const gId = typeof setting === 'object' ? setting.guildId : setting;
      const chMode = typeof setting === 'object' ? setting.mode : 'private';
      if (gId === guildId) {
        activeChannels.push({ id: chanId, mode: chMode });
      }
    }

    if (activeChannels.length === 0) {
      const embed = createNoticeEmbed({
        title: '🌸 DANH SÁCH CỔNG KẾT NỐI',
        description: 'Hiện tại server này không có kênh nào được thiết lập làm cổng kết nối trực tiếp với Chisa.',
        color: '#95a5a6',
      });
      await interaction.reply({ embeds: [embed], ephemeral: true });
      return;
    }

    const channelListStr = activeChannels.map((item) => `- <#${item.id}> (Chế độ: **${formatModeName(item.mode)}**)`).join('\n');
    const embed = createNoticeEmbed({
      title: '🌸 DANH SÁCH CÁC CỔNG KẾT NỐI TRỰC TIẾP VỚI CHISA',
      description: channelListStr,
      color: '#ba68c8',
    });
    await interaction.reply({ embeds: [embed], ephemeral: true });
    return;
  }

  if (action === 'disable' && allOption) {
    await interaction.deferReply({ ephemeral: true });
    const res = await disableAll(client, guildId);
    const embed = createNoticeEmbed({
      title: '🌸 KẾT QUẢ HỦY KÍCH HOẠT',
      description: res.replyText,
      color: '#95a5a6',
    });
    await interaction.editReply({ embeds: [embed] });
    return;
  }

  const targetChannel = interaction.options.getChannel('channel') || interaction.channel;
  
  if (!targetChannel.isTextBased()) {
    const embed = createNoticeEmbed({
      title: '❌ KÊNH KHÔNG HỢP LỆ',
      description: 'Vui lòng chọn một kênh chat chữ (text channel) hợp lệ.',
      color: '#e74c3c',
    });
    await interaction.reply({ embeds: [embed], ephemeral: true });
    return;
  }

  if (action === 'disable') {
    await interaction.deferReply({ ephemeral: true });
    const res = await disableChannels(client, guildId, [targetChannel.id]);
    const embed = createNoticeEmbed({
      title: '🌸 KẾT QUẢ HỦY THIẾT LẬP KÊNH',
      description: res.replyText,
      color: '#95a5a6',
    });
    await interaction.editReply({ embeds: [embed] });
    return;
  }

  // Action: enable
  if (action === 'enable') {
    await interaction.deferReply({ ephemeral: true });
    const res = await enableChannels(client, guildId, [targetChannel.id], interaction.user.id, mode);
    const embed = createNoticeEmbed({
      title: '🌸 KẾT QUẢ THIẾT LẬP KÊNH',
      description: res.replyText,
      color: '#2ecc71',
    });
    await interaction.editReply({ embeds: [embed] });
    return;
  }

  const embed = createNoticeEmbed({
    title: '❌ HÀNH ĐỘNG KHÔNG HỢP LỆ',
    description: `Hành động không hợp lệ: ${action}`,
    color: '#e74c3c',
  });
  await interaction.reply({ embeds: [embed], ephemeral: true });
}

export async function executePrefix(client, message, argsText) {
  if (!message.guildId) {
    const embed = createNoticeEmbed({
      title: '💬 TIN NHẮN RIÊNG (DM) VỚI CHISA LUÔN SẴN SÀNG',
      description:
        'Không gian trò chuyện trực tiếp (DM) đã được mặc định kích hoạt sẵn ở chế độ **Riêng tư 1-1 (Private Mode)**. Senpai có thể nhắn tin trực tiếp với em bất cứ lúc nào mà không cần dùng lệnh `c!setup` nhé ~\n\n' +
        '*(Lệnh `c!setup` chỉ dùng để chỉ định và quản lý các kênh kết nối trong Server Discord)*',
      color: '#ffb6c1',
    });
    await message.reply({ embeds: [embed] });
    return;
  }

  const { guildSettingsCache } = client.services;
  
  if (!isGuildModeratorOrAdmin(message.member)) {
    const embed = createNoticeEmbed({
      title: '🚫 YÊU CẦU QUYỀN QUẢN TRỊ',
      description: 'Chỉ Admin hoặc Moderator mới có quyền sử dụng lệnh này.',
      color: '#e67e22',
    });
    await message.reply({ embeds: [embed] });
    return;
  }

  const guildId = message.guildId;
  const args = argsText ? argsText.trim().split(/\s+/) : [];
  const arg1 = args[0]?.toLowerCase();
  const arg2 = args[1]?.toLowerCase();

  // Case: c!setup list
  if (arg1 === 'list') {
    const activeChannels = [];
    for (const [chanId, setting] of guildSettingsCache.entries()) {
      const gId = typeof setting === 'object' ? setting.guildId : setting;
      const chMode = typeof setting === 'object' ? setting.mode : 'private';
      if (gId === guildId) {
        activeChannels.push({ id: chanId, mode: chMode });
      }
    }

    if (activeChannels.length === 0) {
      const embed = createNoticeEmbed({
        title: '🌸 DANH SÁCH CỔNG KẾT NỐI',
        description: 'Hiện tại server này không có kênh nào được thiết lập làm cổng kết nối trực tiếp với Chisa.',
        color: '#95a5a6',
      });
      await message.reply({ embeds: [embed] });
      return;
    }

    const channelListStr = activeChannels.map((item) => `- <#${item.id}> (Chế độ: **${formatModeName(item.mode)}**)`).join('\n');
    const embed = createNoticeEmbed({
      title: '🌸 DANH SÁCH CÁC CỔNG KẾT NỐI TRỰC TIẾP VỚI CHISA',
      description: channelListStr,
      color: '#ba68c8',
    });
    await message.reply({ embeds: [embed] });
    return;
  }

  // Case: c!setup disable all
  if (arg1 === 'disable' && arg2 === 'all') {
    const res = await disableAll(client, guildId);
    const embed = createNoticeEmbed({
      title: '🌸 KẾT QUẢ HỦY KÍCH HOẠT',
      description: res.replyText,
      color: '#95a5a6',
    });
    await message.reply({ embeds: [embed] });
    return;
  }

  // Case: c!setup disable [channels...]
  if (arg1 === 'disable') {
    const channelArgs = args.slice(1);
    let targetChannelIds = [];
    
    if (channelArgs.length > 0) {
      const { channelIds, invalidArgs } = parseChannelIds(channelArgs);
      if (invalidArgs.length > 0) {
        const embed = createNoticeEmbed({
          title: '❌ KÊNH KHÔNG HỢP LỆ',
          description: `Có đối số không phải kênh hợp lệ: ${invalidArgs.join(', ')}`,
          color: '#e74c3c',
        });
        await message.reply({ embeds: [embed] });
        return;
      }
      targetChannelIds = channelIds;
    } else {
      targetChannelIds = [message.channel.id];
    }

    const res = await disableChannels(client, guildId, targetChannelIds);
    const embed = createNoticeEmbed({
      title: '🌸 KẾT QUẢ HỦY THIẾT LẬP KÊNH',
      description: res.replyText,
      color: '#95a5a6',
    });
    await message.reply({ embeds: [embed] });
    return;
  }

  // Case: c!setup [channels...] [mode: community/semi-private/private] (enable)
  let mode = 'semi-private';
  const cleanArgs = [];
  for (const a of args) {
    const lower = a.toLowerCase();
    if (lower === 'community' || lower === 'group' || lower === 'congdong') {
      mode = 'community';
    } else if (lower === 'semi-private' || lower === 'semi' || lower === 'semiprivate' || lower === 'lienthong') {
      mode = 'semi-private';
    } else if (lower === 'private' || lower === 'isolated' || lower === 'colap' || lower === 'riengtu') {
      mode = 'private';
    } else {
      cleanArgs.push(a);
    }
  }

  let targetChannelIds = [];
  if (cleanArgs.length > 0) {
    const { channelIds, invalidArgs } = parseChannelIds(cleanArgs);
    if (invalidArgs.length > 0) {
      const embed = createNoticeEmbed({
        title: '❌ CÚ PHÁP LỆNH SETUP KHÔNG HỢP LỆ',
        description:
          'Sử dụng các cú pháp sau:\n' +
          '• `c!setup` (Bật kênh này chế độ **Semi-Private** liên thông — mặc định)\n' +
          '• `c!setup community` (Bật kênh này chế độ **Community** cộng đồng)\n' +
          '• `c!setup private` (Bật kênh này chế độ **Private** cô lập)\n' +
          '• `c!setup <#kênh> [community/semi-private/private]` (Bật kênh được tag)\n' +
          '• `c!setup disable` (Tắt kênh này)\n' +
          '• `c!setup disable all` (Tắt tất cả)\n' +
          '• `c!setup list` (Xem danh sách các kênh)',
        color: '#e74c3c',
      });
      await message.reply({ embeds: [embed] });
      return;
    }
    targetChannelIds = channelIds;
  } else {
    targetChannelIds = [message.channel.id];
  }

  const res = await enableChannels(client, guildId, targetChannelIds, message.author.id, mode);
  const embed = createNoticeEmbed({
    title: '🌸 KẾT QUẢ THIẾT LẬP KÊNH',
    description: res.replyText,
    color: '#2ecc71',
  });
  await message.reply({ embeds: [embed] });
}
