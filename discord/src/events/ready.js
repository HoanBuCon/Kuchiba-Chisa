export const name = 'ready';
export const once = true;

export async function execute(client) {
  const { logger } = client.services;
  logger.info({ user: client.user?.tag }, 'Discord bot ready');

  if (client.user) {
    client.user.setPresence({
      activities: [
        {
          name: '/ask Chisa',
          type: 0,
        },
      ],
      status: 'online',
    });
  }
}
