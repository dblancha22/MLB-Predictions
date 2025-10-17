import React, { useCallback } from "react";

import { useTheme } from "@/contexts/ThemeContext";
import { BaseballGame, getTodayDate } from "@/schema/BaseballGame";
import { BetOnTeam } from "@/schema/BetTypes";
import { StyleSheet, Text, View } from "react-native";
import Matchup from "./Matchup";

interface Props {
  teamBet: BetOnTeam;
}

export default function TeamBet({ teamBet }: Props) {
  const { colors } = useTheme();

  const getGame = useCallback((gameId: string): BaseballGame => {
    // TODO get game info
    const game: BaseballGame = {
      id: gameId,
      gameMetadata: {
        status: "scheduled",
        dateTime: getTodayDate(19, 5),
        venue: "Yankee Stadium",
        homeTeam: "Yankees",
        awayTeam: "Red Sox",
        odds: {
          spread: { home: -1.5, away: 1.5 },
          moneyline: { home: -120, away: +100 },
        },
      },
      homeTeamData: {
        homeTeam: "Yankees",
        homePitcher: "Gerrit Cole",
      },
      awayTeamData: {
        awayTeam: "Red Sox",
        awayPitcher: "Chris Sale",
      },
      gameRealTimeData: {},
    };
    return game;
  }, []);

  return (
    <View
      key={`team-${teamBet.gameId}`}
      style={[styles.betCard, { backgroundColor: colors.cardBackground }]}
    >
      <View style={styles.betHeader}>
        <View
          style={[styles.pickBadge, { backgroundColor: colors.gameScheduled }]}
        >
          <Text style={styles.pickText}>
            {`${teamBet.pick.toUpperCase()} ML (${teamBet.odds > 0 ? "+" : ""}${teamBet.odds})`}
          </Text>
        </View>
      </View>

      <Matchup game={getGame(teamBet.gameId)} />

      {/* <View style={styles.betDetails}>
        <Text style={[styles.betLabel, { color: colors.secondaryText }]}>
          Odds: {teamBet.odds > 0 ? "+" : ""} {teamBet.odds}
        </Text>
      </View> */}

      <Text style={[styles.timeText, { color: colors.tertiaryText }]}>
        {teamBet.dateTime.toLocaleTimeString("en-US", {
          hour: "numeric",
          minute: "2-digit",
          hour12: true,
        })}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  betCard: {
    borderRadius: 12,
    padding: 16,
    shadowColor: "#000",
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
    elevation: 5,
    width: "25%",
    alignItems: "center",
  },
  betHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  pickBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
    flexDirection: "row",
    alignItems: "center",
  },
  pickText: {
    fontSize: 14,
    fontWeight: "bold",
    color: "#fff",
    alignContent: "center",
  },
  betDetails: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  betLabel: {
    fontSize: 12,
    fontWeight: "500",
  },
  timeText: {
    fontSize: 14,
    fontWeight: "500",
    marginBottom: 4,
  },
});
