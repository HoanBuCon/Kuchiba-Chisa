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
        if (error.status && error.status >= 400 && error.status < 500) {
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

  async ask({ coreUserId, message, username, channelName, guildName } = {}) {
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
      }),
    });

    return {
      response: payload.response ?? '',
      emotions: payload.emotions ?? null,
      loopThinkingActivated: payload.loop_thinking_activated ?? false,
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
}
