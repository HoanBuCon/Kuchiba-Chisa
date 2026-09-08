import pg from 'pg';
import { env } from '../config/env.js';

const { Pool } = pg;

const pool = new Pool({
  connectionString: env.database.url,
  max: 10,
  ssl: env.database.ssl ? { rejectUnauthorized: false } : undefined,
});

export async function closePool() {
  await pool.end();
}

export { pool };
