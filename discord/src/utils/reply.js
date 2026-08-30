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

export function getEmotionStatusSummary(emotions = {}) {
  const trust = Number(emotions.trust || 0);
  const attachment = Number(emotions.attachment || 0);
  const shyness = Number(emotions.shyness || 0);
  const curiosity = Number(emotions.curiosity !== undefined ? emotions.curiosity : 0.20);
  const comfort = Number(emotions.comfort !== undefined ? emotions.comfort : 0.50);
  const joy = Number(emotions.joy !== undefined ? emotions.joy : 0.40);
  const sadness = Number(emotions.sadness !== undefined ? emotions.sadness : 0.10);
  const irritation = Number(emotions.irritation !== undefined ? emotions.irritation : 0.10);

  // 1. Plutchik Emotional Dyads (Giao thoa cảm xúc phức hợp)
  if (shyness >= 0.80 && attachment >= 0.65 && irritation < 0.25 && sadness < 0.35) {
    return '💖 Chisa đang ngượng ngùng cực điểm, vỏ bọc Kuudere tan chảy hoàn toàn trước Senpai ~';
  }
  if (sadness >= 0.45 && trust >= 0.70 && irritation < 0.25) {
    return '🥺 Chisa đang xúc động, cảm thấy an toàn tuyệt đối để tựa vào vai Senpai tâm sự điều sâu kín.';
  }
  if (irritation >= 0.40 && irritation < 0.70 && trust >= 0.60 && attachment >= 0.20) {
    return '😤 Chisa đang phồng má dỗi yêu, giả vờ quay mặt đi nhưng vẫn ngầm đợi Senpai dỗ dành ~';
  }
  if (joy >= 0.55 && shyness >= 0.55 && irritation < 0.20 && sadness < 0.30 && trust >= 0.40) {
    return '😳 Chisa vừa ngập tràn hạnh phúc vừa ngượng chín mặt che má cười khúc khích ~';
  }
  if (comfort >= 0.70 && curiosity >= 0.60 && irritation < 0.20 && sadness < 0.30) {
    return '✨ Chisa đang say sưa cùng Senpai khám phá cấu trúc thế giới trong sự bình yên thanh thản.';
  }

  // 2. Quan Hệ Bền Vững Đỉnh Cao (Tier A5 / T5)
  if (attachment >= 0.88 && trust >= 0.90 && irritation < 0.25 && sadness < 0.35) {
    return '💍 Chisa xem Senpai là lý do tồn tại duy nhất, gắn kết trọn đời không thể tách rời.';
  }

  // 3. Trạng thái Tiêu cực & Cảnh báo phòng thủ (Chặn triệt để - Không để lọt nhãn chill khi nổi giận)
  if (irritation >= 0.70) {
    if (trust < 0.50) {
      return '💢 Chisa đang cực kỳ tức giận và lạnh lùng dựng rào chắn phòng thủ nghiêm ngặt.';
    }
    return '💢 Chisa đang rất khó chịu và bức xúc trước lời nói/hành vi của Senpai.';
  }
  if (irritation >= 0.40) {
    if (trust >= 0.50 && attachment >= 0.10) {
      return '😤 Chisa đang giận dỗi ra mặt, cảm thấy bực bội và chưa muốn nói chuyện.';
    }
    return '😾 Chisa cảm thấy rất khó chịu trước thái độ hoặc lời trêu chọc của đối phương.';
  }
  if (irritation >= 0.20) {
    if (trust >= 0.50 && attachment >= 0.05) {
      return '😤 Chisa có chút phụng phịu dỗi nhẹ, đang muốn Senpai quan tâm nhiều hơn ~';
    }
    return '😾 Chisa cảm thấy hơi khó chịu và không hài lòng.';
  }
  if (trust < 0.35) {
    return '✋ Chisa đang giữ khoảng cách nghiêm nghị, đề phòng và chưa tin tưởng.';
  }
  if (sadness >= 0.70) {
    return '🌧️ Chisa đang cảm thấy đau lòng và chìm trong nỗi buồn sâu sắc.';
  }
  if (sadness >= 0.40) {
    return '🥺 Chisa đang bâng khuâng, có chút u buồn man mác trong lòng.';
  }
  if (comfort < 0.30) {
    return '⚡ Chisa đang cảm thấy căng thẳng và bất an trước bối cảnh xung quanh.';
  }

  // 4. Trạng thái Tích cực & Nâng cao
  if (joy >= 0.60 && shyness >= 0.25) {
    return '🥰 Chisa đang ngập tràn niềm vui, đôi má hơi ửng hồng hạnh phúc bên Senpai ~';
  }
  if (joy >= 0.50) {
    return '😊 Chisa đang có tâm trạng rất vui vẻ, thoải mái và dễ chịu.';
  }
  if (shyness >= 0.55) {
    return '🙈 Chisa đang bối rối, hai má ửng hồng thẹn thùng trước lời nói của Senpai ~';
  }
  if (curiosity >= 0.85) {
    return '💡 Chisa đang phấn khích tột độ, ánh mắt sáng lấp lánh say mê giải mã cùng Senpai!';
  }
  if (curiosity >= 0.60) {
    return '🔎 Chisa đang rất hào hứng và say mê muốn cùng Senpai tìm hiểu sâu hơn.';
  }
  if (comfort >= 0.85) {
    return '🕊️ Chisa cảm nhận sự bình yên tuyệt đối, coi Senpai là bến đỗ an toàn nhất thế gian.';
  }
  if (comfort >= 0.60) {
    return '🍵 Chisa đang cảm nhận được sự ấm áp, bình yên và thư thái trọn vẹn bên Senpai.';
  }

  // 5. Mặc định (Baseline Kuudere)
  return '🍃 Chisa ở trạng thái Kuudere điềm tĩnh, ấm áp và quan tâm Senpai một cách tinh tế.';
}

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
      const summaryText = getEmotionStatusSummary(emotions);
      lines.push('');
      lines.push('**[Trạng thái Cảm xúc]**');
      lines.push('```');
      lines.push(emotionLines.join('\n'));
      lines.push('```');
      lines.push(`*${summaryText}*`);
    }
  }

  return lines.join('\n');
}

export async function resolveMentionsInGuild(guild, text) {
  if (!guild || !text || !text.includes('@')) {
    return text;
  }

  // Regex to match mention-like patterns e.g. @manhit, @Fym, @Mạnh, @kuro_senpai
  const mentionMatches = text.match(/@([\p{L}\p{N}_.\-]+)/gu);
  if (!mentionMatches) {
    return text;
  }

  let resolvedText = text;

  try {
    for (const match of mentionMatches) {
      const rawName = match.slice(1).toLowerCase();
      // Exclude special discord mentions
      if (rawName === 'everyone' || rawName === 'here') {
        continue;
      }

      // 1. Check in cached guild members first
      let member = guild.members?.cache?.find((m) =>
        m.user?.username?.toLowerCase() === rawName ||
        m.user?.globalName?.toLowerCase() === rawName ||
        m.displayName?.toLowerCase() === rawName
      );

      // 2. If not found in cache, fetch member by query
      if (!member && typeof guild.members?.fetch === 'function') {
        try {
          const fetched = await guild.members.fetch({ query: rawName, limit: 1 });
          member = fetched?.first();
        } catch {
          // ignore lookup error
        }
      }

      if (member) {
        resolvedText = resolvedText.replaceAll(match, `<@${member.id}>`);
      }
    }
  } catch {
    // Graceful fallback to original text
  }

  return resolvedText;
}

export async function replyWithChunks(context, text, emotions, client) {
  const isInteraction = typeof context.editReply === 'function';
  const guild = context.guild || null;

  // Proactively resolve @mentions to real Discord <@UserID> tags when in a server guild
  const resolvedText = guild ? await resolveMentionsInGuild(guild, text) : text;

  const formatted = formatCoreResponse(resolvedText, emotions, client);
  const chunks = splitDiscordMessage(formatted, client.services?.config?.reply?.maxChars ?? 1900);

  if (isInteraction) {
    await context.editReply({
      content: chunks[0] || 'Chisa chưa tạo được phản hồi.',
      allowedMentions: { parse: ['users'], repliedUser: false }
    });
    for (let i = 1; i < chunks.length; i += 1) {
      await context.followUp({
        content: chunks[i],
        allowedMentions: { parse: ['users'] }
      });
    }
  } else {
    await context.reply({
      content: chunks[0] || 'Chisa chưa tạo được phản hồi.',
      allowedMentions: { parse: ['users'], repliedUser: false }
    });
    for (let i = 1; i < chunks.length; i += 1) {
      await context.channel.send({
        content: chunks[i],
        allowedMentions: { parse: ['users'] }
      });
    }
  }
}
