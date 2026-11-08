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
}

/** Web and fallback: the offline vector map. Native platforms use MapCanvas.native.tsx. */
export function MapCanvas({ scene }: MapCanvasProps) {
  return <VectorMap scene={scene} />;
}

export const supportsSatellite = false;
