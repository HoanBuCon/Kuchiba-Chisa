export const name = 'messageCreate';
export const once = false;

export async function execute(client, message) {
  const runner = client.services.prefixCommandRunner;
  if (!runner) {
    return;
  }

  try {
    const handled = await runner.handleMessage(message);
    if (handled) {
      return;
    }

    // Direct chat channel feature
    if (message.guild && !message.author?.bot) {
      const isDirectChannel = client.services.guildSettingsCache?.has(message.channelId);
      if (isDirectChannel) {
        // If message starts with '!', do not respond
        if (message.content?.trim().startsWith('!')) {
          return;
        }

        // Otherwise, process as an ask query directly
        const askCommand = client.commands.get('ask');
        if (askCommand && typeof askCommand.executePrefix === 'function') {
          const discordUser = await client.services.repositories.users.ensureDiscordUser({
            discordUserId: message.author.id,
            discordGuildId: message.guildId || 'DM',
            discordUserName: message.author.username,
            discordUserGlobalName: message.author.globalName ?? null,
            discordUserTag: message.author.tag ?? message.author.username,
          });

          await askCommand.executePrefix(client, message, message.content.trim(), discordUser);
        }
      }
    }
  } catch (error) {
    client.services.logger.error(
      { err: error, userId: message.author?.id, channelId: message.channelId },
      'Discord message dispatcher failed',
    );

    const isPrefix = message.content?.trim().startsWith(runner.prefix);
    if (isPrefix && message.channel?.send) {
      await message.channel.send('Bot gặp lỗi khi xử lý lệnh này.');
    }
  }
}
