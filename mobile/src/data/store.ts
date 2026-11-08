import type { AppState, PersistedState } from '@/domain/types';
import { type Action, reducer, toPersisted } from '@/state/reducer';

/** Minimal async key-value storage (AsyncStorage in the app, an in-memory map in tests). */
export interface KeyValueStore {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export const STORAGE_KEY = 'hitide/state/v1';

function isPersisted(value: unknown): value is PersistedState {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<PersistedState>;
  return (
    v.version === 1 &&
    typeof v.contact?.name === 'string' &&
    typeof v.contact?.phone === 'string' &&
    typeof v.preferences?.spokenAlerts === 'boolean' &&
    typeof v.preferences?.locationSharing === 'boolean' &&
    (v.selectedRouteId === 'original' || v.selectedRouteId === 'alternate') &&
    Array.isArray(v.readIds)
  );
}

/**
 * The reducer-backed state container both repositories share: dispatch, subscribe, and best-effort persistence
 * of the user's own settings. Urgent overlays and safety cases are never persisted.
 */
export class AppStore {
  private state: AppState;
  private readonly listeners = new Set<() => void>();

  constructor(
    initial: AppState,
    private readonly storage: KeyValueStore,
  ) {
    this.state = initial;
  }

  getSnapshot = (): AppState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /** Restores persisted settings. Corrupt or unreadable storage keeps the defaults. */
  async hydrate(now: string): Promise<void> {
    try {
      const raw = await this.storage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed: unknown = JSON.parse(raw);
      if (isPersisted(parsed)) this.dispatch({ type: 'hydrate', persisted: parsed, now });
    } catch {
      // Unreadable storage must not block the app; defaults are a correct starting point.
    }
  }

  dispatch(action: Action): void {
    const next = reducer(this.state, action);
    if (next === this.state) return;
    const persistChanged = JSON.stringify(toPersisted(next)) !== JSON.stringify(toPersisted(this.state));
    this.state = next;
    if (persistChanged) void this.persist();
    this.emit();
  }

  private emit(): void {
    this.listeners.forEach((l) => l());
  }

  async clearPersisted(): Promise<void> {
    try {
      await this.storage.removeItem(STORAGE_KEY);
    } catch {
      // Reset still restores in-memory defaults.
    }
  }

  private async persist(): Promise<void> {
    try {
      await this.storage.setItem(STORAGE_KEY, JSON.stringify(toPersisted(this.state)));
    } catch {
      // Persistence is best-effort; in-memory state stays correct.
    }
  }
}
