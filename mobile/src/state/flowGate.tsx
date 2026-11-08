import { type Href, router } from 'expo-router';
import { useEffect, useRef } from 'react';
import { useAppState } from '@/data/RepositoryProvider';
import type { FlowMode } from '@/domain/types';
import { deriveFlowMode } from './reducer';

const FLOW_ROUTES: Record<Exclude<FlowMode, 'normal'>, Href> = {
  turn_around: '/turn-around',
  check_in: '/check-in',
  support: '/support',
  resolved: '/resolved',
};

let nextExit: Href | null = null;

/** Closes any open sheets first, so a focused flow never renders inside a modal. */
function replaceFromRoot(target: Href): void {
  if (router.canDismiss()) router.dismissAll();
  router.replace(target);
}

/** Where to land when the current focused flow ends (e.g. Trips after acknowledging a turn-around). */
export function setFlowExit(target: Href): void {
  nextExit = target;
}

/**
 * Moves the app into and out of focused flows whenever the derived mode changes.
 * Screens dispatch actions; only this gate navigates between ordinary tabs and urgent flows.
 */
export function FlowGate() {
  const state = useAppState();
  const mode = deriveFlowMode(state);
  const previous = useRef<FlowMode | null>(null);

  useEffect(() => {
    const was = previous.current;
    if (was === mode) return;
    previous.current = mode;
    if (mode !== 'normal') {
      nextExit = null;
      replaceFromRoot(FLOW_ROUTES[mode]);
      return;
    }
    if (was !== null) {
      const target = nextExit ?? '/';
      nextExit = null;
      replaceFromRoot(target);
    }
  }, [mode]);

  return null;
}
