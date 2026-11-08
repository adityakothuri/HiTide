import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { cleanup, fireEvent, render, screen } from '@testing-library/react-native';
import type { ReactElement } from 'react';
import * as Speech from 'expo-speech';
import { type KeyValueStore, MockFloodWatchRepository } from '@/data/mockRepository';
import { RepositoryProvider } from '@/data/RepositoryProvider';
import type { Scenario } from '@/domain/types';
import { CheckInScreen } from '../CheckInScreen';
import { ContactScreen } from '../ContactScreen';
import { TurnAroundScreen } from '../TurnAroundScreen';
import { UpdatesScreen } from '../UpdatesScreen';

jest.mock('expo-router', () => ({
  router: {
    push: jest.fn(),
    navigate: jest.fn(),
    back: jest.fn(),
    replace: jest.fn(),
    canDismiss: () => false,
    dismissAll: jest.fn(),
  },
  useLocalSearchParams: () => ({}),
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest.mock factories must be synchronous
  useFocusEffect: (effect: () => void) => require('react').useEffect(effect, [effect]),
}));
jest.mock('@/map/FloodMap', () => ({ FloodMap: () => null }));
jest.mock('expo-speech', () => ({ speak: jest.fn(), stop: jest.fn() }));
jest.mock('@react-native-async-storage/async-storage', () =>
  // eslint-disable-next-line @typescript-eslint/no-require-imports -- jest.mock factories must be synchronous
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
// eslint-disable-next-line @typescript-eslint/no-require-imports -- jest.mock factories must be synchronous
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

const memory = (): KeyValueStore => {
  const data: Record<string, string> = {};
  return {
    getItem: async (k) => data[k] ?? null,
    setItem: async (k, v) => {
      data[k] = v;
    },
    removeItem: async (k) => {
      delete data[k];
    },
  };
};

let repo: MockFloodWatchRepository;

async function show(scenario: Scenario, ui: ReactElement) {
  repo = new MockFloodWatchRepository({ storage: memory(), latencyMs: 5, contactNotifyDelayMs: 50 });
  repo.setScenario(scenario);
  await render(<RepositoryProvider repository={repo}>{ui}</RepositoryProvider>);
}

const flush = (ms = 20) => new Promise((r) => setTimeout(r, ms));

beforeEach(() => {
  jest.clearAllMocks();
});
afterEach(async () => {
  await cleanup();
});

describe('Check-in screen', () => {
  it('records a help request once even when tapped repeatedly', async () => {
    await show('check_in', <CheckInScreen />);
    const help = await screen.findByRole('button', { name: 'I need help' });
    await fireEvent.press(help);
    await fireEvent.press(help);
    await flush();
    const events = repo.getSnapshot().safetyCase?.events ?? [];
    expect(events.filter((e) => e.kind === 'help_received')).toHaveLength(1);
    expect(repo.getSnapshot().safetyCase?.status).toBe('help_requested');
  });

  it('marks the user safe', async () => {
    await show('check_in', <CheckInScreen />);
    await fireEvent.press(await screen.findByRole('button', { name: 'I’m safe' }));
    await flush();
    expect(repo.getSnapshot().safetyCase?.status).toBe('safe');
  });

  it('shows an error and allows retry when the request fails', async () => {
    await show('check_in', <CheckInScreen />);
    repo.setSimulateFailures(true);
    await fireEvent.press(await screen.findByRole('button', { name: 'I need help' }));
    expect(await screen.findByText(/reach Flood Watch/)).toBeTruthy();
    expect(repo.getSnapshot().safetyCase?.status).toBe('checking');
  });
});

describe('Turn-around screen', () => {
  it('speaks the alert once and acknowledges into the alternate route', async () => {
    await show('turn_around', <TurnAroundScreen />);
    await screen.findByText('Closure reported on Riverside Drive');
    expect(Speech.speak).toHaveBeenCalledTimes(1);
    await fireEvent.press(screen.getByRole('button', { name: 'Show alternate route' }));
    const s = repo.getSnapshot();
    expect(s.alert?.acknowledged).toBe(true);
    expect(s.selectedRouteId).toBe('alternate');
  });

  it('does not speak when spoken alerts are off', async () => {
    repo = new MockFloodWatchRepository({ storage: memory(), latencyMs: 0 });
    await repo.setPreferences({ spokenAlerts: false });
    repo.setScenario('turn_around');
    await render(
      <RepositoryProvider repository={repo}>
        <TurnAroundScreen />
      </RepositoryProvider>,
    );
    expect(await screen.findByText('Voice guidance is off')).toBeTruthy();
    expect(Speech.speak).not.toHaveBeenCalled();
  });
});

describe('Updates screen', () => {
  it('filters by category and marks items read when opened', async () => {
    await show('help_requested', <UpdatesScreen />);
    await fireEvent.press(await screen.findByRole('tab', { name: 'Check-ins' }));
    expect(screen.getByText('Help request received')).toBeTruthy();
    expect(screen.queryByText('Flood warning near home')).toBeNull();

    await fireEvent.press(screen.getByRole('tab', { name: 'All' }));
    await fireEvent.press(screen.getByText('Flood warning near home'));
    expect(repo.getSnapshot().readIds).toContain('upd-warning');
  });
});

describe('Contact screen', () => {
  it('validates and saves an edited contact', async () => {
    await show('flood_warning', <ContactScreen />);
    await fireEvent.press(await screen.findByRole('button', { name: 'Edit contact' }));
    await fireEvent.changeText(screen.getByLabelText('Name'), 'Sam Lee');
    await fireEvent.changeText(screen.getByLabelText('Mobile number'), '12');
    await fireEvent.press(screen.getByRole('button', { name: 'Save contact' }));
    expect(screen.getByText('Enter a 10-digit phone number.')).toBeTruthy();
    expect(repo.getSnapshot().contact.name).toBe('Maria Whitfield');

    await fireEvent.changeText(screen.getByLabelText('Mobile number'), '(830) 555-0199');
    await fireEvent.press(screen.getByRole('button', { name: 'Save contact' }));
    expect(await screen.findByText('Contact saved.')).toBeTruthy();
    expect(repo.getSnapshot().contact).toMatchObject({ name: 'Sam Lee', phone: '(830) 555-0199' });
  });
});
