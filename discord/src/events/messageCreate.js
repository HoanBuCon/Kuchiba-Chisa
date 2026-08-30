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

      // 1. Extract direct valid image attachments
      const directImages = [];
      if (message.attachments && message.attachments.size > 0) {
        message.attachments.forEach((att) => {
          const ct = (att.contentType || '').toLowerCase();
          const isImg = ct.startsWith('image/') || /\.(png|jpe?g|webp|gif)$/i.test(att.name || '');
          if (isImg && att.url) {
            directImages.push(att.url);
          }
        });
      }

      let isEphemeralReference = false;

      // In Community Mode: ONLY reply if user mentions Chisa or replies to Chisa's message
      if (isCommunityMode) {
        const botId = client.user?.id;
        const mentionsBot = botId ? message.mentions.users.has(botId) : false;

        let repliesToBot = false;
        let refImages = [];
        let refAuthorName = null;
        let refContent = null;

        if (message.reference) {
          try {
            const refMsg = await message.fetchReference();
            if (refMsg) {
              if (botId && refMsg.author?.id === botId) {
                repliesToBot = true;
              } else {
                // User is replying to another user's message in the community channel
                const authorMember = message.guild?.members?.cache?.get(refMsg.author?.id);
                refAuthorName = authorMember?.displayName || refMsg.author?.globalName || refMsg.author?.username || 'Thành viên';
                refContent = refMsg.content?.trim() || '';

                if (refMsg.attachments && refMsg.attachments.size > 0) {
                  refMsg.attachments.forEach((att) => {
                    const ct = (att.contentType || '').toLowerCase();
                    const isImg = ct.startsWith('image/') || /\.(png|jpe?g|webp|gif)$/i.test(att.name || '');
                    if (isImg && att.url) {
                      refImages.push(att.url);
                    }
                  });
                }
              }
            }
          } catch {
            // Ignore fetch error
          }
        }

        if (!mentionsBot && !repliesToBot) {
          // Do not reply in community mode if not mentioned or replied to Chisa
          return;
        }

        // Community Reply Reference: If user replied to another member's image and tagged Chisa
        if (refImages.length > 0 && directImages.length === 0) {
          directImages.push(...refImages);
          isEphemeralReference = true;
          if (refAuthorName) {
            const refPrefix = `[Đang trả lời ảnh của @${refAuthorName}${refContent ? `: "${refContent}"` : ''}] `;
            rawContent = rawContent ? `${refPrefix}${rawContent}` : `${refPrefix}Em hãy xem và phân tích bức ảnh này giúp Senpai nhé.`;
          }
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

      // If user sent image without text, provide a natural default query
      if (!rawContent) {
        if (directImages.length > 0) {
          rawContent = 'Em hãy xem và phân tích bức ảnh này giúp Senpai nhé.';
        } else {
          return;
        }
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

        await askCommand.executePrefix(client, message, rawContent, discordUser, {
          images: directImages,
          isEphemeralReference,
        });
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
