import dotenv from 'dotenv';

dotenv.config();
try {
  dotenv.config({ path: new URL('../../.env', import.meta.url) });
} catch (_) {}

const required = (name) => {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
};

const parseBoolean = (value, fallback = false) => {
  if (value === undefined) {
    return fallback;
  }
  return ['1', 'true', 'yes', 'on'].includes(String(value).toLowerCase());
};

const parseInteger = (value, fallback) => {
  const parsed = Number.parseInt(String(value ?? fallback), 10);
  return Number.isNaN(parsed) ? fallback : parsed;
};

const parseCsv = (value) => {
  if (!value) {
    return [];
  }
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
};

const trimTrailingSlash = (value) => value.replace(/\/+$/, '');

export const env = {
  nodeEnv: process.env.NODE_ENV ?? 'development',
  discord: {
    token: required('DISCORD_TOKEN'),
    clientId: required('DISCORD_CLIENT_ID'),
    guildId: process.env.DISCORD_GUILD_ID ?? '',
    allowedChannelIds: parseCsv(process.env.DISCORD_ALLOWED_CHANNEL_IDS),
    enablePrefix: parseBoolean(process.env.DISCORD_ENABLE_PREFIX, true),
  },
  database: {
    url: required('DATABASE_URL'),
    ssl: parseBoolean(process.env.DATABASE_SSL, false),
  },
  coreRag: {
    baseUrl: trimTrailingSlash(process.env.CORE_RAG_BASE_URL ?? 'http://localhost:8000'),
    chatPath: process.env.CORE_RAG_CHAT_PATH ?? '/api/v1/chat',
    clearPathTemplate: process.env.CORE_RAG_CLEAR_PATH_TEMPLATE ?? '/api/v1/chat/clear/{user_id}',
    timeoutMs: parseInteger(process.env.CORE_RAG_TIMEOUT_MS, 60_000),
    retryCount: parseInteger(process.env.CORE_RAG_RETRY_COUNT, 0),
  },
  rateLimit: {
    windowMs: parseInteger(process.env.DISCORD_RATE_LIMIT_WINDOW_MS, 15_000),
    maxRequests: parseInteger(process.env.DISCORD_RATE_LIMIT_MAX_REQUESTS, 5),
  },
  reply: {
    maxChars: parseInteger(process.env.DISCORD_REPLY_MAX_CHARS, 1900),
  },
  isProd: process.env.NODE_ENV === 'production',
};

export { parseBoolean, parseInteger, parseCsv, required, trimTrailingSlash };
