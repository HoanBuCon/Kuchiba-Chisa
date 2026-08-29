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

async function loadDocsContent() {
  try {
    const filePath = new URL('../assets/docs/emotion_docs.md', import.meta.url);
    return await readFile(filePath, 'utf8');
  } catch (error) {
    return 'Không thể tải tệp tài liệu cảm xúc. Vui lòng liên hệ Admin.';
  }
}

export async function execute(client, interaction) {
  const content = await loadDocsContent();
  const bannerAttachment = new AttachmentBuilder(bannerPath, { name: 'chisa_banner.jpg' });

  const embed = new EmbedBuilder()
    .setTitle('🌸 TÀI LIỆU HỆ THỐNG CẢM XÚC 🌸')
    .setDescription(content)
    .setColor('#ba68c8')
    .setImage('attachment://chisa_banner.jpg')
    .setFooter({ text: 'Kuchiba Chisa Emotion Engine' })
    .setTimestamp();

  await interaction.reply({ embeds: [embed], files: [bannerAttachment] });
}

export async function executePrefix(client, message, argsText) {
  const content = await loadDocsContent();
  const bannerAttachment = new AttachmentBuilder(bannerPath, { name: 'chisa_banner.jpg' });

  const embed = new EmbedBuilder()
    .setTitle('🌸 TÀI LIỆU HỆ THỐNG CẢM XÚC 🌸')
    .setDescription(content)
    .setColor('#ba68c8')
    .setImage('attachment://chisa_banner.jpg')
    .setFooter({ text: 'Kuchiba Chisa Emotion Engine' })
    .setTimestamp();

  await message.reply({ embeds: [embed], files: [bannerAttachment] });
}
