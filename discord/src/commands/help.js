import {
  SlashCommandBuilder,
  EmbedBuilder,
  AttachmentBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ComponentType,
  InteractionContextType,
} from 'discord.js';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const bannerUrl = new URL('../assets/img/chisa_banner.jpg', import.meta.url);
const bannerPath = fileURLToPath(bannerUrl);

export const data = new SlashCommandBuilder()
  .setName('help')
  .setDescription('Hiển thị bảng hướng dẫn và tra cứu chi tiết từng lệnh của Chisa')
  .setContexts([
    InteractionContextType.Guild,
    InteractionContextType.BotDM,
    InteractionContextType.PrivateChannel,
  ]);

const HELP_PAGES = {
  home: {
    title: '🌸 TRUNG TÂM HƯỚNG DẪN SỬ DỤNG - KUCHIBA CHISA 🌸',
    footer: 'Bấm các nút bên dưới để chuyển trang',
  },
  ask: {
    title: '💬 HƯỚNG DẪN CHI TIẾT: /ask & c!ask',
    footer: 'Lệnh /ask',
  },
  clear: {
    title: '🧹 HƯỚNG DẪN CHI TIẾT: /clear & c!clear',
    footer: 'Lệnh /clear',
  },
  setup: {
    title: '⚙️ HƯỚNG DẪN CHI TIẾT: /setup & c!setup',
    footer: 'Lệnh /setup',
  },
  docs: {
    title: '📖 HƯỚNG DẪN CHI TIẾT: /docs & c!docs',
    footer: 'Lệnh /docs',
  },
  about: {
    title: '🌸 HƯỚNG DẪN CHI TIẾT: /about & c!about',
    footer: 'Lệnh /about',
  },
};

const helpContentCache = new Map();

async function loadHelpPageContent(pageKey = 'home') {
  if (helpContentCache.has(pageKey)) {
    return helpContentCache.get(pageKey);
  }

  try {
    const fileUrl = new URL(`../assets/docs/help/${pageKey}.md`, import.meta.url);
    const content = await readFile(fileUrl, 'utf8');
    helpContentCache.set(pageKey, content);
    return content;
  } catch (error) {
    return 'Không thể tải nội dung hướng dẫn cho mục này. Vui lòng liên hệ Admin.';
  }
}

async function createHelpEmbed(pageKey = 'home') {
  const meta = HELP_PAGES[pageKey] || HELP_PAGES.home;
  const content = await loadHelpPageContent(pageKey);

  return new EmbedBuilder()
    .setTitle(meta.title)
    .setDescription(content)
    .setColor('#ffb6c1')
    .setImage('attachment://chisa_banner.jpg')
    .setFooter({ text: meta.footer })
    .setTimestamp();
}

function createHelpActionRows(currentPage = 'home') {
  const row1 = new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId('help_ask')
      .setLabel('/ask')
      .setEmoji('💬')
      .setStyle(currentPage === 'ask' ? ButtonStyle.Primary : ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId('help_clear')
      .setLabel('/clear')
      .setEmoji('🧹')
      .setStyle(currentPage === 'clear' ? ButtonStyle.Primary : ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId('help_setup')
      .setLabel('/setup')
      .setEmoji('⚙️')
      .setStyle(currentPage === 'setup' ? ButtonStyle.Primary : ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId('help_docs')
      .setLabel('/docs')
      .setEmoji('📖')
      .setStyle(currentPage === 'docs' ? ButtonStyle.Primary : ButtonStyle.Secondary),
    new ButtonBuilder()
      .setCustomId('help_about')
      .setLabel('/about')
      .setEmoji('🌸')
      .setStyle(currentPage === 'about' ? ButtonStyle.Primary : ButtonStyle.Secondary),
  );

  const row2 = new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId('help_home')
      .setLabel('Trang Tổng Quan')
      .setEmoji('🏠')
      .setStyle(currentPage === 'home' ? ButtonStyle.Success : ButtonStyle.Secondary)
      .setDisabled(currentPage === 'home'),
  );

  return [row1, row2];
}

function setupHelpCollector(message, authorId) {
  const collector = message.createMessageComponentCollector({
    componentType: ComponentType.Button,
    time: 300_000, // 5 minutes
  });

  collector.on('collect', async (i) => {
    if (i.user.id !== authorId) {
      await i.reply({
        content: '🌸 Bảng hướng dẫn này đang mở cho Senpai đã gọi lệnh. Bạn hãy tự gõ `/help` hoặc `c!help` để tương tác riêng nhé!',
        ephemeral: true,
      });
      return;
    }

    const pageKey = i.customId.replace('help_', '');
    const newEmbed = await createHelpEmbed(pageKey);
    const newComponents = createHelpActionRows(pageKey);

    await i.update({
      embeds: [newEmbed],
      components: newComponents,
    });
  });

  collector.on('end', async () => {
    try {
      const disabledRows = createHelpActionRows('home').map((row) => {
        row.components.forEach((btn) => btn.setDisabled(true));
        return row;
      });
      await message.edit({ components: disabledRows }).catch(() => {});
    } catch {
      // Ignore if message was deleted
    }
  });
}

export async function execute(client, interaction) {
  const bannerAttachment = new AttachmentBuilder(bannerPath, { name: 'chisa_banner.jpg' });
  const embed = await createHelpEmbed('home');
  const components = createHelpActionRows('home');

  const response = await interaction.reply({
    embeds: [embed],
    components,
    files: [bannerAttachment],
    fetchReply: true,
  });

  setupHelpCollector(response, interaction.user.id);
}

export async function executePrefix(client, message, argsText) {
  const bannerAttachment = new AttachmentBuilder(bannerPath, { name: 'chisa_banner.jpg' });
  const embed = await createHelpEmbed('home');
  const components = createHelpActionRows('home');

  const response = await message.reply({
    embeds: [embed],
    components,
    files: [bannerAttachment],
  });

  setupHelpCollector(response, message.author.id);
}
