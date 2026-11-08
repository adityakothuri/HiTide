import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, type ReactNode, useContext, useEffect, useState, useSyncExternalStore } from 'react';
import type { AppState } from '@/domain/types';
import { MockHiTideRepository } from './mockRepository';
import type { HiTideRepository } from './repository';

const RepositoryContext = createContext<HiTideRepository | null>(null);

/** Swap this factory for the SpaceTimeDB adapter later. Screens never construct repositories. */
function createRepository(): HiTideRepository {
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
    repo.load().finally(() => {
      if (!active) return;
      setReady(true);
      onReady?.();
    });
    return () => {
      active = false;
    };
  }, [repo, onReady]);

  useEffect(() => () => repo.dispose(), [repo]);

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
