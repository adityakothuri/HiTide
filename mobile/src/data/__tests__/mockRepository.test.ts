import { describe, expect, it, jest } from '@jest/globals';
import { deriveFlowMode } from '@/state/reducer';
import { type KeyValueStore, MockHiTideRepository, STORAGE_KEY } from '../mockRepository';
import { validateContact } from '../repository';

function memoryStore(initial: Record<string, string> = {}): KeyValueStore & { data: Record<string, string> } {
  const data = { ...initial };
  return {
    data,
    getItem: async (k) => data[k] ?? null,
    setItem: async (k, v) => {
      data[k] = v;
    },
    removeItem: async (k) => {
      delete data[k];
    },
  };
}

const make = (storage = memoryStore()) =>
  new MockHiTideRepository({ storage, latencyMs: 0, contactNotifyDelayMs: 10 });

const flush = () => new Promise((r) => setTimeout(r, 0));

describe('MockHiTideRepository', () => {
  it('records concurrent help taps once and simulates the contact notification', async () => {
    const repo = make();
    repo.setScenario('check_in');
    await Promise.all([repo.requestHelp(), repo.requestHelp(), repo.requestHelp()]);
    const events = repo.getSnapshot().safetyCase?.events ?? [];
    expect(events.filter((e) => e.kind === 'help_received')).toHaveLength(1);
    await new Promise((r) => setTimeout(r, 30));
    expect(repo.getSnapshot().safetyCase?.events.some((e) => e.kind === 'contact_notified')).toBe(true);
    repo.stop();
  });

  it('persists preferences, contact, route and read state but never an urgent overlay', async () => {
    const storage = memoryStore();
    const repo = make(storage);
    await repo.setPreferences({ spokenAlerts: false });
    await repo.selectRoute('alternate');
    repo.setScenario('turn_around');
    await flush();
    const saved = JSON.parse(storage.data[STORAGE_KEY]);
    expect(saved).not.toHaveProperty('alert');
    expect(saved).not.toHaveProperty('safetyCase');

    const restarted = make(storage);
    await restarted.load();
    const s = restarted.getSnapshot();
    expect(s.preferences.spokenAlerts).toBe(false);
    expect(deriveFlowMode(s)).toBe('normal');
  });

  it('ignores corrupt storage', async () => {
    const repo = make(memoryStore({ [STORAGE_KEY]: '{not json' }));
    await expect(repo.load()).resolves.toBeUndefined();
    expect(repo.getSnapshot().contact.name).toBe('Maria Whitfield');
  });

  it('surfaces simulated write failures without changing state', async () => {
    const repo = make();
    repo.setSimulateFailures(true);
    await expect(repo.selectRoute('alternate')).rejects.toThrow(/reach HiTide/);
    expect(repo.getSnapshot().selectedRouteId).toBe('original');
  });

  it('rejects invalid contact edits', async () => {
    const repo = make();
    await expect(repo.updateContact({ name: ' ', relationship: '', phone: '12' })).rejects.toThrow();
    expect(validateContact({ name: 'Sam', relationship: '', phone: '(830) 555-0199' }).ok).toBe(true);
  });

  it('stops notifying after unsubscribe and clears storage on reset', async () => {
    const storage = memoryStore();
    const repo = make(storage);
    const listener = jest.fn();
    const off = repo.subscribe(listener);
    repo.markRead('upd-warning');
    off();
    repo.markRead('upd-contact');
    expect(listener).toHaveBeenCalledTimes(1);
    await flush();
    await repo.reset();
    await flush();
    expect(repo.getSnapshot().readIds).toEqual([]);
    const saved = storage.data[STORAGE_KEY];
    if (saved) expect(JSON.parse(saved).readIds).toEqual([]);
  });
});
