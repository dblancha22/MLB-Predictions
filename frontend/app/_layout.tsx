import { NavigationHeader } from "@/components/NavigationHeader";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { Stack } from "expo-router";
import React from "react";

export default function RootLayout() {
  return (
    <ThemeProvider>
      <Stack
        screenOptions={{
          header: () => <NavigationHeader />,
        }}
      />
    </ThemeProvider>
  );
}
