import { UPDATE_IDS } from '@/data/fixtures';
import type { UpdateItem } from '@/domain/types';

/** Update-feed items shared by the scenario reducer and the live backend mapping. */

export function routeSelectedUpdate(now: string, via: string): UpdateItem {
  return {
    id: UPDATE_IDS.routeSelected,
    category: 'trips',
    icon: 'route',
    title: 'Alternate route selected',
    body: `Your work trip now goes via ${via}`,
    at: now,
    target: 'route',
    actionLabel: 'View route',
  };
}

export function turnAroundUpdate(now: string, road: string): UpdateItem {
  return {
    id: UPDATE_IDS.turnAround,
    category: 'trips',
    icon: 'warning',
    title: 'Turn-around alert',
    body: `Flooded road reported ahead on ${road}`,
    at: now,
    target: 'route',
    actionLabel: 'Review route',
  };
}

export type CaseUpdateKind = 'check_in' | 'help' | 'safe';

/** `helpBody` overrides the help item's text (live mode describes what the backend actually did). */
export function caseUpdate(kind: CaseUpdateKind, now: string, helpBody = 'Simulated workflow · Sample data'): UpdateItem {
  const content = {
    check_in: { id: UPDATE_IDS.checkIn, title: 'Safety check-in sent', body: 'We noticed a stop near a reported flood' },
    help: { id: UPDATE_IDS.help, title: 'Help request received', body: helpBody },
    safe: { id: UPDATE_IDS.safe, title: 'You marked yourself safe', body: 'Thanks for checking in' },
  }[kind];
  return { ...content, category: 'checkins', icon: 'shield', at: now, target: 'case' };
}
