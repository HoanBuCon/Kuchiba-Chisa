import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { readFile } from 'node:fs/promises';

export const data = new SlashCommandBuilder()
  .setName('docs')
  .setDescription('Hiển thị tài liệu chi tiết về hệ thống cảm xúc của Chisa')
  .setDMPermission(false);

async function loadDocsContent() {
  try {
    const filePath = new URL('../assets/emotion_docs.md', import.meta.url);
    return await readFile(filePath, 'utf8');
  } catch (error) {
    return 'Không thể tải tệp tài liệu cảm xúc. Vui lòng liên hệ Admin.';
  }
}

export async function execute(client, interaction) {
  const content = await loadDocsContent();
  const embed = new EmbedBuilder()
    .setTitle('🌸 TÀI LIỆU HỆ THỐNG CẢM XÚC 🌸')
    .setDescription(content)
    .setColor('#ba68c8')
    .setThumbnail(client.user.displayAvatarURL())
    .setFooter({ text: 'Kuchiba Chisa Emotion Engine 2.0 • Startorch Academy' })
    .setTimestamp();

  await interaction.reply({ embeds: [embed] });
}

export async function executePrefix(client, message, argsText) {
  const content = await loadDocsContent();
  const embed = new EmbedBuilder()
    .setTitle('🌸 TÀI LIỆU HỆ THỐNG CẢM XÚC 🌸')
    .setDescription(content)
    .setColor('#ba68c8')
    .setThumbnail(client.user.displayAvatarURL())
    .setFooter({ text: 'Kuchiba Chisa Emotion Engine • Startorch Academy' })
    .setTimestamp();

  await message.reply({ embeds: [embed] });
}
