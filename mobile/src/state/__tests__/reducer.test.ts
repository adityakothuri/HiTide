import { describe, expect, it } from '@jest/globals';
import { UPDATE_IDS } from '@/data/fixtures';
import { buildScenario, deriveFlowMode, initialState, reducer } from '../reducer';
import { selectedRouteAffected, unreadCount, visibleUpdates } from '../selectors';

const NOW = '2026-11-08T15:30:00.000Z';
const LATER = '2026-11-08T15:31:00.000Z';
const carry = (s = initialState(NOW)) => ({
  contact: s.contact,
  preferences: s.preferences,
  selectedRouteId: s.selectedRouteId,
  readIds: s.readIds,
});

describe('flow precedence', () => {
  it('shows ordinary tabs for a flood warning without an alert or case', () => {
    expect(deriveFlowMode(buildScenario('flood_warning', carry(), NOW))).toBe('normal');
  });

  it('shows the turn-around alert until it is acknowledged', () => {
    const s = buildScenario('turn_around', carry(), NOW);
    expect(deriveFlowMode(s)).toBe('turn_around');
    expect(deriveFlowMode(reducer(s, { type: 'acknowledge_turn_around', now: LATER }))).toBe('normal');
  });

  it('gives an open safety case precedence over an active turn-around alert', () => {
    const alert = buildScenario('turn_around', carry(), NOW);
    const withCase = { ...alert, safetyCase: buildScenario('check_in', carry(), NOW).safetyCase };
    expect(deriveFlowMode(withCase)).toBe('check_in');
  });

  it('keeps a minimized help request active but returns to tabs', () => {
    const s = reducer(buildScenario('help_requested', carry(), NOW), { type: 'minimize_case' });
    expect(deriveFlowMode(s)).toBe('normal');
    expect(s.safetyCase?.status).toBe('help_requested');
    expect(deriveFlowMode(reducer(s, { type: 'restore_case' }))).toBe('support');
  });
});

describe('check-in responses', () => {
  const checking = () => buildScenario('check_in', carry(), NOW);

  it('marks the user safe and shows the resolved state, then clears the case', () => {
    const safe = reducer(checking(), { type: 'mark_safe', now: LATER });
    expect(safe.safetyCase?.status).toBe('safe');
    expect(safe.safetyCase?.events.at(-1)).toMatchObject({ kind: 'marked_safe', at: LATER });
    expect(deriveFlowMode(safe)).toBe('resolved');
    const done = reducer(safe, { type: 'dismiss_resolved' });
    expect(done.safetyCase).toBeNull();
    expect(deriveFlowMode(done)).toBe('normal');
  });

  it('records a help request exactly once', () => {
    const once = reducer(checking(), { type: 'request_help', now: LATER });
    const twice = reducer(once, { type: 'request_help', now: LATER });
    expect(twice).toBe(once);
    expect(once.safetyCase?.events.filter((e) => e.kind === 'help_received')).toHaveLength(1);
    expect(deriveFlowMode(once)).toBe('support');
  });

  it('records the simulated contact notification once, only after a help request', () => {
    expect(reducer(checking(), { type: 'contact_notified', now: LATER })).toEqual(checking());
    const help = reducer(checking(), { type: 'request_help', now: NOW });
    const notified = reducer(help, { type: 'contact_notified', now: LATER });
    const again = reducer(notified, { type: 'contact_notified', now: LATER });
    expect(again).toBe(notified);
    expect(notified.safetyCase?.events.find((e) => e.kind === 'contact_notified')).toMatchObject({
      at: LATER,
      simulated: true,
    });
  });
});

describe('route acceptance', () => {
  it('selecting the alternate route clears the affected flag and adds a trip update', () => {
    const s = buildScenario('flood_warning', carry(), NOW);
    expect(selectedRouteAffected(s)).toBe(true);
    const next = reducer(s, { type: 'select_route', routeId: 'alternate', now: LATER });
    expect(next.selectedRouteId).toBe('alternate');
    expect(selectedRouteAffected(next)).toBe(false);
    expect(visibleUpdates(next, 'trips').map((u) => u.id)).toContain(UPDATE_IDS.routeSelected);
  });

  it('acknowledging a turn-around selects the alternate route', () => {
    const next = reducer(buildScenario('turn_around', carry(), NOW), { type: 'acknowledge_turn_around', now: LATER });
    expect(next.selectedRouteId).toBe('alternate');
    expect(next.alert?.acknowledged).toBe(true);
  });

  it('ignores an alternate selection when there is no closure', () => {
    const s = buildScenario('normal', carry(), NOW);
    expect(reducer(s, { type: 'select_route', routeId: 'alternate', now: LATER })).toBe(s);
  });
});

describe('updates and preferences', () => {
  it('filters updates by category', () => {
    const s = buildScenario('help_requested', carry(), NOW);
    expect(visibleUpdates(s, 'checkins').every((u) => u.category === 'checkins')).toBe(true);
    expect(visibleUpdates(s, 'trips').every((u) => u.category === 'trips')).toBe(true);
    expect(visibleUpdates(s, 'all')).toHaveLength(s.updates.length);
  });

  it('marks updates read once', () => {
    const s = buildScenario('flood_warning', carry(), NOW);
    const before = unreadCount(s);
    const read = reducer(s, { type: 'mark_read', id: UPDATE_IDS.warning });
    expect(unreadCount(read)).toBe(before - 1);
    expect(reducer(read, { type: 'mark_read', id: UPDATE_IDS.warning })).toBe(read);
  });

  it('keeps preferences and contact edits across scenario changes, and reset restores defaults', () => {
    let s = initialState(NOW);
    s = reducer(s, { type: 'set_preferences', patch: { spokenAlerts: false } });
    s = reducer(s, { type: 'update_contact', contact: { name: 'Sam Lee', relationship: 'Friend', phone: '8305550199' } });
    s = reducer(s, { type: 'set_scenario', scenario: 'turn_around', now: LATER });
    expect(s.preferences.spokenAlerts).toBe(false);
    expect(s.contact.name).toBe('Sam Lee');
    const reset = reducer(s, { type: 'reset', now: LATER });
    expect(reset.preferences.spokenAlerts).toBe(true);
    expect(reset.contact.name).toBe('Maria Whitfield');
    expect(reset.alert).toBeNull();
  });
});
