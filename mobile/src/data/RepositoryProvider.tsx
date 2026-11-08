import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, type ReactNode, useContext, useEffect, useState, useSyncExternalStore } from 'react';
import type { AppState } from '@/domain/types';
import { readLiveConfig } from './live/config';
import { LiveHiTideRepository } from './live/liveRepository';
import { MockHiTideRepository } from './mockRepository';
import type { HiTideRepository } from './repository';

const RepositoryContext = createContext<HiTideRepository | null>(null);

/**
 * Live backend when EXPO_PUBLIC_API_URL is set (see mobile/.env.example), otherwise local sample data.
 * Screens never construct repositories. A malformed URL throws here with a clear message.
 */
function createRepository(): HiTideRepository {
  // Expo inlines EXPO_PUBLIC_* at build time only for literal `process.env.NAME` reads.
  const config = readLiveConfig({
    apiUrl: process.env.EXPO_PUBLIC_API_URL,
    userId: process.env.EXPO_PUBLIC_USER_ID,
  });
  if (config) return new LiveHiTideRepository({ config, storage: AsyncStorage });
  return new MockHiTideRepository({ storage: AsyncStorage });
}

interface ProviderProps {
  children: ReactNode;
  onReady?: () => void;
  /** Inject a repository (tests, or a future backend adapter). Defaults to the local mock. */
  repository?: HiTideRepository;
}

export function RepositoryProvider({ children, onReady, repository }: ProviderProps) {
  const [repo] = useState(() => repository ?? createRepository());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    repo
      .load()
      .catch(() => undefined) // load() never needs the network; a storage failure keeps defaults
      .finally(() => {
        if (!active) return;
        setReady(true);
        onReady?.();
      });
    return () => {
      active = false;
    };
  }, [repo, onReady]);

  // Background work runs only while mounted and after local settings are restored (so a late hydrate can't
  // overwrite live data). start/stop are idempotent, which keeps StrictMode and Fast Refresh remounts safe.
  useEffect(() => {
    if (!ready) return undefined;
    repo.start();
    return () => repo.stop();
  }, [repo, ready]);

  if (!ready) return null;
  return <RepositoryContext.Provider value={repo}>{children}</RepositoryContext.Provider>;
}

export function useRepository(): HiTideRepository {
  const repo = useContext(RepositoryContext);
  if (!repo) throw new Error('useRepository must be used inside RepositoryProvider');
  return repo;
}

/** Subscribes to the full app state. Re-renders only when the snapshot reference changes. */
export function useAppState(): AppState {
  const repo = useRepository();
  return useSyncExternalStore(repo.subscribe, repo.getSnapshot, repo.getSnapshot);
}
