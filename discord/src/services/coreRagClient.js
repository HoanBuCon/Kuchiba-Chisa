import { env } from '../config/env.js';
import { logger } from '../config/logger.js';
import crypto from 'node:crypto';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const encodeJwtPart = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');

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

  createWorkloadToken({ subjectId, tenantId = null, channelId = null, displayName = null, scopes }) {
    const now = Math.floor(Date.now() / 1000);
    const header = encodeJwtPart({ alg: 'HS256', typ: 'JWT' });
    const payload = encodeJwtPart({
      sub: subjectId,
      tenant_id: tenantId,
      channel_id: channelId,
      display_name: displayName,
      scopes,
      source: 'discord',
      token_use: 'workload',
      iss: env.coreRag.workloadJwtIssuer,
      aud: env.coreRag.workloadJwtAudience,
      iat: now,
      exp: now + 120,
    });
    const signature = crypto
      .createHmac('sha256', env.coreRag.workloadJwtSecret)
      .update(`${header}.${payload}`)
      .digest('base64url');
    return `${header}.${payload}.${signature}`;
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

  async ask({ coreUserId, guildId = null, channelId = null, message, username, channelName, guildName, images = [], isEphemeralReference = false } = {}) {
    const url = this.buildUrl(this.chatPath);
    const workloadToken = this.createWorkloadToken({
      subjectId: coreUserId,
      tenantId: guildId,
      channelId,
      displayName: username,
      scopes: ['chat:write'],
    });
    const payload = await this.requestJson(url, {
      method: 'POST',
      headers: { authorization: `Bearer ${workloadToken}` },
      body: JSON.stringify({
        message,
        images,
        is_ephemeral_reference: isEphemeralReference,
      }),
    });

    return {
      response: payload.response ?? '',
      emotions: payload.emotions ?? null,
      loopThinkingActivated: payload.loop_thinking_activated ?? false,
      imagesProcessed: payload.images_processed ?? [],
      attachedImages: payload.attached_images ?? [],
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
    const workloadToken = this.createWorkloadToken({
      subjectId: coreUserId,
      tenantId: guildId,
      channelId,
      displayName: username,
      scopes: ['community:write'],
    });
    const payload = await this.requestJson(url, {
      method: 'POST',
      headers: { authorization: `Bearer ${workloadToken}` },
      body: JSON.stringify({
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
      imagesProcessed: payload.images_processed ?? [],
      attachedImages: payload.attached_images ?? [],
      raw: payload,
    };
  }

  async clearMemory(coreUserId, { guildId = null, channelId = null, scopes = ['chat:clear'] } = {}) {
    const path = this.clearPathTemplate.replace('{user_id}', encodeURIComponent(coreUserId));
    const url = this.buildUrl(path);
    const workloadToken = this.createWorkloadToken({
      subjectId: coreUserId,
      tenantId: guildId,
      channelId,
      scopes,
    });
    const payload = await this.requestJson(url, {
      method: 'DELETE',
      headers: { authorization: `Bearer ${workloadToken}` },
    });

    return payload;
  }

  async clearCommunityMemory({ guildId, scope = 'all', channelId, coreUserId } = {}) {
    let queryParams = `scope=${encodeURIComponent(scope)}`;
    if (channelId) queryParams += `&channel_id=${encodeURIComponent(channelId)}`;
    if (coreUserId) queryParams += `&user_id=${encodeURIComponent(coreUserId)}`;
    const url = this.buildUrl(`/api/v1/community/clear/${encodeURIComponent(guildId)}?${queryParams}`);
    const workloadToken = this.createWorkloadToken({
      subjectId: coreUserId ?? 'discord-guild-admin',
      tenantId: guildId,
      channelId: channelId ?? null,
      scopes: [scope === 'all' ? 'community:clear:any' : 'community:clear:self'],
    });
    const payload = await this.requestJson(url, {
      method: 'DELETE',
      headers: { authorization: `Bearer ${workloadToken}` },
    });

    return payload;
  }
}
