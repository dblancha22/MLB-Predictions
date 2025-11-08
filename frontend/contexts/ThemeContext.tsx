import React, { createContext, useContext, ReactNode } from "react";
import { useThemeColor } from "@/hooks/useThemeColor";

interface ThemeColors {
  // Base colors
  text: string;
  background: string;
  tint: string;
  icon: string;
  tabIconDefault: string;
  tabIconSelected: string;

  // Baseball game specific colors
  gameScheduled: string;
  gameLive: string;
  gameFinal: string;

  // UI colors
  cardBackground: string;
  cardBorder: string;
  cardBackgroundWin: string;
  cardBackgroundLoss: string;
  secondaryText: string;
  tertiaryText: string;

  // Date selector colors
  dateSelectorBackground: string;
  dateSelectorSelected: string;
}

interface ThemeContextType {
  colors: ThemeColors;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  // Get all theme colors in one place
  const colors: ThemeColors = {
    // Base colors
    text: useThemeColor({}, "text"),
    background: useThemeColor({}, "background"),
    tint: useThemeColor({}, "tint"),
    icon: useThemeColor({}, "icon"),
    tabIconDefault: useThemeColor({}, "tabIconDefault"),
    tabIconSelected: useThemeColor({}, "tabIconSelected"),

    // Baseball game specific colors
    gameScheduled: useThemeColor({}, "gameScheduled"),
    gameLive: useThemeColor({}, "gameLive"),
    gameFinal: useThemeColor({}, "gameFinal"),

    // UI colors
    cardBackground: useThemeColor({}, "cardBackground"),
    cardBorder: useThemeColor({}, "cardBorder"),
    cardBackgroundWin: useThemeColor({}, "cardBackgroundWin"),
    cardBackgroundLoss: useThemeColor({}, "cardBackgroundLoss"),
    secondaryText: useThemeColor({}, "secondaryText"),
    tertiaryText: useThemeColor({}, "tertiaryText"),

    // Date selector colors
    dateSelectorBackground: useThemeColor({}, "dateSelectorBackground"),
    dateSelectorSelected: useThemeColor({}, "dateSelectorSelected"),
  };

  return (
    <ThemeContext.Provider value={{ colors }}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextType {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
