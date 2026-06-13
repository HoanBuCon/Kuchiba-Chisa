export function splitDiscordMessage(text, maxLength = 1900) {
  if (!text || text.length <= maxLength) {
    return [text ?? ''];
  }

  const chunks = [];
  let remaining = text;

  while (remaining.length > maxLength) {
    let splitIndex = remaining.lastIndexOf('\n', maxLength);
    if (splitIndex < Math.floor(maxLength * 0.6)) {
      splitIndex = remaining.lastIndexOf(' ', maxLength);
    }
    if (splitIndex < Math.floor(maxLength * 0.6)) {
      splitIndex = maxLength;
    }

    chunks.push(remaining.slice(0, splitIndex).trim());
    remaining = remaining.slice(splitIndex).trim();
  }

  if (remaining) {
    chunks.push(remaining);
  }

  return chunks.filter(Boolean);
}

export function getCustomEmoji(client, name) {
  if (!client || !client.services || !client.services.emojis) return null;
  const emoji = client.services.emojis.find((e) =>
    e.name.toLowerCase() === name.toLowerCase() ||
    e.name.toLowerCase() === `chisa_${name.toLowerCase()}`
  );
  return emoji ? `<:${emoji.name}:${emoji.id}>` : null;
}

const EMOTION_LABELS = {
  joy: { label: 'Vui vẻ', emoji: '💖' },
  sadness: { label: 'Buồn bã', emoji: '💧' },
  trust: { label: 'Tin tưởng', emoji: '🤝' },
  irritation: { label: 'Khó chịu', emoji: '💢' },
  attachment: { label: 'Gắn bó', emoji: '🌸' }
};

export function formatCoreResponse(responseText, emotions, client) {
  const lines = [responseText?.trim() ?? ''];

  if (emotions && typeof emotions === 'object') {
    const emotionLines = Object.entries(emotions)
      .filter(([_, value]) => value !== null && value !== undefined)
      .map(([key, value]) => {
        const info = EMOTION_LABELS[key] || { label: key, emoji: '💬' };
        const customEmoji = getCustomEmoji(client, key);
        const emojiStr = customEmoji || info.emoji;
        let percent = Math.round(Number(value) * 100);
        if (percent > 100) percent = 100;
        if (percent < 0) percent = 0;
        return `${emojiStr} ${info.label}: ${percent}%`;
      });

    if (emotionLines.length > 0) {
      lines.push('');
      lines.push('**[Trạng thái Cảm xúc]**');
      lines.push('```');
      lines.push(emotionLines.join('\n'));
      lines.push('```');
    }
  }

  return lines.join('\n');
}

export async function replyWithChunks(context, text, emotions, client) {
  const isInteraction = typeof context.editReply === 'function';
  const formatted = formatCoreResponse(text, emotions, client);
  const chunks = splitDiscordMessage(formatted, client.services.config?.reply?.maxChars ?? 1900);

  if (isInteraction) {
    await context.editReply({ content: chunks[0] || 'Chisa chưa tạo được phản hồi.' });
    for (let i = 1; i < chunks.length; i += 1) {
      await context.followUp({ content: chunks[i] });
    }
  } else {
    await context.reply({ content: chunks[0] || 'Chisa chưa tạo được phản hồi.', allowedMentions: { repliedUser: false } });
    for (let i = 1; i < chunks.length; i += 1) {
      await context.channel.send(chunks[i]);
    }
  }
}
