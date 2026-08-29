export const name = 'messageCreate';
export const once = false;

export async function execute(client, message) {
  const runner = client.services.prefixCommandRunner;
  if (!runner || message.author?.bot) {
    return;
  }

  try {
    const handled = await runner.handleMessage(message);
    if (handled) {
      return;
    }

    const isDM = !message.guild;
    const isDirectChannel = message.guild && client.services.guildSettingsCache?.has(message.channelId);

    // Direct chat in dedicated Guild channel OR 1-on-1 Direct Message (DM)
    if (isDM || isDirectChannel) {
      const rawContent = message.content?.trim() || '';
      const lowerContent = rawContent.toLowerCase();
      const prefix = (runner.prefix || 'c!').toLowerCase();

      // If message starts with '!', 'c!', configured prefix, or is any prefix command, do not double-process
      if (
        rawContent.startsWith('!') ||
        lowerContent.startsWith('c!') ||
        lowerContent.startsWith(prefix) ||
        runner.isPrefixCommand(message)
      ) {
        return;
      }

      if (!rawContent) {
        return;
      }

      // Process as a natural conversation query directly to Chisa
      const askCommand = client.commands.get('ask');
      if (askCommand && typeof askCommand.executePrefix === 'function') {
        const discordUser = await client.services.repositories.users.ensureDiscordUser({
          discordUserId: message.author.id,
          discordGuildId: isDM ? 'DM' : (message.guildId || 'DM'),
          discordUserName: message.author.username,
          discordUserGlobalName: message.author.globalName ?? null,
          discordUserTag: message.author.tag ?? message.author.username,
        });

        await askCommand.executePrefix(client, message, rawContent, discordUser);
      }
    }
  } catch (error) {
    client.services.logger.error(
      { err: error, userId: message.author?.id, channelId: message.channelId, isDM: !message.guild },
      'Discord message dispatcher failed',
    );

    const isPrefix = message.content?.trim().startsWith(runner.prefix);
    if (isPrefix && message.channel?.send) {
      await message.channel.send('Bot gặp lỗi khi xử lý lệnh này.');
    }
  }
}
