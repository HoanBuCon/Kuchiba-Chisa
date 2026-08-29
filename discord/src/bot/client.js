import { Client, Collection, GatewayIntentBits, Partials } from 'discord.js';

export function createBotClient({ enablePrefix = true } = {}) {
  const intents = [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.DirectMessages,
    GatewayIntentBits.MessageContent,
  ];

  const client = new Client({
    intents,
    partials: [Partials.Channel, Partials.Message],
  });

  client.commands = new Collection();
  client.services = {};

  return client;
}
