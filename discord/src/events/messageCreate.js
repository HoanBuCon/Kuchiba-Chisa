export const name = 'messageCreate';
export const once = false;

export async function execute(client, message) {
  const runner = client.services.prefixCommandRunner;
  if (!runner) {
    return;
  }

  try {
    await runner.handleMessage(message);
  } catch (error) {
    client.services.logger.error(
      { err: error, userId: message.author?.id, channelId: message.channelId },
      'Discord prefix dispatcher failed',
    );

    if (message.channel?.send) {
      await message.channel.send('Bot gặp lỗi khi xử lý lệnh prefix này.');
    }
  }
}
