import { env } from '../config/env.js';
import { logger } from '../config/logger.js';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export class CoreRagClient {
  constructor() {
    this.baseUrl = env.coreRag.baseUrl;
    this.chatPath = env.coreRag.chatPath;
    this.clearPathTemplate = env.coreRag.clearPathTemplate;
    this.timeoutMs = env.coreRag.timeoutMs;
    this.retryCount = env.coreRag.retryCount;
  }

  buildUrl(pathname) {
    return new URL(pathname, this.baseUrl).toString();
  }

  async requestJson(url, options, { retries = this.retryCount } = {}) {
    let lastError = null;

    for (let attempt = 0; attempt <= retries; attempt += 1) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

      try {
        const response = await fetch(url, {
          ...options,
          signal: controller.signal,
          headers: {
            'content-type': 'application/json',
            ...(options.headers ?? {}),
          },
        });

        const rawText = await response.text();
        let payload = null;
        if (rawText) {
          try {
            payload = JSON.parse(rawText);
          } catch {
            payload = { raw: rawText };
          }
        }

        if (!response.ok) {
          const error = new Error(`Core RAG request failed with status ${response.status}`);
          error.status = response.status;
          error.payload = payload;
          throw error;
        }

        return payload ?? {};
      } catch (error) {
        lastError = error;
        if (error.status && ((error.status >= 400 && error.status < 500) || error.status === 503)) {
          throw error;
        }
        const isLastAttempt = attempt >= retries;
        if (isLastAttempt) {
          break;
        }
        logger.warn({ err: error, attempt: attempt + 1 }, 'Core RAG request failed, retrying');
        await sleep(400 * (attempt + 1));
      } finally {
        clearTimeout(timeout);
      }
    }

    throw lastError;
  }

  async ask({ coreUserId, message, username, channelName, guildName, images = [], isEphemeralReference = false } = {}) {
    const url = this.buildUrl(this.chatPath);
    const payload = await this.requestJson(url, {
      method: 'POST',
      body: JSON.stringify({
        user_id: coreUserId,
        message,
        source: 'discord',
        username,
        channel_name: channelName,
        guild_name: guildName,
        images,
        is_ephemeral_reference: isEphemeralReference,
      }),
    });

    return {
      response: payload.response ?? '',
      emotions: payload.emotions ?? null,
      loopThinkingActivated: payload.loop_thinking_activated ?? false,
      imagesProcessed: payload.images_processed ?? [],
      raw: payload,
    };
  }

  async askCommunity({
    channelId,
    guildId,
    channelName,
    guildName,
    coreUserId,
    username,
    message,
    recentMessages = [],
    images = [],
    isEphemeralReference = false,
  } = {}) {
    const url = this.buildUrl('/api/v1/community/chat');
    const payload = await this.requestJson(url, {
      method: 'POST',
      body: JSON.stringify({
        channel_id: channelId,
        guild_id: guildId ?? null,
        channel_name: channelName || 'general',
        guild_name: guildName ?? null,
        user_id: coreUserId,
        username,
        message,
        recent_messages: recentMessages,
        images,
        is_ephemeral_reference: isEphemeralReference,
      }),
    });

    return {
      response: payload.response ?? '',
      emotions: payload.emotions ?? null,
      sentiment: payload.sentiment ?? null,
      raw: payload,
    };
  }

  async clearMemory(coreUserId) {
    const path = this.clearPathTemplate.replace('{user_id}', encodeURIComponent(coreUserId));
    const url = this.buildUrl(path);
    const payload = await this.requestJson(url, {
      method: 'DELETE',
    });

    return payload;
  }

  async clearCommunityMemory({ guildId, scope = 'all', channelId, coreUserId } = {}) {
    let queryParams = `scope=${encodeURIComponent(scope)}`;
    if (channelId) queryParams += `&channel_id=${encodeURIComponent(channelId)}`;
    if (coreUserId) queryParams += `&user_id=${encodeURIComponent(coreUserId)}`;
    const url = this.buildUrl(`/api/v1/community/clear/${encodeURIComponent(guildId)}?${queryParams}`);
    const payload = await this.requestJson(url, {
      method: 'DELETE',
    });

    return payload;
  }
}
