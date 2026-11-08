import { type Href, router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef } from 'react';
import { useRepository } from '@/data/RepositoryProvider';
import { type HiTideRepository, isValidLngLat } from '@/data/repository';
import type { LngLat, Scenario } from '@/domain/types';
import { setFlowExit } from '@/state/flowGate';
import { deriveFlowMode } from '@/state/reducer';

/**
 * Development-only deep link for scripted review, e.g.
 *   exp://127.0.0.1:8081/--/dev-action?do=check_in
 *   exp://127.0.0.1:8081/--/dev-action?do=help
 *   exp://127.0.0.1:8081/--/dev-action?do=pin&lon=-99.13361&lat=30.03785
 *   exp://127.0.0.1:8081/--/dev-action?to=set-location
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

const ACTIONS: Record<string, (r: HiTideRepository) => unknown> = {
  safe: (r) => r.markSafe(),
  help: (r) => r.requestHelp(),
  ack: (r) => r.acknowledgeTurnAround(),
  'select-alt': (r) => r.selectRoute('alternate'),
  minimize: (r) => r.minimizeCase(),
  restore: (r) => r.restoreCase(),
  dismiss: (r) => r.dismissResolved(),
  reset: (r) => r.reset(),
  // Presentation: scripted table demo (live mode). The drive is started after the reset finishes.
  'reset-demo': (r) => r.resetDemo(),
  drive: (r) => r.startDemoDrive(),
  assistant: (r) => r.callAssistant(),
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
  'flood-map': '/flood-map',
  assistant: '/assistant',
  'set-location': '/set-location',
  'location-result': '/location-result',
};

/** `pin` params: finite numbers within ±180 / ±90, or null. */
function parsePin(lon: string | undefined, lat: string | undefined): LngLat | null {
  if (!lon || !lat) return null;
  const p: readonly number[] = [Number(lon), Number(lat)];
  return isValidLngLat(p) ? p : null;
}

export default function DevAction() {
  const repo = useRepository();
  const { do: action, to, lon, lat } = useLocalSearchParams<{ do?: string; to?: string; lon?: string; lat?: string }>();
  const ran = useRef<string | null>(null);

  useEffect(() => {
    const key = `${action ?? ''}|${to ?? ''}|${lon ?? ''}|${lat ?? ''}`;
    if (!__DEV__ || ran.current === key) return; // once per distinct link (the route can be reused)
    ran.current = key;
    const pin = action === 'pin' ? parsePin(lon, lat) : null;
    // A pin that isn't flooded or dangerous lands on its result, like the Set location screen.
    const target = to ? TARGETS[to] : pin ? TARGETS['location-result'] : undefined;
    if (target) setFlowExit(target);
    const run = async () => {
      try {
        if (action === 'pin') {
          if (pin) await repo.setLocation(pin);
        } else if (action && SCENARIOS.includes(action as Scenario)) repo.setScenario(action as Scenario);
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
  }, [action, to, lon, lat, repo]);

  return null;
}
