import { afterEach, describe, expect, it, jest } from '@jest/globals';
import type { KeyValueStore } from '@/data/store';
import { LiveHiTideRepository } from '@/data/live/liveRepository';
import { HttpError, type DangerApi, type EventHandlers, type LocationPing } from '@/data/live/transport';
import { RepositoryError } from '@/data/repository';
import { deriveFlowMode } from '@/state/reducer';
import realCriticalHelp from './assessment.critical-help.json';

const AT = '2025-07-04T12:00:00+00:00';
const T0 = Date.parse(AT) / 1000;

const memory = (): KeyValueStore => {
  const data: Record<string, string> = {};
  return {
    getItem: async (k) => data[k] ?? null,
    setItem: async (k, v) => {
      data[k] = v;
    },
    removeItem: async (k) => {
      delete data[k];
    },
  };
};

const calm = { ...realCriticalHelp, level: 'none', advice: 'none', reasons: [], assessed_at: AT, response: null };

const awaiting = {
  ...realCriticalHelp,
  response: {
    ...realCriticalHelp.response,
    need_help: false,
    awaiting_reply: true,
    timeline: [{ t: T0, what: 'critical -> voice:critical_call, open_case:case' }],
  },
};

const turnAround = {
  ...realCriticalHelp,
  level: 'danger',
  advice: 'turn_around',
  location: { lat: 30.03, lon: -99.13, ts: T0, state: 'driving', speed_mps: 13 },
  hazard: {
    ...realCriticalHelp.hazard,
    ahead: [{ edge_id: 'e1', road_name: 'Park Street', distance_m: 300, depth_in: null, point_status: 'confirmed_flooded' }],
  },
  response: { ...awaiting.response, awaiting_reply: false, case_open: false, timeline: [] },
};

const FLOOD = {
  at: '2025-07-04T12:20:00+00:00',
  segments: [{ id: 'a-b-0', status: 'confirmed_flooded', name: 'Park Street', coords: [[-99.13, 30.03], [-99.12, 30.03]] }],
  points: [{ id: 'cp-0043', name: 'Park Street', kind: 'crossing', status: 'confirmed_flooded', lon: -99.13, lat: 30.03 }],
  gauges: [{ site: '08166200', name: 'Guadalupe Rv at Kerrville', lon: -99.16, lat: 30.05, stage_ft: 30.1, flood_category: 'major' }],
  alerts: [{ headline: 'REPLAY of July 4, 2025: Flash Flood Emergency for Hunt to Kerrville' }],
};

const DIRECTIONS = {
  text: 'Head for higher ground by Hill Road, about 0.6 km.',
  kind: 'route',
  road_names: ['Hill Road'],
  length_m: 600,
  coords: [[[-99.13, 30.03], [-99.13, 30.04]]],
  avoid: ['Park Street'],
};

const ROUTES = {
  options: [
    { id: 'r0', label: 'Fastest', via: ['Park Street'], length_m: 3100, minutes: 5, status: 'flooded', flooded: ['Park Street'], likely: [], coords: [[[-99.12, 30.02], [-99.13, 30.03]]] },
    { id: 'r1', label: 'Avoids known flooding', via: ['G Street'], length_m: 3900, minutes: 6, status: 'clear', flooded: [], likely: [], coords: [[[-99.12, 30.02], [-99.12, 30.04]]] },
  ],
};

type Mutable<T> = { -readonly [K in keyof T]: T[K] };

function fakeApi(danger: unknown = calm): Mutable<DangerApi> & { pings: LocationPing[]; replies: string[]; routes: number } {
  const api = {
    pings: [] as LocationPing[],
    replies: [] as string[],
    routes: 0,
    getDanger: jest.fn(async (): Promise<unknown> => danger),
    getSummary: jest.fn(async (): Promise<unknown> => ({ mode: 'replay', ready: true })),
    getGauges: jest.fn(async (): Promise<unknown> => []),
    postLocation: jest.fn(async (p: LocationPing): Promise<unknown> => {
      api.pings.push(p);
      return p.speed_mps === 0 ? awaiting : turnAround;
    }),
    postRoute: jest.fn(async (): Promise<void> => {
      api.routes += 1;
    }),
    postReply: jest.fn(async (r: string): Promise<unknown> => {
      api.replies.push(r);
      return { reply: r };
    }),
    restartReplay: jest.fn(async (): Promise<unknown> => ({ ok: true })),
    getFloodLayer: jest.fn(async (): Promise<unknown> => FLOOD),
    getDirections: jest.fn(async (): Promise<unknown> => DIRECTIONS),
    requestAssistant: jest.fn(async (): Promise<unknown> => ({ mode: 'live', phone: '+15550100000', directions: DIRECTIONS })),
    getRouteOptions: jest.fn(async (): Promise<unknown> => ROUTES),
  };
  return api;
}

const CONFIG = { apiUrl: 'http://localhost:8010', wsUrl: 'ws://localhost:8010/ws', userId: 'hc-dana' };

let repo: LiveHiTideRepository | null = null;
let ws: EventHandlers | null = null;

function make(api: DangerApi) {
  repo = new LiveHiTideRepository({
    config: CONFIG,
    storage: memory(),
    api,
    connect: (_url, handlers) => {
      ws = handlers;
      return () => {
        ws = null;
      };
    },
    pollMs: 60_000,
    gaugePollMs: 60_000,
    drivePingMs: 1,
    crestPollMs: 1,
  });
  return repo;
}

const settle = async (check: () => boolean, tries = 200) => {
  for (let i = 0; i < tries && !check(); i += 1) await new Promise((r) => setTimeout(r, 5));
  expect(check()).toBe(true);
};

afterEach(() => {
  repo?.stop();
  repo = null;
});

describe('LiveHiTideRepository', () => {
  it('starts calm and live, learns the backend mode, and pre-checks the planned route', async () => {
    const api = fakeApi();
    const r = make(api);
    expect(r.getSnapshot().connection).toMatchObject({ kind: 'live', status: 'connecting' });
    expect(r.getSnapshot().warning).toBeNull();
    await r.load();
    r.start();
    await settle(() => r.getSnapshot().connection.status === 'live');
    expect(r.getSnapshot().connection.mode).toBe('replay');
    await settle(() => api.routes === 1);
  });

  it('shows offline when the backend is unreachable, and "connecting" before the replay starts', async () => {
    const api = fakeApi();
    api.getDanger = jest.fn(async (): Promise<unknown> => {
      throw new TypeError('Network request failed');
    });
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => r.getSnapshot().connection.status === 'offline');

    const waiting = fakeApi();
    waiting.getDanger = jest.fn(async (): Promise<unknown> => {
      throw new HttpError(409, 'no flood picture yet');
    });
    repo?.stop();
    const r2 = make(waiting);
    await r2.load();
    r2.start();
    await settle(() => (waiting.getDanger as jest.Mock).mock.calls.length > 0);
    expect(r2.getSnapshot().connection.status).toBe('connecting');
  });

  it('ignores malformed payloads', async () => {
    const r = make(fakeApi({ level: 'catastrophic' }));
    await r.load();
    r.start();
    await new Promise((res) => setTimeout(res, 30));
    expect(r.getSnapshot().safetyCase).toBeNull();
    expect(r.getSnapshot().warning).toBeNull();
  });

  it('refetches when the WebSocket announces a danger change for this user only', async () => {
    const api = fakeApi();
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => (api.getDanger as jest.Mock).mock.calls.length >= 1);
    const before = (api.getDanger as jest.Mock).mock.calls.length;
    ws?.onMessage({ type: 'user.danger', payload: { user_id: 'hc-ruth' } });
    ws?.onMessage({ type: 'user.danger', payload: { user_id: 'hc-dana' } });
    await settle(() => (api.getDanger as jest.Mock).mock.calls.length === before + 1);
  });

  it('demo drive: pings along the route, raises the turn-around, then the check-in at the stop', async () => {
    const api = fakeApi();
    const r = make(api);
    await r.load();
    r.start();
    const modes = new Set<string>();
    r.subscribe(() => modes.add(deriveFlowMode(r.getSnapshot())));
    r.startDemoDrive();
    expect(r.getSnapshot().connection.drive).toBe('driving');
    await settle(() => r.getSnapshot().connection.drive === 'stopped', 1000);
    expect(modes.has('turn_around')).toBe(true);
    expect(deriveFlowMode(r.getSnapshot())).toBe('check_in');
    expect(api.pings[api.pings.length - 1].speed_mps).toBe(0);
  });

  it('help is sent once even on a double tap, then shows support', async () => {
    const api = fakeApi(awaiting);
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => deriveFlowMode(r.getSnapshot()) === 'check_in');
    await Promise.all([r.requestHelp(), r.requestHelp()]);
    expect(api.replies).toEqual(['need_help']);
    expect(deriveFlowMode(r.getSnapshot())).toBe('support');
  });

  it('a failed reply surfaces a RepositoryError and keeps the check-in', async () => {
    const api = fakeApi(awaiting);
    api.postReply = jest.fn(async (): Promise<unknown> => {
      throw new TypeError('Network request failed');
    });
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => deriveFlowMode(r.getSnapshot()) === 'check_in');
    await expect(r.markSafe()).rejects.toBeInstanceOf(RepositoryError);
    expect(deriveFlowMode(r.getSnapshot())).toBe('check_in');
  });

  it('a developer scenario pauses backend updates until reset', async () => {
    const api = fakeApi(awaiting);
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => deriveFlowMode(r.getSnapshot()) === 'check_in');
    r.setScenario('normal');
    ws?.onOpen();
    await new Promise((res) => setTimeout(res, 30));
    expect(deriveFlowMode(r.getSnapshot())).toBe('normal');
    await r.reset();
    expect(r.getSnapshot().connection.paused).toBe(false);
    expect(deriveFlowMode(r.getSnapshot())).toBe('check_in');
  });

  it('stop closes the socket and timers', async () => {
    const r = make(fakeApi());
    await r.load();
    r.start();
    expect(ws).not.toBeNull();
    r.stop();
    expect(ws).toBeNull();
    repo = null;
  });
});

describe('LiveHiTideRepository lifecycle and failure reporting', () => {
  it('stop() then start() resumes polling (StrictMode / Fast Refresh remount)', async () => {
    const api = fakeApi(awaiting);
    const r = make(api);
    await r.load();
    r.start();
    r.stop();
    expect(ws).toBeNull();
    r.start();
    expect(ws).not.toBeNull();
    await settle(() => deriveFlowMode(r.getSnapshot()) === 'check_in');
  });

  it('start() twice opens one socket', async () => {
    let sockets = 0;
    repo = new LiveHiTideRepository({
      config: CONFIG,
      storage: memory(),
      api: fakeApi(),
      connect: () => {
        sockets += 1;
        return () => undefined;
      },
      pollMs: 60_000,
      gaugePollMs: 60_000,
    });
    await repo.load();
    repo.start();
    repo.start();
    expect(sockets).toBe(1);
  });

  it('a payload that fails validation is reported, not shown as live', async () => {
    const r = make(fakeApi({ level: 'catastrophic' }));
    await r.load();
    r.start();
    await settle(() => r.getSnapshot().connection.status === 'offline');
  });

  it('a gauge or summary failure does not mark the app offline', async () => {
    const api = fakeApi();
    api.getGauges = jest.fn(async (): Promise<unknown> => {
      throw new HttpError(500, 'boom');
    });
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => r.getSnapshot().connection.status === 'live');
    await new Promise((res) => setTimeout(res, 30));
    expect(r.getSnapshot().connection.status).toBe('live');
  });

  it('a 4xx on a write is not reported as offline', async () => {
    const api = fakeApi();
    api.postRoute = jest.fn(async (): Promise<void> => {
      throw new HttpError(422, 'bad route');
    });
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => r.getSnapshot().connection.status === 'live');
    await expect(r.selectRoute('original')).rejects.toBeInstanceOf(RepositoryError);
    expect(r.getSnapshot().connection.status).toBe('live');
  });

  it('restarting the demo drive never runs two drive loops', async () => {
    const api = fakeApi();
    let release: () => void = () => undefined;
    const gate = new Promise<void>((res) => {
      release = res;
    });
    const original = api.postLocation;
    api.postLocation = jest.fn(async (p: LocationPing): Promise<unknown> => {
      if (api.pings.length === 0) await gate;
      return original(p);
    });
    const r = make(api);
    await r.load();
    r.start();
    r.startDemoDrive();
    await new Promise((res) => setTimeout(res, 5));
    r.stopDemoDrive();
    r.startDemoDrive();
    release();
    await settle(() => r.getSnapshot().connection.drive === 'stopped', 1000);
    const stops = api.pings.filter((p) => p.speed_mps === 0).length;
    expect(stops).toBe(3);
  });

  it('the simulate-failures switch changes the snapshot so the UI re-renders', async () => {
    const r = make(fakeApi());
    const before = r.getSnapshot();
    r.setSimulateFailures(true);
    expect(r.getSnapshot()).not.toBe(before);
    expect(r.getSnapshot().connection.failWrites).toBe(true);
  });
});

describe('resetDemo (presentation table)', () => {
  it('restarts the replay, waits for the crest, and returns to a calm live picture', async () => {
    const api = fakeApi(awaiting);
    const early = { ...calm, assessed_at: '2025-07-04T03:00:00+00:00' };
    const crest = { ...calm, assessed_at: '2025-07-04T12:20:00+00:00' };
    let restarted = false;
    let polls = 0;
    api.restartReplay = jest.fn(async (): Promise<unknown> => {
      restarted = true;
      return { ok: true };
    });
    api.getDanger = jest.fn(async (): Promise<unknown> => {
      if (!restarted) return awaiting;
      polls += 1;
      return polls < 3 ? early : crest;
    });
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => deriveFlowMode(r.getSnapshot()) === 'check_in');
    const done = r.resetDemo();
    expect(r.getSnapshot().connection.drive).toBe('preparing');
    await done;
    expect(api.restartReplay).toHaveBeenCalledTimes(1);
    expect(r.getSnapshot().connection.drive).toBe('idle');
    expect(r.getSnapshot().connection.assessedAt).toBe(crest.assessed_at);
    expect(deriveFlowMode(r.getSnapshot())).toBe('normal');
  });

  it('a failed restart surfaces an error and leaves the drive idle', async () => {
    const api = fakeApi();
    api.restartReplay = jest.fn(async (): Promise<unknown> => {
      throw new TypeError('Network request failed');
    });
    const r = make(api);
    await r.load();
    await expect(r.resetDemo()).rejects.toBeInstanceOf(RepositoryError);
    expect(r.getSnapshot().connection.drive).toBe('idle');
  });
});

describe('flood map, directions and the assistant line', () => {
  it('loads the flood layer for the map window', async () => {
    const api = fakeApi();
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => r.getSnapshot().floodLayer !== null);
    const layer = r.getSnapshot().floodLayer!;
    expect(layer.roads[0]).toMatchObject({ name: 'Park Street', status: 'confirmed_flooded' });
    expect(layer.gauges[0]).toMatchObject({ name: 'Guadalupe River at Kerrville', category: 'major' });
    expect(layer.alerts).toEqual(['Flash Flood Emergency for Hunt to Kerrville']);
    expect(api.getFloodLayer).toHaveBeenCalledWith('-99.18,29.99,-99.08,30.08');
  });

  it('fetches directions only while a check-in or help case is open', async () => {
    const calm = fakeApi();
    const r = make(calm);
    await r.load();
    r.start();
    await settle(() => r.getSnapshot().connection.status === 'live');
    expect(calm.getDirections).not.toHaveBeenCalled();
    repo?.stop();
    const api = fakeApi(awaiting);
    const r2 = make(api);
    await r2.load();
    r2.start();
    await settle(() => r2.getSnapshot().directions !== null);
    expect(r2.getSnapshot().directions).toMatchObject({ kind: 'route', roadNames: ['Hill Road'], avoid: ['Park Street'] });
  });

  it('callAssistant returns the number to dial once, even on a double tap, and shows the step', async () => {
    const api = fakeApi(awaiting);
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => deriveFlowMode(r.getSnapshot()) === 'check_in');
    const [a, b] = await Promise.all([r.callAssistant(), r.callAssistant()]);
    expect(a).toBe(b);
    expect(a).toMatchObject({ mode: 'live', phone: '+15550100000' });
    expect(api.requestAssistant).toHaveBeenCalledTimes(1);
    expect(r.getSnapshot().safetyCase?.events.some((e) => e.kind === 'assistant_call')).toBe(true);
  });

  it('a malformed assistant reply or a bad number is rejected, never dialled', async () => {
    const api = fakeApi(awaiting);
    api.requestAssistant = jest.fn(async (): Promise<unknown> => ({ mode: 'live', phone: 'javascript:alert(1)' }));
    const r = make(api);
    await r.load();
    await expect(r.callAssistant()).rejects.toBeInstanceOf(RepositoryError);
  });
});

describe('route choices', () => {
  it('loads the options and choosing one sends that route for the pre-trip check', async () => {
    const api = fakeApi();
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => r.getSnapshot().routeChoices.length === 2);
    // Least flooding on top: the dry way first, the flooded fastest way last.
    expect(r.getSnapshot().routeChoices.map((c) => c.status)).toEqual(['clear', 'flooded']);
    expect(r.getSnapshot().routeChoices[1]).toMatchObject({ label: 'Fastest', flooded: ['Park Street'] });
    const before = api.routes;
    await r.chooseRoute('r1');
    expect(r.getSnapshot().selectedChoiceId).toBe('r1');
    expect(api.routes).toBe(before + 1);
    await expect(r.chooseRoute('nope')).rejects.toBeInstanceOf(RepositoryError);
  });
});


describe('setLocation (a pin dropped on the map)', () => {
  const PIN = [-99.13361, 30.03785] as const;
  const warned = {
    ...realCriticalHelp,
    level: 'warning',
    advice: 'move_to_high_ground',
    assessed_at: AT,
    location: { lat: PIN[1], lon: PIN[0], ts: T0, state: 'parked', speed_mps: 0 },
    response: {
      ...realCriticalHelp.response,
      need_help: false,
      awaiting_reply: false,
      case_open: false,
      timeline: [{ t: T0, what: 'warning -> text:warning' }],
    },
  };

  it('POSTs the pin as a stopped ping, applies the assessment, and fetches directions for a warning', async () => {
    const api = fakeApi(warned);
    api.postLocation = jest.fn(async (p: LocationPing): Promise<unknown> => {
      api.pings.push(p);
      return warned;
    });
    const r = make(api);
    await r.load();
    r.start();
    await settle(() => r.getSnapshot().connection.status === 'live');
    await r.setLocation(PIN);
    expect(api.pings).toEqual([{ lat: PIN[1], lon: PIN[0], speed_mps: 0 }]);
    const s = r.getSnapshot();
    expect(s.connection.level).toBe('warning');
    expect(s.connection.lastOutreach).toBe('warning -> text:warning');
    expect(s.lastPin).toMatchObject({ at: PIN, level: 'warning' });
    expect(s.position).toEqual(PIN);
    expect(s.directions).toMatchObject({ kind: 'route', roadNames: ['Hill Road'] });
    expect(deriveFlowMode(s)).toBe('normal');
  });

  it('a pin in danger opens the check-in (the backend is calling)', async () => {
    const api = fakeApi(awaiting);
    const r = make(api);
    await r.load();
    r.start();
    await r.setLocation(PIN);
    expect(api.pings[0].speed_mps).toBe(0);
    expect(r.getSnapshot().connection.callPlaced).toBe(true);
    expect(deriveFlowMode(r.getSnapshot())).toBe('check_in');
  });

  it('rejects with a RepositoryError on HTTP or network failure, or an invalid point, and keeps the picture', async () => {
    const api = fakeApi();
    api.postLocation = jest.fn(async (): Promise<unknown> => {
      throw new HttpError(500, 'boom');
    });
    const r = make(api);
    await r.load();
    r.start();
    await expect(r.setLocation(PIN)).rejects.toBeInstanceOf(RepositoryError);
    api.postLocation = jest.fn(async (): Promise<unknown> => {
      throw new TypeError('Network request failed');
    });
    await expect(r.setLocation(PIN)).rejects.toBeInstanceOf(RepositoryError);
    await expect(r.setLocation([200, 30])).rejects.toBeInstanceOf(RepositoryError);
    await expect(r.setLocation([Number.NaN, 30])).rejects.toBeInstanceOf(RepositoryError);
    expect(api.postLocation).toHaveBeenCalledTimes(1);
    expect(r.getSnapshot().lastPin).toBeNull();
  });
});
