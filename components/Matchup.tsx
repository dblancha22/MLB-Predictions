import { useTheme } from "@/contexts/ThemeContext";
import { BaseballGame } from "@/schema/BaseballGame";
import React from "react";
import { Text, View, StyleSheet } from "react-native";

interface Props {
  game: BaseballGame;
}

export default function Matchup({ game }: Props) {
  const { colors } = useTheme();

  return (
    <>
      <View style={styles.teamVsRow}>
        <View style={styles.teamContainer}>
          <Text style={[styles.teamName, { color: colors.text }]}>
            {game.gameMetadata.homeTeam}
          </Text>
          <Text style={styles.score}>
            {game.gameMetadata.status === "scheduled"
              ? ""
              : game.gameRealTimeData.homeScore || 0}
          </Text>
          {game.homeTeamData.homePitcher && (
            <Text style={[styles.pitcherName, { color: colors.tertiaryText }]}>
              {game.homeTeamData.homePitcher}
            </Text>
          )}
        </View>
        <Text style={[styles.vsText, { color: colors.secondaryText }]}>
          vs.
        </Text>
        <View style={styles.teamContainer}>
          <Text style={[styles.teamName, { color: colors.text }]}>
            {game.gameMetadata.awayTeam}
          </Text>
          <Text style={styles.score}>
            {game.gameMetadata.status === "scheduled"
              ? ""
              : game.gameRealTimeData.awayScore || 0}
          </Text>
          {game.awayTeamData.awayPitcher && (
            <Text style={[styles.pitcherName, { color: colors.tertiaryText }]}>
              {game.awayTeamData.awayPitcher}
            </Text>
          )}
        </View>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  teamVsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 4,
    marginBottom: 12,
  },
  teamContainer: {
    flex: 1,
    alignItems: "center",
  },
  teamName: {
    fontSize: 16,
    fontWeight: "600",
    marginBottom: 4,
  },
  score: {
    fontSize: 18,
    fontWeight: "bold",
    color: "#007AFF",
    textAlign: "center",
    marginBottom: 2,
  },
  pitcherName: {
    fontSize: 11,
    fontWeight: "400",
    textAlign: "center",
    fontStyle: "italic",
    marginTop: 2,
  },
  vsText: {
    fontSize: 14,
    fontWeight: "500",
    marginHorizontal: 16,
    fontStyle: "italic",
  },
});
