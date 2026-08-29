import { SlashCommandBuilder, EmbedBuilder, AttachmentBuilder, InteractionContextType } from 'discord.js';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const bannerUrl = new URL('../assets/img/chisa_banner.jpg', import.meta.url);
const bannerPath = fileURLToPath(bannerUrl);

export const data = new SlashCommandBuilder()
  .setName('docs')
  .setDescription('Hiển thị tài liệu chi tiết về hệ thống cảm xúc của Chisa')
  .setContexts([
    InteractionContextType.Guild,
    InteractionContextType.BotDM,
    InteractionContextType.PrivateChannel,
  ]);

const EMBED_DESC_LIMIT = 4096;

async function loadDocsContent() {
  try {
    const filePath = new URL('../assets/docs/emotion_docs.md', import.meta.url);
    return await readFile(filePath, 'utf8');
  } catch (error) {
    return 'Không thể tải tệp tài liệu cảm xúc. Vui lòng liên hệ Admin.';
  }
}

/**
 * Splits markdown content into chunks that fit within Discord's embed description limit.
 * Splits on `---` section dividers to keep sections intact.
 */
function splitIntoEmbedChunks(content) {
  const sections = content.split(/\r?\n---\r?\n/);
  const chunks = [];
  let current = '';

  for (const section of sections) {
    const separator = '\n---\n';
    const candidate = current ? current + separator + section : section;
    if (candidate.length <= EMBED_DESC_LIMIT) {
      current = candidate;
    } else {
      if (current) chunks.push(current);
      current = section.length <= EMBED_DESC_LIMIT ? section : section.substring(0, EMBED_DESC_LIMIT - 3) + '...';
    }
  }
  if (current) chunks.push(current);
  return chunks;
}

function buildDocsEmbeds(content, client) {
  const chunks = splitIntoEmbedChunks(content);

  return chunks.map((chunk, index) => {
    const embed = new EmbedBuilder()
      .setDescription(chunk)
      .setColor('#ba68c8');

    if (index === 0) {
      embed.setTitle('🌸 TÀI LIỆU HỆ THỐNG CẢM XÚC — RESONA Engine 🌸');
    }
    if (index === chunks.length - 1) {
      embed.setImage('attachment://chisa_banner.jpg');
      embed.setFooter({ text: 'RESONA Engine — Kuchiba Chisa' });
      embed.setTimestamp();
    }
    return embed;
  });
}

export async function execute(client, interaction) {
  const content = await loadDocsContent();
  const bannerAttachment = new AttachmentBuilder(bannerPath, { name: 'chisa_banner.jpg' });
  const embeds = buildDocsEmbeds(content, client);

  await interaction.reply({ embeds, files: [bannerAttachment] });
}

export async function executePrefix(client, message, argsText) {
  const content = await loadDocsContent();
  const bannerAttachment = new AttachmentBuilder(bannerPath, { name: 'chisa_banner.jpg' });
  const embeds = buildDocsEmbeds(content, client);

  await message.reply({ embeds, files: [bannerAttachment] });
}
