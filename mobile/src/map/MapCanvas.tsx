import type { LngLat } from '@/domain/types';
import type { MapScene } from './scene';
import { VectorMap } from './VectorMap';

export interface MapCanvasProps {
  scene: MapScene;
  interactive: boolean;
  /** Increment to animate back to the scene's region. */
  recenterToken: number;
  satellite: boolean;
  /** Space covered by an overlapping sheet; keeps markers and map attribution visible. */
  bottomInset: number;
  /** Called with the tapped map position (Set location). Omit for maps that don't take taps. */
  onPressCoordinate?: (p: LngLat) => void;
  /** A dropped pin to draw, if any. */
  pin?: LngLat | null;
}

/** Web and fallback: the offline vector map. Native platforms use MapCanvas.native.tsx. */
export function MapCanvas({ scene, onPressCoordinate, pin }: MapCanvasProps) {
  return <VectorMap scene={scene} onPressCoordinate={onPressCoordinate} pin={pin} />;
}

export const supportsSatellite = false;
