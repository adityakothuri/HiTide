import { type Href, router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef } from 'react';
import { useRepository } from '@/data/RepositoryProvider';
import type { FloodWatchRepository } from '@/data/repository';
import type { Scenario } from '@/domain/types';
import { setFlowExit } from '@/state/flowGate';
import { deriveFlowMode } from '@/state/reducer';

/**
 * Development-only deep link for scripted review, e.g.
 *   exp://127.0.0.1:8081/--/dev-action?do=check_in
 *   exp://127.0.0.1:8081/--/dev-action?do=help
 * Params are checked against fixed allowlists. In production builds this route renders nothing.
 */
const SCENARIOS: readonly Scenario[] = [
  'normal',
  'flood_warning',
  'alternate_route',
  'turn_around',
  'check_in',
  'help_requested',
  'resolved',
];

const ACTIONS: Record<string, (r: FloodWatchRepository) => unknown> = {
  safe: (r) => r.markSafe(),
  help: (r) => r.requestHelp(),
  ack: (r) => r.acknowledgeTurnAround(),
  'select-alt': (r) => r.selectRoute('alternate'),
  minimize: (r) => r.minimizeCase(),
  restore: (r) => r.restoreCase(),
  dismiss: (r) => r.dismissResolved(),
  reset: (r) => r.reset(),
};

const TARGETS: Record<string, Href> = {
  home: '/',
  trips: '/trips',
  updates: '/updates',
  profile: '/profile',
  warning: '/warning',
  route: '/route-details',
  contact: '/contact',
  call: '/call-911',
};

export default function DevAction() {
  const repo = useRepository();
  const { do: action, to } = useLocalSearchParams<{ do?: string; to?: string }>();
  const ran = useRef(false);

  useEffect(() => {
    if (!__DEV__ || ran.current) return;
    ran.current = true;
    const target = to ? TARGETS[to] : undefined;
    if (target) setFlowExit(target);
    const run = async () => {
      try {
        if (action && SCENARIOS.includes(action as Scenario)) repo.setScenario(action as Scenario);
        else if (action && ACTIONS[action]) await ACTIONS[action](repo);
      } catch {
        // Simulated failures are shown by the screens themselves.
      }
      // Focused flows are navigated by FlowGate; only route explicitly otherwise.
      if (deriveFlowMode(repo.getSnapshot()) === 'normal') {
        if (router.canDismiss()) router.dismissAll();
        router.replace(target ?? '/');
      }
      else if (target) router.push(target);
    };
    void run();
  }, [action, to, repo]);

  return null;
}
