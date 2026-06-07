export const name = 'ready';
export const once = true;

export async function execute(client) {
  const { logger } = client.services;
  logger.info({ user: client.user?.tag }, 'Discord bot ready');

  // Fetch application emojis
  try {
    const appEmojis = await client.application.emojis.fetch();
    logger.info({ count: appEmojis.size }, 'Fetched application emojis');
    client.services.emojis = appEmojis;
  } catch (error) {
    logger.warn({ err: error }, 'Could not fetch application emojis, falling back to guild emojis');
    client.services.emojis = client.emojis.cache;
  }

  // Load guild settings cache
  try {
    const settings = await client.services.repositories.guildSettings.getAllSettings();
    client.services.guildSettingsCache = new Map();
    for (const row of settings) {
      if (row.chisa_channel_id) {
        client.services.guildSettingsCache.set(row.chisa_channel_id, row.discord_guild_id);
      }
    }
    logger.info({ count: client.services.guildSettingsCache.size }, 'Guild settings cache loaded');
  } catch (error) {
    logger.error({ err: error }, 'Failed to load guild settings cache');
    client.services.guildSettingsCache = new Map();
  }

  if (client.user) {
    client.user.setPresence({
      activities: [
        {
          name: '/ask Chisa',
          type: 0,
        },
      ],
      status: 'online',
    });
  }
}
