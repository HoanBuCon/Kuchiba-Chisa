// Client for /api/v2 chat: SSE turns, server threads and citation links (CH-001, CONV-001).

const MAX_TITLE_CHARS = 22;

export function parseSseChunk(chunk) {
  let event = 'message';
  const dataLines = [];
  for (const line of chunk.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
  }
  return { event, data: dataLines.length ? JSON.parse(dataLines.join('\n')) : {} };
}

async function* readSseChunks(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    const parts = buffer.split('\n\n');
    buffer = parts.pop();
    yield* parts.filter((part) => part.trim());
  }
}

export function newTurnBody(message, threadId) {
  const body = { message, turn_id: crypto.randomUUID() };
  return threadId ? { ...body, thread_id: threadId } : body;
}

// A failed turn resolves with its voice constant, so it reads as Chisa and not as a crash.
export async function streamTurn({ base, accessToken, body, onStarted, onToken, fetchImpl = fetch }) {
  const response = await fetchImpl(`${base}/chat/turns`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'text/event-stream',
      authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

  for await (const chunk of readSseChunks(response.body)) {
    const { event, data } = parseSseChunk(chunk);
    if (event === 'turn.started') onStarted?.(data);
    if (event === 'token') onToken?.(data.delta ?? '');
    if (event === 'turn.completed') return data;
    if (event === 'turn.failed') return { response: data.message, status: 'failed', citations: [] };
  }
  throw new Error('Stream ended without a final event');
}

export function threadApi(base, accessToken, fetchImpl = fetch) {
  const request = async (path, options = {}) => {
    const response = await fetchImpl(`${base}${path}`, {
      ...options,
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${accessToken}`,
      },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.status === 204 ? null : response.json();
  };
  return {
    list: () => request('/threads'),
    turns: (id) => request(`/threads/${id}/turns`),
    rename: (id, title) =>
      request(`/threads/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
    remove: (id) => request(`/threads/${id}`, { method: 'DELETE' }),
  };
}

export function threadTitle(message) {
  return message.length > MAX_TITLE_CHARS ? `${message.slice(0, MAX_TITLE_CHARS)}...` : message;
}

export function toConversations(threads, untitled) {
  return threads.map((thread) => ({ id: thread.id, title: thread.title || untitled }));
}

export function turnsToMessages(turns, greeting) {
  if (!turns.length) return [greeting];
  return turns.flatMap((turn) => [
    { role: 'user', content: turn.question },
    { role: 'chisa', content: turn.answer, citations: turn.citations },
  ]);
}

function pageName(url) {
  const lastSegment = url.pathname.split('/').filter(Boolean).pop();
  return lastSegment ? decodeURIComponent(lastSegment).replace(/_/g, ' ') : url.hostname;
}

// Only web pages become links: stored values must never reach an href as another scheme.
export function citationLinks(citations = []) {
  const links = new Map();
  for (const citation of citations) {
    let url;
    try {
      url = new URL(citation.title_or_url);
    } catch {
      continue;
    }
    if (url.protocol === 'https:' || url.protocol === 'http:') {
      links.set(url.href, { href: url.href, label: pageName(url) });
    }
  }
  return [...links.values()];
}
