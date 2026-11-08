import type { AppState, RouteOption, UpdateCategory, UpdateItem } from '@/domain/types';

export type UpdateFilter = 'all' | Exclude<UpdateCategory, 'general'>;

export function visibleUpdates(state: AppState, filter: UpdateFilter): UpdateItem[] {
  const items = filter === 'all' ? [...state.updates] : state.updates.filter((u) => u.category === filter);
  return items.sort((a, b) => b.at.localeCompare(a.at));
}

export const isRead = (state: AppState, id: string): boolean => state.readIds.includes(id);

export const unreadCount = (state: AppState): number => state.updates.filter((u) => !isRead(state, u.id)).length;

export const selectedRoute = (state: AppState): RouteOption => state.trip.routes[state.selectedRouteId];

/** True when the route the user is set to take crosses a reported closure. */
export const selectedRouteAffected = (state: AppState): boolean =>
  state.trip.closure !== null && selectedRoute(state).affectedRoad !== null;

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
}

export function greeting(nowIso: string): string {
  const h = new Date(nowIso).getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}
