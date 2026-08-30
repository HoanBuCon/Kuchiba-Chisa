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
    const channelSetting = message.guild ? client.services.guildSettingsCache?.get(message.channelId) : null;
    const isDirectChannel = Boolean(channelSetting);
    const isCommunityMode = channelSetting?.mode === 'community';

    // Direct chat in dedicated Guild channel OR 1-on-1 Direct Message (DM)
    if (isDM || isDirectChannel) {
      let rawContent = message.content?.trim() || '';
      const lowerContent = rawContent.toLowerCase();
      const prefix = (runner.prefix || 'c!').toLowerCase();

      // Common bot command prefixes: c!, !, /, $, %, ++, ;;, -, ?, ., ~, &, >
      const COMMON_BOT_PREFIXES = ['c!', '!', '/', '$', '%', '++', ';;', '-', '?', '.', '~', '&', '>'];
      if (
        COMMON_BOT_PREFIXES.some((p) => lowerContent.startsWith(p)) ||
        runner.isPrefixCommand(message)
      ) {
        if (!rawContent.startsWith('...') && !rawContent.startsWith('?!')) {
          return;
        }
      }

      // In Community Mode: ONLY reply if user mentions Chisa or replies to Chisa's message
      if (isCommunityMode) {
        const botId = client.user?.id;
        const mentionsBot = botId ? message.mentions.users.has(botId) : false;

        let repliesToBot = false;
        if (message.reference && botId) {
          if (message.mentions?.repliedUser?.id === botId) {
            repliesToBot = true;
          } else {
            try {
              const refMsg = await message.fetchReference();
              if (refMsg?.author?.id === botId) {
                repliesToBot = true;
              }
            } catch {
              // Ignore fetch error
            }
          }
        }

        if (!mentionsBot && !repliesToBot) {
          // Do not reply in community mode if not mentioned or replied to Chisa
          return;
        }

        // Clean @bot mention tag from rawContent for clean prompt
        if (botId) {
          const mentionRegex = new RegExp(`<@!?${botId}>`, 'g');
          rawContent = rawContent.replace(mentionRegex, '').trim();
        }
      }

      // Convert any other user mentions <@UserID> to clean @DisplayName
      if (message.guild && message.mentions?.users?.size > 0) {
        message.mentions.users.forEach((u) => {
          if (u.id !== client.user?.id) {
            const member = message.guild.members?.cache?.get(u.id);
            const name = member?.displayName || u.globalName || u.username;
            const userMentionRegex = new RegExp(`<@!?${u.id}>`, 'g');
            rawContent = rawContent.replace(userMentionRegex, `@${name}`);
          }
        });
      }

      if (!rawContent) {
        return;
      }

      // Process as a natural conversation query directly to Chisa
      const askCommand = client.commands.get('ask');
      if (askCommand && typeof askCommand.executePrefix === 'function') {
        let resolvedGuildId = 'DM';
        if (!isDM) {
          if (channelSetting?.mode === 'private') {
            // Mode private: Completely isolated from other channels in the server
            resolvedGuildId = `CHANNEL_${message.channelId}`;
          } else {
            // Mode semi-private & community: Shared server context and memory
            resolvedGuildId = message.guildId || 'DM';
          }
        }

        const discordUser = await client.services.repositories.users.ensureDiscordUser({
          discordUserId: message.author.id,
          discordGuildId: resolvedGuildId,
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
