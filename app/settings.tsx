import React from "react";
import { Text, StyleSheet, ScrollView } from "react-native";
import { SafeAreaView } from "react-native";
import { useTheme } from "@/contexts/ThemeContext";

export default function Settings() {
  const { colors } = useTheme();

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: colors.background }]}
    >
      <ScrollView style={styles.content}>
        <Text style={[styles.title, { color: colors.text }]}>Settings</Text>
        <Text style={[styles.subtitle, { color: colors.secondaryText }]}>
          Coming Soon - App settings and preferences will be displayed here.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    flex: 1,
    padding: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: "bold",
    marginBottom: 16,
    textAlign: "center",
  },
  subtitle: {
    fontSize: 16,
    textAlign: "center",
    fontStyle: "italic",
  },
});
