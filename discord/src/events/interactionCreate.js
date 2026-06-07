export const name = 'interactionCreate';
export const once = false;

export async function execute(client, interaction) {
  if (!interaction.isChatInputCommand()) {
    return;
  }

  const command = client.commands.get(interaction.commandName);
  if (!command) {
    await interaction.reply({
      content: 'Lệnh này chưa được đăng ký trong bot.',
      ephemeral: true,
    });
    return;
  }

  try {
    const discordUser = await client.services.repositories.users.ensureDiscordUser({
      discordUserId: interaction.user.id,
      discordGuildId: interaction.guildId || 'DM',
      discordUserName: interaction.user.username,
      discordUserGlobalName: interaction.user.globalName ?? null,
      discordUserTag: interaction.user.tag ?? interaction.user.username,
    });

    await command.execute(client, interaction, discordUser);
  } catch (error) {
    client.services.logger.error(
      { err: error, commandName: interaction.commandName, userId: interaction.user?.id },
      'Discord command dispatcher failed',
    );

    const fallback = 'Bot gặp lỗi khi xử lý lệnh này.';
    if (interaction.deferred || interaction.replied) {
      await interaction.editReply({ content: fallback });
    } else {
      await interaction.reply({ content: fallback, ephemeral: true });
    }
  }
}
