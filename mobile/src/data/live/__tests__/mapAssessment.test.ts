import { describe, expect, it } from '@jest/globals';
import { UPDATE_IDS } from '@/data/fixtures';
import { applyAssessment } from '@/data/live/mapAssessment';
import { type Assessment, isDangerEventFor, parseAssessment } from '@/data/live/schema';
import type { AppState } from '@/domain/types';
import { deriveFlowMode, initialState, reducer } from '@/state/reducer';
import realCriticalHelp from './assessment.critical-help.json';

const NOW = '2026-11-08T15:00:00.000Z';
const AT = '2025-07-04T12:00:00+00:00';
const T0 = Date.parse(AT) / 1000;

/** A live-mode starting state: no sample warning, closure, or case. */
function liveStart(): AppState {
  const s = reducer(initialState(NOW), { type: 'set_scenario', scenario: 'normal', now: NOW });
  return reducer(s, { type: 'set_connection', patch: { kind: 'live', status: 'connecting' } });
}

type Overrides = Partial<Omit<Assessment, 'hazard' | 'response'>> & {
  hazard?: Partial<Assessment['hazard']>;
  response?: Partial<NonNullable<Assessment['response']>>;
};

function assessment(o: Overrides = {}): Assessment {
  const base = parseAssessment({
    user_id: 'hc-dana',
    level: 'none',
    advice: 'none',
    reasons: [],
    stopped_in_water: false,
    assessed_at: AT,
    location: { lat: 30.0128, lon: -99.1169, ts: T0, state: 'parked', speed_mps: 0 },
    hazard: { road_name: 'Riverside Drive', alert_headlines: [], ahead: [], route: [] },
    response: { awaiting_reply: false, need_help: false, case_open: false, timeline: [] },
  });
  if (!base) throw new Error('base fixture must parse');
  return {
    ...base,
    ...o,
    hazard: { ...base.hazard, ...o.hazard },
    response: { ...base.response!, ...o.response },
  };
}

const FLOODED_AHEAD = {
  edge_id: 'e1',
  road_name: 'Park Street',
  distance_m: 420,
  depth_in: null,
  point_status: 'confirmed_flooded',
};

const warning = (): Assessment =>
  assessment({
    level: 'warning',
    advice: 'move_to_high_ground',
    reasons: ['Flash Flood Warning covers your location'],
    hazard: { alert_headlines: ['REPLAY of July 4, 2025: Flash Flood Warning for Kerr County'] },
  });

const turnAround = (road = 'Park Street'): Assessment =>
  assessment({
    level: 'danger',
    advice: 'turn_around',
    reasons: [`${road} is confirmed flooded ahead`],
    location: { lat: 30.03, lon: -99.13, ts: T0, state: 'driving', speed_mps: 13 },
    hazard: { ahead: [{ ...FLOODED_AHEAD, edge_id: `edge-${road}`, road_name: road }], alert_headlines: ['Flash Flood Emergency for Hunt to Kerrville'] },
  });

const stoppedAwaiting = (): Assessment =>
  assessment({
    level: 'critical',
    advice: 'move_to_high_ground',
    reasons: ['Park Street over Quinlan Creek is confirmed flooded where you are'],
    location: { lat: 30.03785, lon: -99.13361, ts: T0, state: 'parked', speed_mps: 0 },
    hazard: {
      road_name: 'Park Street',
      worst_point: { id: 'cp-0043', name: 'Park Street', status: 'confirmed_flooded', distance_m: 0, on_my_road: true },
    },
    response: {
      awaiting_reply: true,
      case_open: true,
      called: true,
      timeline: [{ t: T0, what: 'critical -> voice:critical_call, open_case:case' }],
    },
  });

describe('parseAssessment', () => {
  it('accepts the real backend payload', () => {
    const a = parseAssessment(realCriticalHelp);
    expect(a?.user_id).toBe('hc-dana');
    expect(a?.response?.need_help).toBe(true);
  });

  it('rejects malformed payloads instead of throwing', () => {
    expect(parseAssessment(null)).toBeNull();
    expect(parseAssessment({ user_id: 'x', level: 'catastrophic' })).toBeNull();
    expect(parseAssessment({ ...realCriticalHelp, hazard: 'flooded' })).toBeNull();
  });

  it('recognises only user.danger events for this user', () => {
    expect(isDangerEventFor({ type: 'user.danger', payload: { user_id: 'hc-dana' } }, 'hc-dana')).toBe(true);
    expect(isDangerEventFor({ type: 'user.danger', payload: { user_id: 'hc-ruth' } }, 'hc-dana')).toBe(false);
    expect(isDangerEventFor({ type: 'segments.update', payload: {} }, 'hc-dana')).toBe(false);
    expect(isDangerEventFor('garbage', 'hc-dana')).toBe(false);
  });
});

describe('applyAssessment', () => {
  it('no danger: no warning, no alert, no case, ordinary tabs', () => {
    const s = applyAssessment(liveStart(), assessment());
    expect(s.warning).toBeNull();
    expect(s.alert).toBeNull();
    expect(s.safetyCase).toBeNull();
    expect(deriveFlowMode(s)).toBe('normal');
    expect(s.connection).toMatchObject({ status: 'live', level: 'none', assessedAt: AT });
  });

  it('warning: shows the NWS headline without inventing issue or expiry times', () => {
    const s = applyAssessment(liveStart(), warning());
    expect(s.warning).toMatchObject({ event: 'Flash Flood Warning', area: 'Kerr County', issuedAt: null, expiresAt: null });
    expect(s.warning?.source).toMatch(/replay of July 4, 2025/);
    expect(s.updates.some((u) => u.id === UPDATE_IDS.warning)).toBe(true);
    expect(deriveFlowMode(s)).toBe('normal');
  });

  it('turn-around while driving: one unacknowledged alert for the flooded road ahead, plus a closure', () => {
    const s = applyAssessment(liveStart(), turnAround());
    expect(deriveFlowMode(s)).toBe('turn_around');
    expect(s.alert).toMatchObject({ road: 'Park Street', acknowledged: false });
    expect(s.trip.closure?.road).toBe('Park Street');
    expect(s.trip.closure?.source).toMatch(/depth not measured/);
    expect(s.trip.routes.original.affectedRoad).toBe('Park Street');
  });

  it('keeps the same alert across repeated assessments, so speech plays once', () => {
    const once = applyAssessment(liveStart(), turnAround());
    const twice = applyAssessment(once, turnAround());
    expect(twice.alert).toBe(once.alert);
  });

  it('an acknowledged alert is not re-raised for the same road', () => {
    const raised = applyAssessment(liveStart(), turnAround());
    const acked = reducer(raised, { type: 'acknowledge_turn_around', now: NOW });
    expect(acked.selectedRouteId).toBe('alternate');
    const again = applyAssessment(acked, turnAround());
    expect(again.alert?.acknowledged).toBe(true);
    expect(deriveFlowMode(again)).toBe('normal');
  });

  it('a different flooded road raises a new alert', () => {
    const first = reducer(applyAssessment(liveStart(), turnAround()), { type: 'acknowledge_turn_around', now: NOW });
    const next = applyAssessment(first, turnAround('Park Lane'));
    expect(next.alert).toMatchObject({ road: 'Park Lane', acknowledged: false });
  });

  it('turn-around advice is ignored when parked (no driving instruction to a stopped car)', () => {
    const parked = turnAround();
    const s = applyAssessment(liveStart(), { ...parked, location: { ...parked.location!, state: 'parked' } });
    expect(s.alert).toBeNull();
  });

  it('stopped near water awaiting a reply opens the check-in, which outranks the alert', () => {
    const alerted = applyAssessment(liveStart(), turnAround());
    const s = applyAssessment(alerted, stoppedAwaiting());
    expect(deriveFlowMode(s)).toBe('check_in');
    expect(s.safetyCase).toMatchObject({ status: 'checking', locationLabel: 'Park Street', location: [-99.13361, 30.03785] });
    expect(s.safetyCase?.events[0]).toMatchObject({ kind: 'stop_detected', at: new Date(T0 * 1000).toISOString() });
  });

  it('the real HELP payload becomes support status with the backend timeline', () => {
    const real = parseAssessment(realCriticalHelp)!;
    const s = applyAssessment(applyAssessment(liveStart(), stoppedAwaiting()), real);
    expect(deriveFlowMode(s)).toBe('support');
    const kinds = s.safetyCase?.events.map((e) => e.kind);
    expect(kinds).toEqual(expect.arrayContaining(['stop_detected', 'help_received', 'contact_notified', 'responders_flagged']));
    expect(s.safetyCase?.events.find((e) => e.kind === 'contact_notified')?.simulated).toBe(true);
  });

  it('never downgrades a local help request while the backend catches up', () => {
    const checking = applyAssessment(liveStart(), stoppedAwaiting());
    const helped = reducer(checking, { type: 'request_help', now: NOW });
    const s = applyAssessment(helped, stoppedAwaiting());
    expect(s.safetyCase?.status).toBe('help_requested');
  });

  it('keeps an open help case even if the backend level drops', () => {
    const real = parseAssessment(realCriticalHelp)!;
    const helped = applyAssessment(liveStart(), real);
    const s = applyAssessment(helped, assessment());
    expect(s.safetyCase?.status).toBe('help_requested');
  });

  it('a SAFE reply resolves the case; dismissing it does not bring it back', () => {
    const checking = applyAssessment(liveStart(), stoppedAwaiting());
    const safeReply = stoppedAwaiting();
    const replied: Assessment = {
      ...safeReply,
      response: {
        ...safeReply.response!,
        awaiting_reply: false,
        timeline: [...safeReply.response!.timeline, { t: T0 + 30, what: 'SAFE from driver' }],
      },
    };
    const resolved = applyAssessment(checking, replied);
    expect(deriveFlowMode(resolved)).toBe('resolved');
    const dismissed = reducer(resolved, { type: 'dismiss_resolved' });
    expect(applyAssessment(dismissed, replied).safetyCase).toBeNull();
  });

  it('all clear: drops the warning, the alert, and the closure', () => {
    const alerted = applyAssessment(liveStart(), turnAround());
    const s = applyAssessment(alerted, assessment({ level: 'watch' }));
    expect(s.warning).toBeNull();
    expect(s.alert).toBeNull();
    expect(s.trip.closure).toBeNull();
    expect(s.selectedRouteId).toBe('original');
  });

  it('does not touch state while a developer scenario is shown', () => {
    const paused = reducer(liveStart(), { type: 'set_connection', patch: { paused: true } });
    const s = reducer(paused, { type: 'apply_remote', assessment: turnAround() });
    expect(s).toBe(paused);
  });

  it('keeps an unchanged update item (and its read state) across polls', () => {
    const first = applyAssessment(liveStart(), warning());
    const read = reducer(first, { type: 'mark_read', id: UPDATE_IDS.warning });
    const second = applyAssessment(read, { ...warning(), assessed_at: '2025-07-04T12:05:00+00:00' });
    expect(second.readIds).toContain(UPDATE_IDS.warning);
    expect(second.updates.find((u) => u.id === UPDATE_IDS.warning)?.at).toBe(
      first.updates.find((u) => u.id === UPDATE_IDS.warning)?.at,
    );
  });

  it('dates the check-in from the stop (the critical call), not an earlier driving alert', () => {
    const real = parseAssessment(realCriticalHelp)!;
    const s = applyAssessment(liveStart(), real);
    const critical = real.response!.timeline.find((e) => e.what.startsWith('critical ->'))!;
    expect(s.safetyCase?.events.find((e) => e.kind === 'stop_detected')?.at).toBe(new Date(critical.t * 1000).toISOString());
  });

  it('ignores timeline entries from an earlier episode (before the last all clear)', () => {
    const base = stoppedAwaiting();
    const fresh: Assessment = {
      ...base,
      response: {
        ...base.response!,
        timeline: [
          { t: T0 - 900, what: 'SAFE from driver' },
          { t: T0 - 600, what: 'all clear' },
          ...base.response!.timeline,
        ],
      },
    };
    const s = applyAssessment(liveStart(), fresh);
    expect(s.safetyCase?.status).toBe('checking');
    expect(s.safetyCase?.events.some((e) => e.kind === 'marked_safe')).toBe(false);
  });

  it('an acknowledged alert survives a brief drop in level, so the same road is not spoken again', () => {
    const acked = reducer(applyAssessment(liveStart(), turnAround()), { type: 'acknowledge_turn_around', now: NOW });
    const dipped = applyAssessment(acked, assessment({ level: 'watch' }));
    const back = applyAssessment(dipped, turnAround());
    expect(back.alert?.acknowledged).toBe(true);
    expect(deriveFlowMode(back)).toBe('normal');
  });

  it('a stale location never raises a turn-around', () => {
    const s = applyAssessment(liveStart(), { ...turnAround(), location_stale: true });
    expect(s.alert).toBeNull();
  });

  it('stopped in water without a backend check-in does not open the check-in flow', () => {
    const s = applyAssessment(liveStart(), assessment({ level: 'danger', stopped_in_water: true }));
    expect(s.safetyCase).toBeNull();
  });

  it('a flooded hit with zero depth is still "depth not measured", never a measured 0 in', () => {
    const t = turnAround();
    const s = applyAssessment(liveStart(), { ...t, hazard: { ...t.hazard, ahead: [{ ...FLOODED_AHEAD, depth_in: 0 }] } });
    expect(s.trip.closure?.source).toMatch(/depth not measured/);
  });

  it('drops the "alternate route selected" item once no closure remains', () => {
    const acked = reducer(applyAssessment(liveStart(), turnAround()), { type: 'acknowledge_turn_around', now: NOW });
    expect(acked.updates.some((u) => u.id === UPDATE_IDS.routeSelected)).toBe(true);
    const clear = applyAssessment(acked, assessment({ level: 'none' }));
    expect(clear.updates.some((u) => u.id === UPDATE_IDS.routeSelected)).toBe(false);
  });

  it('says the contact was notified only when the backend reports it', () => {
    const base = stoppedAwaiting();
    const help: Assessment = {
      ...base,
      response: { ...base.response!, need_help: true, family_contacted: false, timeline: [...base.response!.timeline, { t: T0 + 5, what: 'HELP from driver -> responders flagged' }] },
    };
    const s = applyAssessment(liveStart(), help);
    expect(s.safetyCase?.events.some((e) => e.kind === 'contact_notified')).toBe(false);
    expect(s.updates.find((u) => u.id === UPDATE_IDS.help)?.body).not.toMatch(/contact is being notified/);
  });
});

describe('parseAssessment hardening', () => {
  it('rejects non-finite timeline times and non-ISO assessed_at', () => {
    expect(parseAssessment({ ...realCriticalHelp, assessed_at: 'yesterday' })).toBeNull();
    const bad = { ...realCriticalHelp, response: { ...realCriticalHelp.response, timeline: [{ t: 1e300, what: 'x' }] } };
    expect(parseAssessment(bad)).toBeNull();
  });

  it('tolerates an unknown motion state or confidence instead of dropping a critical assessment', () => {
    const odd = { ...realCriticalHelp, confidence: 'unsure', location: { ...realCriticalHelp.location, state: 'towed' } };
    const a = parseAssessment(odd);
    expect(a?.level).toBe('critical');
    expect(a?.location?.state).toBeNull();
  });
});

describe('review fixes: ordering, alert identity, quiet resolution', () => {
  it('ignores an assessment older than the one shown (a late poll), but accepts a replay rewind', () => {
    const now = reducer(liveStart(), { type: 'apply_remote', assessment: { ...turnAround(), assessed_at: '2025-07-04T12:10:00+00:00' } });
    const late = reducer(now, { type: 'apply_remote', assessment: { ...assessment(), assessed_at: '2025-07-04T12:05:00+00:00' } });
    expect(late).toBe(now);
    const rewound = reducer(now, { type: 'apply_remote', assessment: { ...assessment(), assessed_at: '2025-07-04T05:00:00+00:00' } });
    expect(rewound.alert).toBeNull();
  });

  it('an unchanged connection patch is a no-op (no re-render every poll)', () => {
    const once = reducer(liveStart(), { type: 'apply_remote', assessment: warning() });
    expect(reducer(once, { type: 'set_connection', patch: { status: 'live' } })).toBe(once);
    expect(reducer(once, { type: 'set_connection', patch: { mode: undefined } })).toBe(once);
  });

  it('keeps the acknowledged alert when the look-ahead hit disappears while turn-around advice continues', () => {
    const acked = reducer(applyAssessment(liveStart(), turnAround()), { type: 'acknowledge_turn_around', now: NOW });
    const t = turnAround();
    const noHit: Assessment = { ...t, assessed_at: '2025-07-04T12:01:00+00:00', hazard: { ...t.hazard, ahead: [] } };
    const s = applyAssessment(acked, noHit);
    expect(s.alert).toBe(acked.alert);
    expect(deriveFlowMode(s)).toBe('normal');
  });

  it('a SAFE reply by text closes the check-in into the resolved screen, not silently', () => {
    const checking = applyAssessment(liveStart(), stoppedAwaiting());
    const base = stoppedAwaiting();
    const viaSms: Assessment = {
      ...base,
      response: { ...base.response!, awaiting_reply: false, case_open: false, timeline: [...base.response!.timeline, { t: T0 + 60, what: 'SAFE from driver' }] },
    };
    expect(deriveFlowMode(applyAssessment(checking, viaSms))).toBe('resolved');
  });

  it('a safe/help poll while still driving does not open the check-in; the turn-around shows instead', () => {
    const t = turnAround();
    const polledWhileDriving: Assessment = {
      ...t,
      response: { ...t.response!, awaiting_reply: true, timeline: [{ t: T0, what: 'danger -> poll:danger_poll' }] },
    };
    const s = applyAssessment(liveStart(), polledWhileDriving);
    expect(s.safetyCase).toBeNull();
    expect(deriveFlowMode(s)).toBe('turn_around');
  });

  it('degraded evidence never reads as clear: the connection carries it to Home', () => {
    const s = applyAssessment(liveStart(), assessment({ level: 'none', hazard: { degraded_sources: ['nws_alerts'] } }));
    expect(s.connection.degraded).toBe(true);
    const low = applyAssessment(liveStart(), assessment({ level: 'watch', confidence: 'low', reasons: ['Creek rising nearby'] }));
    expect(low.connection.degraded).toBe(true);
    expect(low.connection.topReason).toBe('Creek rising nearby');
  });

  it('an acknowledged alert is cleared once the danger is fully over (level none)', () => {
    const acked = reducer(applyAssessment(liveStart(), turnAround()), { type: 'acknowledge_turn_around', now: NOW });
    expect(applyAssessment(acked, assessment({ level: 'none' })).alert).toBeNull();
  });

  it('route-check hits for the alternate are not drawn as a closure on the usual route', () => {
    const acked = reducer(applyAssessment(liveStart(), turnAround()), { type: 'acknowledge_turn_around', now: NOW });
    const t = turnAround();
    const altHit: Assessment = {
      ...t,
      advice: 'move_to_high_ground',
      assessed_at: '2025-07-04T12:02:00+00:00',
      hazard: { ...t.hazard, ahead: [], route: [{ ...FLOODED_AHEAD, edge_id: 'alt-1', road_name: 'Memorial Boulevard' }] },
    };
    const s = applyAssessment(acked, altHit);
    expect(s.trip.closure?.road).toBe('Park Street');
  });

  it('maps the backend assistant entries: requested, then the call summary', () => {
    const base = stoppedAwaiting();
    const withCall = (what: string): Assessment => ({
      ...base,
      response: { ...base.response!, timeline: [...base.response!.timeline, { t: T0 + 60, what }] },
    });
    const requested = applyAssessment(liveStart(), withCall('assistant call requested'));
    expect(requested.safetyCase?.events.find((e) => e.kind === 'assistant_call')).toMatchObject({
      detail: 'Calling the HiTide assistant',
      simulated: false,
    });
    const done = applyAssessment(requested, withCall('assistant call: Caller is on the roof and asked for help.'));
    expect(done.safetyCase?.events.find((e) => e.kind === 'assistant_call')?.detail).toBe(
      'Caller is on the roof and asked for help.',
    );
  });
});


describe('outreach: call placed and the latest outreach entry', () => {
  const at = (what: string, dt = 0) => ({ t: T0 + dt, what });

  it('a critical call to the driver sets callPlaced (shown as the check-in banner)', () => {
    const s = applyAssessment(
      liveStart(),
      assessment({
        level: 'critical',
        response: { case_open: true, awaiting_reply: true, timeline: [at('critical -> voice:critical_call, open_case:case')] },
      }),
    );
    expect(s.connection.callPlaced).toBe(true);
    expect(s.connection.lastOutreach).toBe('critical -> voice:critical_call, open_case:case');
    expect(deriveFlowMode(s)).toBe('check_in');
  });

  it('a danger call and a "no reply to poll -> call" both count as a call', () => {
    const danger = applyAssessment(liveStart(), assessment({ level: 'danger', response: { timeline: [at('danger -> voice:danger_call')] } }));
    expect(danger.connection.callPlaced).toBe(true);
    const polled = applyAssessment(
      liveStart(),
      assessment({ level: 'danger', response: { timeline: [at('danger -> poll:danger_poll'), at('no reply to poll -> call', 60)] } }),
    );
    expect(polled.connection.callPlaced).toBe(true);
  });

  it('a text or a poll is not a call; a call from an earlier episode no longer counts', () => {
    const texted = applyAssessment(liveStart(), assessment({ level: 'warning', response: { timeline: [at('warning -> text:warning')] } }));
    expect(texted.connection.callPlaced).toBe(false);
    expect(texted.connection.lastOutreach).toBe('warning -> text:warning');
    const earlier = applyAssessment(
      liveStart(),
      assessment({ response: { timeline: [at('critical -> voice:critical_call'), at('all clear', 600)] } }),
    );
    expect(earlier.connection.callPlaced).toBe(false);
    expect(earlier.connection.lastOutreach).toBeNull();
  });
});
