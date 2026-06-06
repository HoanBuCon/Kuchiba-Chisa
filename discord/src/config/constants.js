export const DEFAULT_COMMANDS = {
  ask: process.env.DISCORD_COMMAND_NAME_ASK ?? 'ask',
  clear: process.env.DISCORD_COMMAND_NAME_CLEAR ?? 'clear',
};

export const DEFAULT_PREFIX = process.env.DISCORD_PREFIX ?? 'c!';

export const DEFAULT_RATE_LIMIT = {
  windowMs: Number.parseInt(process.env.DISCORD_RATE_LIMIT_WINDOW_MS ?? '15000', 10),
  maxRequests: Number.parseInt(process.env.DISCORD_RATE_LIMIT_MAX_REQUESTS ?? '5', 10),
};

export const DEFAULT_REPLY_MAX_CHARS = Number.parseInt(process.env.DISCORD_REPLY_MAX_CHARS ?? '1900', 10);
