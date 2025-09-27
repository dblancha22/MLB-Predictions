/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

const tintColorLight = '#0a7ea4';
const tintColorDark = '#fff';

export const Colors = {
  light: {
    text: '#11181C',
    background: '#fff',
    tint: tintColorLight,
    icon: '#687076',
    tabIconDefault: '#687076',
    tabIconSelected: tintColorLight,
    // Baseball game specific colors
    gameScheduled: '#95E1D3',
    gameLive: '#FF6B6B',
    gameFinal: '#4ECDC4',
    cardBackground: '#fff',
    cardBorder: '#e0e0e0',
    secondaryText: '#666',
    tertiaryText: '#888',
    dateSelectorBackground: '#f0f0f0',
    dateSelectorSelected: '#007AFF',
  },
  dark: {
    text: '#ECEDEE',
    background: '#151718',
    tint: tintColorDark,
    icon: '#9BA1A6',
    tabIconDefault: '#9BA1A6',
    tabIconSelected: tintColorDark,
    // Baseball game specific colors (adjusted for dark mode)
    gameScheduled: '#4A7C59',
    gameLive: '#FF4757',
    gameFinal: '#2ED573',
    cardBackground: '#2A2A2A',
    cardBorder: '#404040',
    secondaryText: '#B0B0B0',
    tertiaryText: '#888',
    dateSelectorBackground: '#404040',
    dateSelectorSelected: '#007AFF',
  },
};
