import type { LngLat } from '@/domain/types';
import type { LiveConfig } from './config';

/** HTTP and WebSocket access to the per-user danger API (docs/api-contract.md, "Per-user danger"). */

export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'HttpError';
  }
}

export interface LocationPing {
  lat: number;
  lon: number;
  speed_mps: number;
  heading_deg?: number;
}

export type Reply = 'safe' | 'need_help';

export interface DangerApi {
  getDanger(): Promise<unknown>;
  getSummary(): Promise<unknown>;
  getGauges(): Promise<unknown>;
  postLocation(ping: LocationPing): Promise<unknown>;
  postRoute(route: readonly LngLat[]): Promise<void>;
  postReply(reply: Reply): Promise<unknown>;
  /** Restarts the July 4, 2025 replay (also restarts it for the dashboard). Fast, so the crest arrives in ~1 min. */
  restartReplay(): Promise<unknown>;
  /** The dashboard's flood layers for one map window. */
  getFloodLayer(bbox: string): Promise<unknown>;
  /** A way to higher ground from the user's last position. */
  getDirections(): Promise<unknown>;
  /** Prepare the assistant line (context to the agent) and get its number to dial. */
  requestAssistant(): Promise<unknown>;
  /** Up to 3 ways between two points, each with its flooding. */
  getRouteOptions(start: LngLat, end: LngLat): Promise<unknown>;
}

/** Replay speed for the table demo: reaches the Kerrville crest in about a minute, then holds the final state. */
export const DEMO_REPLAY_SPEED = 1000;

const DEFAULT_TIMEOUT_MS = 6000;
const MAX_ROUTE_POINTS = 2000;

/** The backend takes [lat, lon] pairs; the app stores [lon, lat]. Thins very long routes to the API's limit. */
export function toRoutePoints(route: readonly LngLat[]): [number, number][] {
  const stride = Math.ceil(route.length / MAX_ROUTE_POINTS) || 1;
  const thinned = route.filter((_, i) => i % stride === 0 || i === route.length - 1);
  return thinned.map(([lon, lat]) => [lat, lon]);
}

export function createDangerApi(
  config: LiveConfig,
  fetchImpl: typeof fetch = fetch,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): DangerApi {
  const user = `${config.apiUrl}/api/users/${encodeURIComponent(config.userId)}`;

  async function request(url: string, init?: RequestInit): Promise<unknown> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetchImpl(url, {
        ...init,
        headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}) },
        signal: controller.signal,
      });
      if (!res.ok) throw new HttpError(res.status, `HiTide returned ${res.status}`);
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  }

  const post = (url: string, body: unknown) => request(url, { method: 'POST', body: JSON.stringify(body) });

  return {
    getDanger: () => request(`${user}/danger`),
    getSummary: () => request(`${config.apiUrl}/api/safety/summary`),
    getGauges: () => request(`${config.apiUrl}/api/region/gauges`),
    postLocation: (ping) => post(`${user}/location`, ping),
    postRoute: async (route) => {
      await post(`${user}/route`, { points: toRoutePoints(route) });
    },
    postReply: (reply) => post(`${user}/reply`, { reply, by: 'driver' }),
    getFloodLayer: (bbox) => request(`${config.apiUrl}/api/region/flood-layer?bbox=${encodeURIComponent(bbox)}`),
    getDirections: () => request(`${user}/directions`),
    requestAssistant: () => post(`${user}/assistant`, {}),
    getRouteOptions: (start, end) =>
      request(`${config.apiUrl}/api/routes/options?start=${start[0]},${start[1]}&end=${end[0]},${end[1]}`),
    restartReplay: () =>
      post(`${config.apiUrl}/api/demo/start?scenario=hill_country&speed=${DEMO_REPLAY_SPEED}`, {}),
  };
}

export interface EventHandlers {
  /** A message arrived; the payload is untrusted and must be validated by the caller. */
  onMessage(data: unknown): void;
  onOpen(): void;
  onClose(): void;
}

type SocketFactory = (url: string) => WebSocket;

const MIN_RECONNECT_MS = 1000;
const MAX_RECONNECT_MS = 15_000;
/** Backoff resets only after a connection has stayed up this long (a server that accepts then drops won't spin). */
const STABLE_MS = 5000;
/** Event payloads are small; anything larger is ignored rather than parsed. */
const MAX_MESSAGE_CHARS = 256 * 1024;

/** Opens the backend WebSocket and keeps it open with capped exponential backoff. Returns a stop function. */
export function connectEvents(
  wsUrl: string,
  handlers: EventHandlers,
  makeSocket: SocketFactory = (url) => new WebSocket(url),
): () => void {
  let socket: WebSocket | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  let stable: ReturnType<typeof setTimeout> | null = null;
  let delay = MIN_RECONNECT_MS;
  let stopped = false;

  const open = () => {
    if (stopped) return;
    try {
      socket = makeSocket(wsUrl);
    } catch {
      schedule();
      return;
    }
    socket.onopen = () => {
      stable = setTimeout(() => {
        delay = MIN_RECONNECT_MS;
      }, STABLE_MS);
      handlers.onOpen();
    };
    socket.onmessage = (e: MessageEvent) => {
      if (typeof e.data !== 'string' || e.data.length > MAX_MESSAGE_CHARS) return;
      let data: unknown;
      try {
        data = JSON.parse(e.data);
      } catch {
        return; // not JSON: ignore this message, keep the connection
      }
      handlers.onMessage(data);
    };
    socket.onclose = () => {
      if (stable) clearTimeout(stable);
      socket = null;
      handlers.onClose();
      schedule();
    };
    socket.onerror = () => socket?.close();
  };

  const schedule = () => {
    if (stopped || retry) return;
    retry = setTimeout(() => {
      retry = null;
      open();
    }, delay);
    delay = Math.min(delay * 2, MAX_RECONNECT_MS);
  };

  open();
  return () => {
    stopped = true;
    if (retry) clearTimeout(retry);
    if (stable) clearTimeout(stable);
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
  };
}
