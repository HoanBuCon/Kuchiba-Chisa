import 'dotenv/config';
import { readdir } from 'node:fs/promises';
import { REST } from '@discordjs/rest';
import { Routes } from 'discord-api-types/v10';
import { env } from '../src/config/env.js';

const DISCORD_SNOWFLAKE_RE = /^\d{17,20}$/;

async function loadCommandPayloads() {
  const commandDir = new URL('../src/commands/', import.meta.url);
  const files = (await readdir(commandDir, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.endsWith('.js'))
    .map((entry) => entry.name);

  const commands = [];
  for (const fileName of files) {
    const moduleUrl = new URL(`../src/commands/${fileName}`, import.meta.url);
    const commandModule = await import(moduleUrl.href);
    commands.push(commandModule.data.toJSON());
  }

  return commands;
}

async function main() {
  const commands = await loadCommandPayloads();
  const rest = new REST({ version: '10' }).setToken(env.discord.token);
  const guildId = env.discord.guildId?.trim();
  const isValidGuildId = Boolean(guildId && DISCORD_SNOWFLAKE_RE.test(guildId));

  if (isValidGuildId) {
    await rest.put(
      Routes.applicationGuildCommands(env.discord.clientId, guildId),
      { body: commands },
    );
    console.log(`Registered ${commands.length} guild commands for ${guildId}`);
    return;
  }

  if (guildId) {
    console.warn(`DISCORD_GUILD_ID is invalid (${guildId}); falling back to global slash commands.`);
  }

  await rest.put(Routes.applicationCommands(env.discord.clientId), { body: commands });
  console.log(`Registered ${commands.length} global commands`);
}

main().catch((error) => {
  console.error('Failed to register Discord commands:', error);
  process.exit(1);
});
