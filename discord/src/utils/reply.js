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

export function formatCoreResponse(responseText, emotions) {
  const lines = [responseText?.trim() ?? ''];

  if (emotions && typeof emotions === 'object') {
    const emotionLine = Object.entries(emotions)
      .map(([key, value]) => `${key}: ${Number(value).toFixed(2)}`)
      .join(' | ');

    if (emotionLine) {
      lines.push('');
      lines.push(`Cảm xúc hiện tại: ${emotionLine}`);
    }
  }

  return lines.join('\n');
}
