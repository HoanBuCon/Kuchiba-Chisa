import { readdir } from 'node:fs/promises';

export async function loadEvents(client) {
  const eventsPath = new URL('../events/', import.meta.url);
  const eventFiles = (await readdir(eventsPath, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.endsWith('.js'))
    .map((entry) => entry.name);

  for (const fileName of eventFiles) {
    const fileUrl = new URL(`../events/${fileName}`, import.meta.url);
    const eventModule = await import(fileUrl.href);

    if (typeof eventModule.execute !== 'function' || !eventModule.name) {
      throw new Error(`Invalid event module: ${fileName}`);
    }

    if (eventModule.once) {
      client.once(eventModule.name, (...args) => eventModule.execute(client, ...args));
    } else {
      client.on(eventModule.name, (...args) => eventModule.execute(client, ...args));
    }
  }
}
