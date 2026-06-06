import 'dotenv/config';
import { startApp } from './app.js';
import { logger } from './config/logger.js';

startApp().catch((error) => {
  logger.error({ err: error }, 'Discord bot failed to start');
  process.exit(1);
});
