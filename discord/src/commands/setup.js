import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
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
  .setDMPermission(false);

function createSetupEmbed(client, channelName) {
  return new EmbedBuilder()
    .setTitle('🌸 Cổng Kết Nối Trực Tiếp Chisa 🌸')
    .setDescription(`Kênh **${channelName}** đã được thiết lập để kết nối trực tiếp với Chisa!`)
    .addFields(
      { 
        name: '💬 Trò chuyện không cần lệnh', 
        value: 'Từ bây giờ, bạn có thể nhắn tin trực tiếp trong kênh này và Chisa sẽ luôn trả lời mà không cần dùng lệnh `/ask` hay prefix `c!ask`' 
      },
      { 
        name: '🤫 Tắt tự động phản hồi / Dùng lệnh Bot khác', 
        value: 'Nếu muốn gửi tin nhắn thường hoặc dùng lệnh prefix bot khác trong kênh này mà **không muốn Chisa trả lời**, hãy thêm tiền tố `!` hoặc `c!` ở đầu tin nhắn (Ví dụ: `!Chào mọi người`, `c!help`, `!play ...`).' 
      }
    )
    .setColor('#ffb6c1')
    .setThumbnail(client.user.displayAvatarURL())
    .setTimestamp();
}

function parseChannelIds(args) {
  const channelIds = [];
  const invalidArgs = [];
  
  for (const arg of args) {
    const match = arg.match(/^<#(\d+)>$/);
    if (match) {
      channelIds.push(match[1]);
    } else if (/^\d+$/.test(arg)) {
      channelIds.push(arg);
    } else {
      invalidArgs.push(arg);
    }
  }
  return { channelIds, invalidArgs };
}

async function disableAll(client, guildId) {
  const { logger, repositories, guildSettingsCache } = client.services;
  
  const activeChannels = [];
  for (const [chanId, gId] of guildSettingsCache.entries()) {
    if (gId === guildId) {
      activeChannels.push(chanId);
    }
  }

  if (activeChannels.length === 0) {
    return {
      replyText: 'Hiện tại server này không có kênh nào đang được kích hoạt cổng kết nối trực tiếp với Chisa.',
      disabled: []
    };
  }

  try {
    await repositories.guildSettings.disableAllChannels(guildId);
    for (const chanId of activeChannels) {
      guildSettingsCache.delete(chanId);
      
      // Notify the target channel itself
      try {
        const chan = await client.channels.fetch(chanId);
        if (chan?.isTextBased()) {
          await chan.send('🌸 Cổng kết nối trực tiếp với Chisa tại kênh này đã được hủy.');
        }
      } catch (err) {
        logger.warn({ err, channelId: chanId }, 'Failed to send disabled notification to target channel during disable all');
      }
    }
    
    logger.info({ guildId }, 'Disabled all direct chat channels for guild');
    const listStr = activeChannels.map(id => `- <#${id}>`).join('\n');
    return {
      replyText: `Đã hủy kích hoạt tất cả các cổng kết nối trực tiếp với Chisa trên server này:\n${listStr}`,
      disabled: activeChannels
    };
  } catch (error) {
    logger.error({ err: error, guildId }, 'Failed to disable all direct chat channels');
    return {
      replyText: 'Gặp lỗi khi hủy kích hoạt tất cả kênh trò chuyện trực tiếp.',
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
      
      // Notify the target channel itself
      try {
        const chan = await client.channels.fetch(channelId);
        if (chan?.isTextBased()) {
          await chan.send('🌸 Cổng kết nối trực tiếp với Chisa tại kênh này đã được hủy.');
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

async function enableChannels(client, guildId, channelIds, triggeredByUserId) {
  const { logger, repositories, guildSettingsCache } = client.services;

  const enabled = [];
  const alreadyEnabled = [];
  const failed = [];
  const invalid = [];

  for (const channelId of channelIds) {
    if (guildSettingsCache.has(channelId)) {
      alreadyEnabled.push(channelId);
      continue;
    }

    try {
      const channel = await client.channels.fetch(channelId);
      if (!channel || !channel.isTextBased()) {
        invalid.push(channelId);
        continue;
      }

      await repositories.guildSettings.setChisaChannel(guildId, channelId, triggeredByUserId);
      guildSettingsCache.set(channelId, guildId);
      enabled.push(channelId);

      // Send the fancy setup embed in the target channel itself
      const embed = createSetupEmbed(client, channel.name);
      await channel.send({ embeds: [embed] });
    } catch (error) {
      logger.error({ err: error, guildId, channelId }, 'Failed to enable channel');
      failed.push(channelId);
    }
  }

  let replyText = '';
  if (enabled.length > 0) {
    replyText += `Đã thiết lập thành công cổng kết nối trực tiếp tại các kênh:\n${enabled.map(id => `- <#${id}>`).join('\n')}\n`;
  }
  if (alreadyEnabled.length > 0) {
    replyText += `Các kênh sau đã được kích hoạt cổng kết nối trực tiếp với Chisa rồi ạ:\n${alreadyEnabled.map(id => `- <#${id}>`).join('\n')}\n`;
  }
  if (invalid.length > 0) {
    replyText += `Các kênh sau không hợp lệ hoặc không phải là kênh chat chữ:\n${invalid.map(id => `- <#${id}>`).join('\n')}\n`;
  }
  if (failed.length > 0) {
    replyText += `Gặp lỗi khi thiết lập các kênh:\n${failed.map(id => `- <#${id}>`).join('\n')}\n`;
  }

  return { replyText: replyText.trim(), enabled };
}

export async function execute(client, interaction) {
  const { logger, repositories, guildSettingsCache } = client.services;
  
  if (!isGuildModeratorOrAdmin(interaction.member)) {
    await interaction.reply({
      content: 'Chỉ Admin hoặc Moderator mới có quyền sử dụng lệnh này.',
      ephemeral: true,
    });
    return;
  }

  const action = interaction.options.getString('action') || 'enable';
  const allOption = interaction.options.getBoolean('all') || false;
  const guildId = interaction.guildId;

  if (action === 'disable' && allOption) {
    await interaction.deferReply({ ephemeral: true });
    const res = await disableAll(client, guildId);
    await interaction.editReply({
      content: res.replyText,
    });
    return;
  }

  const targetChannel = interaction.options.getChannel('channel') || interaction.channel;
  
  if (!targetChannel.isTextBased()) {
    await interaction.reply({
      content: 'Vui lòng chọn một kênh chat chữ (text channel) hợp lệ.',
      ephemeral: true,
    });
    return;
  }

  if (action === 'disable') {
    await interaction.deferReply({ ephemeral: true });
    const res = await disableChannels(client, guildId, [targetChannel.id]);
    await interaction.editReply({
      content: res.replyText,
    });
    return;
  }

  // Action: enable
  await interaction.deferReply({ ephemeral: true });
  const res = await enableChannels(client, guildId, [targetChannel.id], interaction.user.id);
  await interaction.editReply({
    content: res.replyText,
  });
}

export async function executePrefix(client, message, argsText) {
  const { logger, repositories, guildSettingsCache } = client.services;
  
  if (!isGuildModeratorOrAdmin(message.member)) {
    await message.reply('Chỉ Admin hoặc Moderator mới có quyền sử dụng lệnh này.');
    return;
  }

  const guildId = message.guildId;
  const args = argsText ? argsText.trim().split(/\s+/) : [];
  const arg1 = args[0]?.toLowerCase();
  const arg2 = args[1]?.toLowerCase();

  // Case: c!setup list
  if (arg1 === 'list') {
    const activeChannels = [];
    for (const [chanId, gId] of guildSettingsCache.entries()) {
      if (gId === guildId) {
        activeChannels.push(chanId);
      }
    }

    if (activeChannels.length === 0) {
      await message.reply('Hiện tại server này không có kênh nào được thiết lập làm cổng kết nối trực tiếp với Chisa.');
      return;
    }

    const channelListStr = activeChannels.map((id) => `- <#${id}>`).join('\n');
    await message.reply(`🌸 **Danh sách các cổng kết nối trực tiếp với Chisa:**\n${channelListStr}`);
    return;
  }

  // Case: c!setup disable all
  if (arg1 === 'disable' && arg2 === 'all') {
    const res = await disableAll(client, guildId);
    await message.reply(res.replyText);
    return;
  }

  // Case: c!setup disable [channels...]
  if (arg1 === 'disable') {
    const channelArgs = args.slice(1);
    let targetChannelIds = [];
    
    if (channelArgs.length > 0) {
      const { channelIds, invalidArgs } = parseChannelIds(channelArgs);
      if (invalidArgs.length > 0) {
        await message.reply(`Có đối số không phải kênh hợp lệ: ${invalidArgs.join(', ')}`);
        return;
      }
      targetChannelIds = channelIds;
    } else {
      targetChannelIds = [message.channel.id];
    }

    const res = await disableChannels(client, guildId, targetChannelIds);
    await message.reply(res.replyText);
    return;
  }

  // Case: c!setup [channels...] (enable)
  const channelArgs = args;
  let targetChannelIds = [];
  
  if (channelArgs.length > 0) {
    const { channelIds, invalidArgs } = parseChannelIds(channelArgs);
    if (invalidArgs.length > 0) {
      await message.reply(`Cú pháp không hợp lệ. Sử dụng:\n- \`c!setup\` (Bật kênh này)\n- \`c!setup <#kênh1> <#kênh2> ...\` (Bật nhiều kênh được tag)\n- \`c!setup disable\` (Tắt kênh này)\n- \`c!setup disable <#kênh1> <#kênh2> ...\` (Tắt nhiều kênh được tag)\n- \`c!setup disable all\` (Tắt tất cả)\n- \`c!setup list\` (Xem danh sách các kênh)`);
      return;
    }
    targetChannelIds = channelIds;
  } else {
    targetChannelIds = [message.channel.id];
  }

  const res = await enableChannels(client, guildId, targetChannelIds, message.author.id);
  await message.reply(res.replyText);
}
