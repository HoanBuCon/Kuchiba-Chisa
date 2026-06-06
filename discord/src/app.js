import { env } from './config/env.js';
import { logger } from './config/logger.js';
import { createBotClient } from './bot/client.js';
import { loadCommands } from './bot/loadCommands.js';
import { loadEvents } from './bot/loadEvents.js';
import { ensureSchema, closePool, pool } from './database/pool.js';
import { DiscordUserRepository } from './repositories/discordUserRepository.js';
import { InteractionRepository } from './repositories/interactionRepository.js';
import { CoreRagClient } from './services/coreRagClient.js';
import { RateLimiter } from './services/rateLimiter.js';
import { PrefixCommandRunner } from './services/prefixCommandRunner.js';

let botClient = null;
let cleanupTimer = null;

export async function startApp() {
  await ensureSchema();

  botClient = createBotClient({ enablePrefix: env.discord.enablePrefix });
  const repositories = {
    users: new DiscordUserRepository(pool),
    interactions: new InteractionRepository(pool),
  };
  const rateLimiter = new RateLimiter(env.rateLimit);
  const coreRagClient = new CoreRagClient();

  botClient.services = {
    env,
    logger,
    config: {
      reply: env.reply,
    },
    rateLimiter,
    coreRagClient,
    prefixCommandRunner: new PrefixCommandRunner({
      logger,
      rateLimiter,
      repositories,
      coreRagClient,
      replyMaxChars: env.reply.maxChars,
    }),
    repositories,
  };

  await loadCommands(botClient);
  await loadEvents(botClient);

  cleanupTimer = setInterval(() => {
    botClient?.services?.rateLimiter?.pruneExpired();
  }, 5 * 60 * 1000);
  cleanupTimer.unref();

  const shutdown = async (signal) => {
    logger.info({ signal }, 'Shutting down Discord bot');
    if (cleanupTimer) {
      clearInterval(cleanupTimer);
    }
    try {
      botClient?.destroy();
    } catch (error) {
      logger.warn({ err: error }, 'Discord client destroy failed');
    }
    await closePool().catch((error) => {
      logger.warn({ err: error }, 'PostgreSQL pool close failed');
    });
    process.exit(0);
  };

  process.once('SIGINT', shutdown);
  process.once('SIGTERM', shutdown);

  await botClient.login(env.discord.token);
  logger.info('Discord bot login completed');

  return botClient;
}
