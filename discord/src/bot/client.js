import { Client, Collection, GatewayIntentBits } from 'discord.js';

export function createBotClient({ enablePrefix = true } = {}) {
  const intents = [GatewayIntentBits.Guilds];

  if (enablePrefix) {
    intents.push(
      GatewayIntentBits.GuildMessages,
      GatewayIntentBits.MessageContent,
    );
  }

  const client = new Client({
    intents,
  });

  client.commands = new Collection();
  client.services = {};

  return client;
}
