import { Stack } from "expo-router";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { NavigationHeader } from "@/components/NavigationHeader";

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
