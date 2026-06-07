import { DEFAULT_PREFIX } from '../config/constants.js';

export class PrefixCommandRunner {
  constructor({ client, prefix = DEFAULT_PREFIX }) {
    this.client = client;
    this.prefix = prefix;
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

    // Look up command dynamically from client.commands Map
    const command = this.client.commands.get(parsed.commandName);
    if (command && typeof command.executePrefix === 'function') {
      const discordUser = await this.client.services.repositories.users.ensureDiscordUser({
        discordUserId: message.author.id,
        discordGuildId: message.guildId || 'DM',
        discordUserName: message.author.username,
        discordUserGlobalName: message.author.globalName ?? null,
        discordUserTag: message.author.tag ?? message.author.username,
      });

      await command.executePrefix(this.client, message, parsed.argsText, discordUser);
      return true;
    }

    return false;
  }
}
