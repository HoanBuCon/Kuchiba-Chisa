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

const EMOTION_LABELS = {
  joy: 'Vui vẻ',
  sadness: 'Buồn bã',
  trust: 'Tin tưởng',
  irritation: 'Khó chịu',
  attachment: 'Gắn kết'
};

export function formatCoreResponse(responseText, emotions) {
  const lines = [responseText?.trim() ?? ''];

  if (emotions && typeof emotions === 'object') {
    const emotionLine = Object.entries(emotions)
      .filter(([_, value]) => value !== null && value !== undefined)
      .map(([key, value]) => `${EMOTION_LABELS[key] || key} (${Number(value).toFixed(2)})`)
      .join(' | ');

    if (emotionLine) {
      lines.push('');
      lines.push(`*[Cảm xúc: ${emotionLine}]*`);
    }
  }

  return lines.join('\n');
}
