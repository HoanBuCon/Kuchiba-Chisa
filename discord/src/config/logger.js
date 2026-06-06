import pino from 'pino';
import { env } from './env.js';

const transport = env.isProd
  ? undefined
  : {
      target: 'pino-pretty',
      options: {
        colorize: true,
        translateTime: 'SYS:standard',
        ignore: 'pid,hostname',
      },
    };

export const logger = pino({
  level: process.env.DISCORD_LOG_LEVEL ?? (env.isProd ? 'info' : 'debug'),
  base: {
    service: 'discord-bot',
  },
  transport,
});
