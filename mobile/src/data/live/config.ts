/**
 * Live-mode configuration from public build-time env (EXPO_PUBLIC_*). These values are not secrets:
 * the API URL and a demo user id. Nothing here grants access; the backend enforces its own origin/key checks.
 */

export interface LiveConfig {
  apiUrl: string;
  wsUrl: string;
  userId: string;
}

export const DEFAULT_USER_ID = 'hc-dana';

const API_URL = /^https?:\/\/[A-Za-z0-9.-]+(:\d{1,5})?$/;
const USER_ID = /^[a-z0-9][a-z0-9-]{0,63}$/;

export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConfigError';
  }
}

/**
 * Returns null when no API URL is set (sample-data mode). Throws ConfigError for a value that is set but invalid,
 * so a typo fails loudly instead of silently showing sample data.
 */
export function readLiveConfig(env: { apiUrl?: string; userId?: string }): LiveConfig | null {
  const raw = env.apiUrl?.trim();
  if (!raw) return null;
  const apiUrl = raw.replace(/\/+$/, '');
  if (!API_URL.test(apiUrl)) {
    throw new ConfigError(`EXPO_PUBLIC_API_URL must look like http://192.168.1.20:8000 (got "${raw}").`);
  }
  const userId = env.userId?.trim() || DEFAULT_USER_ID;
  if (!USER_ID.test(userId)) {
    throw new ConfigError(`EXPO_PUBLIC_USER_ID must be lowercase letters, digits and dashes (got "${userId}").`);
  }
  return { apiUrl, wsUrl: `${apiUrl.replace(/^http/, 'ws')}/ws`, userId };
}
