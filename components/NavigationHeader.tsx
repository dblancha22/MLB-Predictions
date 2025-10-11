import React from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Platform,
} from "react-native";
import { useRouter, usePathname } from "expo-router";
import { useTheme } from "@/contexts/ThemeContext";

interface NavigationItem {
  name: string;
  path: string;
  label: string;
}

const navigationItems: NavigationItem[] = [
  { name: "Scores", path: "/", label: "Scores" },
  { name: "BestBets", path: "/bestbets", label: "Best Bets" },
  { name: "History", path: "/history", label: "History" },
  { name: "Settings", path: "/settings", label: "Settings" },
];

export function NavigationHeader() {
  const router = useRouter();
  const pathname = usePathname();
  const { colors } = useTheme();

  const handleNavigation = (path: string) => {
    if (pathname !== path) {
      router.push(path as any);
    }
  };

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: colors.cardBackground,
          borderBottomColor: colors.cardBorder,
        },
      ]}
    >
      <Text style={[styles.title, { color: colors.text }]}>NoMoreTickets</Text>
      <View style={styles.navigationContainer}>
        {navigationItems.map((item) => (
          <TouchableOpacity
            key={item.name}
            style={[
              styles.navButton,
              {
                backgroundColor:
                  pathname === item.path
                    ? colors.dateSelectorSelected
                    : "transparent",
                borderBottomColor:
                  pathname === item.path
                    ? colors.dateSelectorSelected
                    : "transparent",
              },
            ]}
            onPress={() => handleNavigation(item.path)}
          >
            <Text
              style={[
                styles.navButtonText,
                {
                  color: pathname === item.path ? "#fff" : colors.text,
                },
              ]}
            >
              {item.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingTop: Platform.OS === "web" ? 20 : 50, // Less padding on web
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    shadowColor: "#000",
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
    elevation: 5,
  },
  title: {
    fontSize: 24,
    fontWeight: "bold",
    textAlign: "center",
    marginBottom: 16,
  },
  navigationContainer: {
    flexDirection: "row",
    justifyContent: "space-around",
  },
  navButton: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    borderBottomWidth: 2,
    minWidth: 80,
    alignItems: "center",
  },
  navButtonText: {
    fontSize: 14,
    fontWeight: "600",
  },
});
