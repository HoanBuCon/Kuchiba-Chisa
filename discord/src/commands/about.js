import { SlashCommandBuilder, EmbedBuilder, AttachmentBuilder, InteractionContextType } from 'discord.js';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const bannerUrl = new URL('../assets/img/chisa_banner.jpg', import.meta.url);
const bannerPath = fileURLToPath(bannerUrl);

export const data = new SlashCommandBuilder()
  .setName('about')
  .setDescription('Giới thiệu về Bot Kuchiba Chisa')
  .setContexts(InteractionContextType.Guild);

async function loadAboutContent() {
  try {
    const filePath = new URL('../assets/docs/about.md', import.meta.url);
    return await readFile(filePath, 'utf8');
  } catch (error) {
    return 'Không thể tải tệp giới thiệu. Vui lòng liên hệ Admin.';
  }
}

export async function execute(client, interaction) {
  const content = await loadAboutContent();
  const bannerAttachment = new AttachmentBuilder(bannerPath, { name: 'chisa_banner.jpg' });

  const embed = new EmbedBuilder()
    .setTitle('🌸 GIỚI THIỆU VỀ KUCHIBA CHISA 🌸')
    .setDescription(content)
    .setColor('#ffb6c1')
    .setImage('attachment://chisa_banner.jpg')
    .setFooter({ text: 'Kuchiba Chisa' })
    .setTimestamp();

  await interaction.reply({ embeds: [embed], files: [bannerAttachment] });
}

export async function executePrefix(client, message, argsText) {
  const content = await loadAboutContent();
  const bannerAttachment = new AttachmentBuilder(bannerPath, { name: 'chisa_banner.jpg' });

  const embed = new EmbedBuilder()
    .setTitle('🌸 GIỚI THIỆU VỀ KUCHIBA CHISA AI 🌸')
    .setDescription(content)
    .setColor('#ffb6c1')
    .setImage('attachment://chisa_banner.jpg')
    .setFooter({ text: 'Kuchiba Chisa' })
    .setTimestamp();

  await message.reply({ embeds: [embed], files: [bannerAttachment] });
}
