import { DEFAULT_COMMANDS, DEFAULT_PREFIX } from '../config/constants.js';
import { splitDiscordMessage } from '../utils/reply.js';

export class PrefixCommandRunner {
  constructor({ logger, rateLimiter, repositories, coreRagClient, replyMaxChars, prefix = DEFAULT_PREFIX, commands = DEFAULT_COMMANDS }) {
    this.logger = logger;
    this.rateLimiter = rateLimiter;
    this.repositories = repositories;
    this.coreRagClient = coreRagClient;
    this.replyMaxChars = replyMaxChars;
    this.prefix = prefix;
    this.commands = commands;
  }

  isPrefixCommand(message) {
    return Boolean(message?.guild && !message.author?.bot && message.content?.startsWith(this.prefix));
  }

  parse(message) {
    const raw = message.content.slice(this.prefix.length).trim();
    if (!raw) {
      return null;
    }

    const [commandNameRaw] = raw.split(/\s+/);
    const commandName = commandNameRaw.toLowerCase();
    const argsText = raw.slice(commandNameRaw.length).trim();

    return { commandName, argsText };
  }

  async handleMessage(message) {
    if (!this.isPrefixCommand(message)) {
      return false;
    }

    const parsed = this.parse(message);
    if (!parsed) {
      return true;
    }

    if (parsed.commandName === this.commands.ask) {
      await this.handleAsk(message, parsed.argsText);
      return true;
    }

    if (parsed.commandName === this.commands.clear) {
      await this.handleClear(message);
      return true;
    }

    return false;
  }

  async handleAsk(message, question) {
    const rateKey = `${message.author.id}:ask`;
    const rate = this.rateLimiter.allow(rateKey);

    if (!rate.allowed) {
      const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
      await message.reply(`Bạn đang gửi quá nhanh. Hãy chờ khoảng ${waitSeconds}s rồi thử lại.`);
      return;
    }

    if (!question) {
      await message.reply(`Dùng ${this.prefix}${this.commands.ask} <nội dung> để hỏi Chisa.`);
      return;
    }

    await message.channel.sendTyping().catch(() => {});

    const discordUser = await this.repositories.users.ensureDiscordUser({
      discordUserId: message.author.id,
      discordUserName: message.author.username,
      discordUserGlobalName: message.author.globalName ?? null,
      discordUserTag: message.author.tag ?? message.author.username,
    });

    const interactionId = await this.repositories.interactions.createInteraction({
      discordUserId: message.author.id,
      coreUserId: discordUser.core_user_id,
      discordUserName: message.author.username,
      discordUserGlobalName: message.author.globalName ?? null,
      discordUserTag: message.author.tag ?? message.author.username,
      discordGuildId: message.guildId ?? null,
      discordGuildName: message.guild?.name ?? null,
      discordChannelId: message.channelId,
      discordChannelName: message.channel?.name ?? null,
      discordMessageId: message.id,
      commandName: `${this.prefix}${this.commands.ask}`,
      userMessage: question,
      metadata: {
        source: 'discord',
        command: this.commands.ask,
        mode: 'prefix',
      },
    });

    try {
      await this.repositories.interactions.markCoreRequest(interactionId);

      const result = await this.coreRagClient.ask({
        coreUserId: discordUser.core_user_id,
        message: question,
      });

      await this.repositories.interactions.markSuccess(interactionId, {
        assistantMessage: result.response,
        metadata: {
          emotions: result.emotions,
          source: 'core-rag',
          mode: 'prefix',
        },
      });

      const chunks = splitDiscordMessage(result.response, this.replyMaxChars);
      await message.reply({ content: chunks[0] || 'Chisa chưa tạo được phản hồi.', allowedMentions: { repliedUser: false } });

      for (let index = 1; index < chunks.length; index += 1) {
        await message.channel.send(chunks[index]);
      }
    } catch (error) {
      this.logger.error({ err: error, userId: message.author.id, interactionId }, 'Discord prefix ask failed');
      await this.repositories.interactions.markFailure(interactionId, error instanceof Error ? error.message : String(error));
      await message.reply('Xin lỗi, Chisa không thể trả lời lúc này. Hãy thử lại sau ít phút.');
    }
  }

  async handleClear(message) {
    const rateKey = `${message.author.id}:clear`;
    const rate = this.rateLimiter.allow(rateKey);

    if (!rate.allowed) {
      const waitSeconds = Math.ceil((rate.resetAt - Date.now()) / 1000);
      await message.reply(`Bạn vừa dùng ${this.prefix}${this.commands.clear} quá nhanh. Hãy chờ khoảng ${waitSeconds}s rồi thử lại.`);
      return;
    }

    await message.channel.sendTyping().catch(() => {});

    const discordUser = await this.repositories.users.ensureDiscordUser({
      discordUserId: message.author.id,
      discordUserName: message.author.username,
      discordUserGlobalName: message.author.globalName ?? null,
      discordUserTag: message.author.tag ?? message.author.username,
    });

    const interactionId = await this.repositories.interactions.createInteraction({
      discordUserId: message.author.id,
      coreUserId: discordUser.core_user_id,
      discordUserName: message.author.username,
      discordUserGlobalName: message.author.globalName ?? null,
      discordUserTag: message.author.tag ?? message.author.username,
      discordGuildId: message.guildId ?? null,
      discordGuildName: message.guild?.name ?? null,
      discordChannelId: message.channelId,
      discordChannelName: message.channel?.name ?? null,
      discordMessageId: message.id,
      commandName: `${this.prefix}${this.commands.clear}`,
      userMessage: `${this.prefix}${this.commands.clear}`,
      status: 'clearing',
      metadata: {
        source: 'discord',
        command: this.commands.clear,
        mode: 'prefix',
      },
    });

    try {
      await this.coreRagClient.clearMemory(discordUser.core_user_id);
      await this.repositories.interactions.clearUserInteractions(discordUser.core_user_id, interactionId);
      await this.repositories.users.markCleared(discordUser.core_user_id);
      await this.repositories.interactions.markSuccess(interactionId, {
        assistantMessage: 'Memory cleared',
        metadata: {
          source: 'core-rag',
          command: this.commands.clear,
          mode: 'prefix',
        },
      });

      this.logger.info({ userId: message.author.id, coreUserId: discordUser.core_user_id }, 'Discord prefix memory cleared');
      await message.reply('Memory của bạn đã được xóa. Chisa sẽ bắt đầu lại từ đầu trong lần trò chuyện tiếp theo.');
    } catch (error) {
      this.logger.error({ err: error, userId: message.author.id }, 'Discord prefix clear failed');
      await this.repositories.interactions.markFailure(interactionId, error instanceof Error ? error.message : String(error));
      await message.reply('Không thể xóa memory lúc này. Hãy thử lại sau.');
    }
  }
}
