import React, { useCallback } from "react";
import { useTheme } from "@/contexts/ThemeContext";
import { BetOnTeam, BetOnTotal } from "@/schema/BetTypes";
import { StyleSheet, View, Text } from "react-native";
import Matchup from "./Matchup";
import { BaseballGame, getTodayDate } from "@/schema/BaseballGame";

export default function CompletedBet({ bet }: { bet: BetOnTeam | BetOnTotal }) {
  const { colors } = useTheme();

  const isTeamBet = (bet: BetOnTeam | BetOnTotal): boolean => {
    return !("total" in bet);
  };

  const getGame = useCallback((gameId: string): BaseballGame => {
    // TODO get game info
    const game: BaseballGame = {
      id: gameId,
      gameMetadata: {
        status: "final",
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
      gameRealTimeData: {
        homeScore: 5,
        awayScore: 4,
        inning: 9,
        inningHalf: "bottom",
        balls: 0,
        strikes: 2,
        outs: 3,
      },
    };
    return game;
  }, []);

  return (
    <View
      key={`team-${bet.gameId}`}
      style={[
        styles.betCard,
        {
          backgroundColor:
            bet.result?.outcome === "win"
              ? colors.cardBackgroundWin
              : colors.cardBackgroundLoss,
        },
      ]}
    >
      <View style={styles.betHeader}>
        <View
          style={[styles.pickBadge, { backgroundColor: colors.gameScheduled }]}
        >
          <Text style={styles.pickText}>
            {`${bet.pick.toUpperCase()}${isTeamBet(bet) ? " ML " : " "}(${bet.odds > 0 ? "+" : ""}${bet.odds})`}
          </Text>
        </View>
      </View>

      <Matchup game={getGame(bet.gameId)} />

      {/* <View style={styles.betDetails}>
          <Text style={[styles.betLabel, { color: colors.secondaryText }]}>
            Odds: {teamBet.odds > 0 ? "+" : ""} {teamBet.odds}
          </Text>
        </View> */}

      {/* <Text style={[styles.timeText, { color: colors.tertiaryText }]}>
        {bet.dateTime.toLocaleTimeString("en-US", {
          hour: "numeric",
          minute: "2-digit",
          hour12: true,
        })}
      </Text> */}
    </View>
  );
  //   return isTeamBet(bet) ? (
  //     <TeamBet teamBet={bet} />
  //   ) : (
  //     <TotalBet totalBet={bet as BetOnTotal} />
  //   );
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
    width: 400,
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
