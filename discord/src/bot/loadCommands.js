import { readdir } from 'node:fs/promises';

export async function loadCommands(client) {
  const commandsPath = new URL('../commands/', import.meta.url);
  const commandFiles = (await readdir(commandsPath, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.endsWith('.js'))
    .map((entry) => entry.name);

  for (const fileName of commandFiles) {
    const fileUrl = new URL(`../commands/${fileName}`, import.meta.url);
    const commandModule = await import(fileUrl.href);

    if (!commandModule.data || typeof commandModule.execute !== 'function') {
      throw new Error(`Invalid command module: ${fileName}`);
    }

    client.commands.set(commandModule.data.name, commandModule);
  }

  return client.commands;
}
