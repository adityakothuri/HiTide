import { router } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Linking } from 'react-native';
import { useRepository } from '@/data/RepositoryProvider';
import type { AssistantLine } from '@/domain/types';

const TEL = /^\+?[0-9]{7,15}$/;

/** Open the dialer for a validated number. False when this device can't place calls (simulator, iPad). */
export async function openDialer(phone: string | null): Promise<boolean> {
  if (!phone || !TEL.test(phone)) return false;
  const url = `tel:${phone}`;
  try {
    if (!(await Linking.canOpenURL(url))) return false;
    await Linking.openURL(url);
    return true;
  } catch {
    return false;
  }
}

/** Dial the assistant's number if this device can; otherwise the sheet shows it to call from another phone. */
export function dialAssistant(line: AssistantLine): Promise<boolean> {
  return line.mode === 'live' ? openDialer(line.phone) : Promise.resolve(false);
}

/** "Call the HiTide assistant": prepare the line on the backend, then open the dialer or the assistant sheet. */
export function useAssistantCall() {
  const repo = useRepository();
  const [isPending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );

  const call = useCallback(async () => {
    if (inFlight.current) return; // a second tap before the first finishes does nothing
    inFlight.current = true;
    setError(null);
    setPending(true);
    try {
      const line = await repo.callAssistant();
      const dialled = await dialAssistant(line);
      if (!dialled) router.navigate('/assistant'); // navigate, not push: "Call again" on the sheet doesn't stack it
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : 'Couldn’t reach the assistant. Try again.');
    } finally {
      inFlight.current = false;
      if (mounted.current) setPending(false);
    }
  }, [repo]);

  return { call, isPending, error };
}
