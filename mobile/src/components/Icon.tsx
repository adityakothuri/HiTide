import { View } from 'react-native';
import Svg, { Circle, Path, Rect } from 'react-native-svg';
import { color as palette } from '@/theme/tokens';

export type IconName =
  | 'home'
  | 'car'
  | 'bell'
  | 'person'
  | 'warning'
  | 'chevronRight'
  | 'chevronLeft'
  | 'pin'
  | 'locate'
  | 'layers'
  | 'navigate'
  | 'briefcase'
  | 'shield'
  | 'shieldCheck'
  | 'pinCheck'
  | 'speaker'
  | 'speakerOff'
  | 'phone'
  | 'check'
  | 'chatCheck'
  | 'arrowRight'
  | 'close'
  | 'route'
  | 'clock'
  | 'info';

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
  strokeWidth?: number;
}

/** One consistent 24px line-icon set (1.8 stroke, round caps) used across the app. */
export function Icon({ name, size = 24, color = palette.ink, strokeWidth = 1.8 }: IconProps) {
  const p: StrokeProps = { stroke: color, strokeWidth, fill: 'none', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  return (
    <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants" aria-hidden>
      <Svg width={size} height={size} viewBox="0 0 24 24">
      {renderIcon(name, p, color)}
    </Svg>
    </View>
  );
}

type StrokeProps = {
  stroke: string;
  strokeWidth: number;
  fill: 'none';
  strokeLinecap: 'round';
  strokeLinejoin: 'round';
};

function renderIcon(name: IconName, p: StrokeProps, c: string) {
  switch (name) {
    case 'home':
      return <Path {...p} d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z" />;
    case 'car':
      return (
        <>
          <Path {...p} d="M5 16.5V12l1.7-4.4A2 2 0 0 1 8.6 6.3h6.8a2 2 0 0 1 1.9 1.3L19 12v4.5" />
          <Rect {...p} x="3.5" y="11.5" width="17" height="5.5" rx="1.5" />
          <Path {...p} d="M6.5 17v2M17.5 17v2M7.5 14.2h1M15.5 14.2h1" />
        </>
      );
    case 'bell':
      return <Path {...p} d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15zM10 20.5a2.2 2.2 0 0 0 4 0" />;
    case 'person':
      return (
        <>
          <Circle {...p} cx="12" cy="8" r="3.6" />
          <Path {...p} d="M4.8 20c.8-3.6 3.6-5.6 7.2-5.6s6.4 2 7.2 5.6" />
        </>
      );
    case 'warning':
      return <Path {...p} d="M12 4 21 19.5H3zM12 10v4.2M12 17h.01" />;
    case 'chevronRight':
      return <Path {...p} d="m9.5 5.5 6.5 6.5-6.5 6.5" />;
    case 'chevronLeft':
      return <Path {...p} d="M14.5 5.5 8 12l6.5 6.5" />;
    case 'pin':
      return (
        <>
          <Path {...p} d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z" />
          <Circle {...p} cx="12" cy="10" r="2.3" />
        </>
      );
    case 'pinCheck':
      return (
        <>
          <Path {...p} d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z" />
          <Path {...p} d="m9.3 10 1.9 1.9 3.6-3.7" />
        </>
      );
    case 'locate':
      return (
        <>
          <Circle {...p} cx="12" cy="12" r="6" />
          <Circle cx="12" cy="12" r="2.2" fill={c} />
          <Path {...p} d="M12 3v3M12 18v3M3 12h3M18 12h3" />
        </>
      );
    case 'layers':
      return <Path {...p} d="m12 4 8.5 4.5L12 13 3.5 8.5zM3.5 12.5 12 17l8.5-4.5M3.5 16.2 12 20.7l8.5-4.5" />;
    case 'navigate':
      return <Path {...p} d="M20.5 3.5 3.5 10.8l7 2.7 2.7 7z" />;
    case 'briefcase':
      return (
        <>
          <Rect {...p} x="3.5" y="7.5" width="17" height="12" rx="2" />
          <Path {...p} d="M9 7.5V6a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 6v1.5M3.5 12.5h17" />
        </>
      );
    case 'shield':
      return <Path {...p} d="M12 3.5 19 6v5.5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6z" />;
    case 'shieldCheck':
      return (
        <>
          <Path {...p} d="M12 3.5 19 6v5.5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6z" />
          <Path {...p} d="m9 12 2.2 2.2L15.3 10" />
        </>
      );
    case 'speaker':
      return <Path {...p} d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" />;
    case 'speakerOff':
      return <Path {...p} d="M4 9.5h3.5L12 5.5v13l-4.5-4H4zM16 9.5l5 5M21 9.5l-5 5" />;
    case 'phone':
      return (
        <Path
          d="M6.6 3.5h2.6l1.4 4.3-2 1.4a11 11 0 0 0 6.2 6.2l1.4-2 4.3 1.4v2.6A2.1 2.1 0 0 1 18.4 20 15.4 15.4 0 0 1 4 5.6a2.1 2.1 0 0 1 2.6-2.1z"
          fill={c}
        />
      );
    case 'check':
      return <Path {...p} d="m5 12.5 4.5 4.5L19 7.5" />;
    case 'chatCheck':
      return (
        <>
          <Path {...p} d="M5 4.5h14a1.5 1.5 0 0 1 1.5 1.5v9.5A1.5 1.5 0 0 1 19 17h-8l-4.5 3.5V17H5a1.5 1.5 0 0 1-1.5-1.5V6A1.5 1.5 0 0 1 5 4.5z" />
          <Path {...p} d="m8.5 10.8 2.4 2.4 4.6-4.6" />
        </>
      );
    case 'arrowRight':
      return <Path {...p} d="M5 12h13.5M13 6.5l5.5 5.5-5.5 5.5" />;
    case 'close':
      return <Path {...p} d="m6 6 12 12M18 6 6 18" />;
    case 'route':
      return (
        <>
          <Circle {...p} cx="6" cy="18" r="2" />
          <Circle {...p} cx="18" cy="6" r="2" />
          <Path {...p} d="M8 18h7.5a3 3 0 0 0 0-6h-7a3 3 0 0 1 0-6H16" />
        </>
      );
    case 'clock':
      return (
        <>
          <Circle {...p} cx="12" cy="12" r="8.5" />
          <Path {...p} d="M12 7.5V12l3 2" />
        </>
      );
    case 'info':
      return (
        <>
          <Circle {...p} cx="12" cy="12" r="8.5" />
          <Path {...p} d="M12 11v5M12 8h.01" />
        </>
      );
    default:
      return null;
  }
}
