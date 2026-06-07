import { SlashCommandBuilder, EmbedBuilder } from 'discord.js';
import { readFile } from 'node:fs/promises';

export const data = new SlashCommandBuilder()
  .setName('help')
  .setDescription('Hiển thị bảng hướng dẫn sử dụng Bot Chisa')
  .setDMPermission(false);

async function loadHelpContent() {
  try {
    const filePath = new URL('../assets/help.md', import.meta.url);
    return await readFile(filePath, 'utf8');
  } catch (error) {
    return 'Không thể tải tệp hướng dẫn. Vui lòng liên hệ Admin.';
  }
}

export async function execute(client, interaction) {
  const content = await loadHelpContent();
  const embed = new EmbedBuilder()
    .setTitle('🌸 BẢNG HƯỚNG DẪN SỬ DỤNG CHISA BOT 🌸')
    .setDescription(content)
    .setColor('#ffb6c1')
    .setThumbnail(client.user.displayAvatarURL())
    .setTimestamp();

  await interaction.reply({ embeds: [embed] });
}

export async function executePrefix(client, message, argsText) {
  const content = await loadHelpContent();
  const embed = new EmbedBuilder()
    .setTitle('🌸 BẢNG HƯỚNG DẪN SỬ DỤNG CHISA BOT 🌸')
    .setDescription(content)
    .setColor('#ffb6c1')
    .setThumbnail(client.user.displayAvatarURL())
    .setTimestamp();

  await message.reply({ embeds: [embed] });
}
