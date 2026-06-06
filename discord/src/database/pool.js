import { readFile } from 'node:fs/promises';
import pg from 'pg';
import { env } from '../config/env.js';
import { logger } from '../config/logger.js';

const { Pool } = pg;

const pool = new Pool({
  connectionString: env.database.url,
  max: 10,
  ssl: env.database.ssl ? { rejectUnauthorized: false } : undefined,
});

let schemaReady = false;

export async function ensureSchema() {
  if (schemaReady) {
    return;
  }

  const schemaPath = new URL('./schema.sql', import.meta.url);
  const schemaSql = await readFile(schemaPath, 'utf8');
  await pool.query(schemaSql);
  schemaReady = true;
  logger.info('Discord database schema ensured');
}

export async function closePool() {
  await pool.end();
}

export { pool };
