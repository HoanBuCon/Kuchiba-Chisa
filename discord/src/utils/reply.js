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

export function getDynamicEmotionEmoji(key, value) {
  const v = Number(value) || 0;
  switch (key) {
    case 'trust':
      if (v < 0.35) return '✋';
      if (v <= 0.75) return '🤝';
      return '🛡️';
    case 'attachment':
      if (v < 0.45) return '🌸';
      if (v <= 0.70) return '💗';
      return '💖';
    case 'shyness':
      if (v < 0.25) return '😶';
      if (v <= 0.55) return '😳';
      return '🙈';
    case 'curiosity':
      if (v < 0.40) return '🔍';
      if (v <= 0.70) return '🔎';
      return '💡';
    case 'comfort':
      if (v < 0.40) return '🍃';
      if (v <= 0.70) return '🍵';
      return '🕊️';
    case 'joy':
      if (v < 0.30) return '🙂';
      if (v <= 0.60) return '😊';
      return '🥰';
    case 'sadness':
      if (v < 0.40) return '💧';
      if (v <= 0.70) return '🥺';
      return '🌧️';
    case 'irritation':
      if (v < 0.40) return '😾';
      if (v <= 0.70) return '😤';
      return '💢';
    default:
      return '💬';
  }
}

const CANONICAL_EMOTION_ORDER = [
  'trust',
  'attachment',
  'shyness',
  'curiosity',
  'comfort',
  'joy',
  'sadness',
  'irritation',
];

const EMOTION_LABELS = {
  trust: { label: 'Tin tưởng' },
  attachment: { label: 'Gắn bó' },
  shyness: { label: 'Ngại ngùng' },
  curiosity: { label: 'Hiếu kỳ' },
  comfort: { label: 'Bình yên' },
  joy: { label: 'Vui vẻ' },
  sadness: { label: 'Buồn bã' },
  irritation: { label: 'Khó chịu' },
};

export function formatCoreResponse(responseText, emotions, client) {
  const lines = [responseText?.trim() ?? ''];

  if (emotions && typeof emotions === 'object') {
    const emotionLines = [];
    for (const key of CANONICAL_EMOTION_ORDER) {
      if (emotions[key] !== null && emotions[key] !== undefined) {
        const value = emotions[key];
        const info = EMOTION_LABELS[key] || { label: key };
        const dynamicEmoji = getDynamicEmotionEmoji(key, value);
        const customEmoji = getCustomEmoji(client, key);
        const emojiStr = customEmoji || dynamicEmoji;
        let percent = Math.round(Number(value) * 100);
        if (percent > 100) percent = 100;
        if (percent < 0) percent = 0;
        emotionLines.push(`${emojiStr} ${info.label}: ${percent}%`);
      }
    }

    for (const [key, value] of Object.entries(emotions)) {
      if (!CANONICAL_EMOTION_ORDER.includes(key) && value !== null && value !== undefined) {
        const info = EMOTION_LABELS[key] || { label: key };
        const dynamicEmoji = getDynamicEmotionEmoji(key, value);
        const customEmoji = getCustomEmoji(client, key);
        const emojiStr = customEmoji || dynamicEmoji;
        let percent = Math.round(Number(value) * 100);
        if (percent > 100) percent = 100;
        if (percent < 0) percent = 0;
        emotionLines.push(`${emojiStr} ${info.label}: ${percent}%`);
      }
    }

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
