import CompletedBet from "@/components/CompletedBet";
import { useTheme } from "@/contexts/ThemeContext";
import {
  BetOnTeam,
  BetOnTotal,
  mockBetOnTeamData,
  mockBetOnTotalData,
} from "@/schema/BetTypes";
import React, { useState } from "react";
import {
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";

export default function History() {
  const { colors } = useTheme();
  const [selectedTab, setSelectedTab] = useState<"team" | "total">("team");
  const [selectedDate, setSelectedDate] = useState<string>("all");

  const getOutcomeColor = (outcome?: "win" | "loss") => {
    switch (outcome) {
      case "win":
        return "#4CAF50";
      case "loss":
        return "#F44336";
      default:
        return colors.secondaryText;
    }
  };

  const getOutcomeIcon = (outcome?: "win" | "loss") => {
    switch (outcome) {
      case "win":
        return "✓";
      case "loss":
        return "✗";
      default:
        return "?";
    }
  };

  // Get unique dates from historical data
  const getAvailableDates = () => {
    const allBets = [...mockBetOnTeamData, ...mockBetOnTotalData];
    const dates = allBets.map(
      (bet) => bet.dateTime.toISOString().split("T")[0],
    );
    const uniqueDates = [...new Set(dates)].sort(
      (a, b) => new Date(b).getTime() - new Date(a).getTime(),
    );
    return uniqueDates;
  };

  // Filter bets by selected date
  const filterBetsByDate = (bets: (BetOnTeam | BetOnTotal)[]) => {
    if (selectedDate === "all") {
      return bets;
    }
    return bets.filter((bet) => {
      const betDate = bet.dateTime.toISOString().split("T")[0];
      return betDate === selectedDate;
    });
  };

  // Format date for display
  const getDisplayDate = (dateString: string) => {
    if (dateString === "all") return "All Dates";
    const date = new Date(dateString);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    const dayBefore = new Date(today);
    dayBefore.setDate(today.getDate() - 2);

    if (dateString === today.toISOString().split("T")[0]) {
      return "Today";
    } else if (dateString === yesterday.toISOString().split("T")[0]) {
      return "Yesterday";
    } else if (dateString === dayBefore.toISOString().split("T")[0]) {
      return "Day Before";
    } else {
      return date.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
    }
  };

  const calculateStats = (bets: (BetOnTeam | BetOnTotal)[]) => {
    const completed = bets.filter((bet) => bet.result !== undefined);
    const wins =
      completed.filter((bet) => bet.result?.outcome === "win")?.length ?? 0;
    const losses =
      completed.filter((bet) => bet.result?.outcome === "loss")?.length ?? 0;
    const winRate = completed.length > 0 ? (wins / completed.length) * 100 : 0;

    return { wins, losses, total: completed.length ?? 0, winRate };
  };

  // Get filtered bets based on selected date
  const filteredTeamBets = filterBetsByDate(mockBetOnTeamData) as BetOnTeam[];
  const filteredTotalBets = filterBetsByDate(
    mockBetOnTotalData,
  ) as BetOnTotal[];
  const allFilteredBets = [...filteredTeamBets, ...filteredTotalBets];

  // Calculate stats for filtered data
  const teamStats = calculateStats(filteredTeamBets);
  const totalStats = calculateStats(filteredTotalBets);
  const overallStats = calculateStats(allFilteredBets);

  const formatDate = (date: Date) => {
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  };

  const renderTeamBet = (bet: BetOnTeam) => (
    <View
      key={bet.gameId}
      style={[styles.betCard, { backgroundColor: colors.cardBackground }]}
    >
      <View style={styles.betHeader}>
        <View style={styles.betInfo}>
          {/* <Text style={[styles.betType, { color: colors.text }]}>{bet.type.toUpperCase()}</Text> */}
          <Text style={[styles.betDate, { color: colors.tertiaryText }]}>
            {formatDate(bet.dateTime)}
          </Text>
        </View>
        <View
          style={[
            styles.outcomeBadge,
            { backgroundColor: getOutcomeColor(bet.result?.outcome) },
          ]}
        >
          <Text style={styles.outcomeText}>
            {getOutcomeIcon(bet.result?.outcome)}{" "}
            {bet.result?.outcome.toUpperCase()}
          </Text>
        </View>
      </View>

      <View style={styles.betMatchup}>
        <Text style={[styles.teamName, { color: colors.text }]}>
          {bet.homeTeam}
        </Text>
        <Text style={[styles.vsText, { color: colors.secondaryText }]}>vs</Text>
        <Text style={[styles.teamName, { color: colors.text }]}>
          {bet.awayTeam}
        </Text>
      </View>

      <View style={styles.betDetails}>
        <Text style={[styles.betLabel, { color: colors.secondaryText }]}>
          Pick: {bet.pick}
        </Text>
        <Text style={[styles.betLabel, { color: colors.secondaryText }]}>
          Odds: {bet.odds}
        </Text>
      </View>

      {bet.result?.outcome && bet.result.finalScore && (
        <View style={styles.resultDetails}>
          <Text style={[styles.resultText, { color: colors.secondaryText }]}>
            Final: {bet.homeTeam} {bet.result.finalScore.home} -{" "}
            {bet.result.finalScore.away} {bet.awayTeam}
          </Text>
        </View>
      )}
    </View>
  );

  const renderTotalBet = (bet: BetOnTotal) => (
    <View
      key={bet.gameId}
      style={[styles.betCard, { backgroundColor: colors.cardBackground }]}
    >
      <View style={styles.betHeader}>
        <View style={styles.betInfo}>
          <Text style={[styles.betType, { color: colors.text }]}>TOTAL</Text>
          <Text style={[styles.betDate, { color: colors.tertiaryText }]}>
            {formatDate(bet.dateTime)}
          </Text>
        </View>
        <View
          style={[
            styles.outcomeBadge,
            { backgroundColor: getOutcomeColor(bet.result?.outcome) },
          ]}
        >
          <Text style={styles.outcomeText}>
            {getOutcomeIcon(bet.result?.outcome)}{" "}
            {bet.result?.outcome.toUpperCase()}
          </Text>
        </View>
      </View>

      <View style={styles.betDetails}>
        <Text style={[styles.betLabel, { color: colors.secondaryText }]}>
          Pick: {bet.pick} {bet.total}
        </Text>
        <Text style={[styles.betLabel, { color: colors.secondaryText }]}>
          Odds: {bet.odds}
        </Text>
      </View>

      {bet.result && bet.result.finalScore && (
        <View style={styles.resultDetails}>
          <Text style={[styles.resultText, { color: colors.secondaryText }]}>
            Final Score:{" "}
            {bet.result.finalScore.home + bet.result.finalScore.away} runs
          </Text>
          <Text style={[styles.resultText, { color: colors.secondaryText }]}>
            Total: {bet.result.finalScore.home + bet.result.finalScore.away}
          </Text>
        </View>
      )}
    </View>
  );

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: colors.background }]}
    >
      <View style={styles.content}>
        <Text style={[styles.title, { color: colors.text }]}>
          Previous Results
        </Text>

        {/* Overall Stats */}
        <View
          style={[
            styles.statsContainer,
            { backgroundColor: colors.cardBackground },
          ]}
        >
          <Text style={[styles.statsTitle, { color: colors.text }]}>
            Overall Record
          </Text>
          <View style={styles.statsRow}>
            {/* TODO: Add tracker for units won i.e. 4.3x or 430% 
              Do we need to track wins/losses?
            */}
            <View style={styles.statItem}>
              <Text style={[styles.statNumber, { color: "#4CAF50" }]}>
                {overallStats.wins}
              </Text>
              <Text style={[styles.statLabel, { color: colors.secondaryText }]}>
                Wins
              </Text>
            </View>
            <View style={styles.statItem}>
              <Text style={[styles.statNumber, { color: "#F44336" }]}>
                {overallStats.losses}
              </Text>
              <Text style={[styles.statLabel, { color: colors.secondaryText }]}>
                Losses
              </Text>
            </View>
            <View style={styles.statItem}>
              <Text style={[styles.statNumber, { color: colors.text }]}>
                {overallStats.winRate.toFixed(1)}%
              </Text>
              <Text style={[styles.statLabel, { color: colors.secondaryText }]}>
                Win Rate
              </Text>
            </View>
          </View>
        </View>

        {/* Date Selector */}
        <View
          style={[
            styles.dateSelectorContainer,
            { backgroundColor: colors.cardBackground },
          ]}
        >
          <Text style={[styles.dateSelectorTitle, { color: colors.text }]}>
            Select Date
          </Text>
          <TouchableOpacity
            style={[
              styles.dropdownButton,
              {
                backgroundColor: colors.dateSelectorBackground,
                borderColor: colors.cardBorder,
              },
            ]}
            onPress={() => {
              // For now, cycle through dates on tap - in a real app this would open a modal or picker
              const availableDates = ["all", ...getAvailableDates()];
              const currentIndex = availableDates.indexOf(selectedDate);
              const nextIndex = (currentIndex + 1) % availableDates.length;
              setSelectedDate(availableDates[nextIndex]);
            }}
          >
            <Text style={[styles.dropdownButtonText, { color: colors.text }]}>
              {getDisplayDate(selectedDate)}
            </Text>
            <Text
              style={[styles.dropdownArrow, { color: colors.secondaryText }]}
            >
              ▼
            </Text>
          </TouchableOpacity>
        </View>

        {/* Tab Selector */}
        <View style={styles.tabContainer}>
          <TouchableOpacity
            style={[
              styles.tab,
              {
                backgroundColor:
                  selectedTab === "team"
                    ? colors.dateSelectorSelected
                    : colors.dateSelectorBackground,
              },
            ]}
            onPress={() => setSelectedTab("team")}
          >
            <Text
              style={[
                styles.tabText,
                { color: selectedTab === "team" ? "#fff" : colors.text },
              ]}
            >
              Team Bets ({teamStats.wins}-{teamStats.losses})
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.tab,
              {
                backgroundColor:
                  selectedTab === "total"
                    ? colors.dateSelectorSelected
                    : colors.dateSelectorBackground,
              },
            ]}
            onPress={() => setSelectedTab("total")}
          >
            <Text
              style={[
                styles.tabText,
                { color: selectedTab === "total" ? "#fff" : colors.text },
              ]}
            >
              Total Bets ({totalStats.wins}-{totalStats.losses})
            </Text>
          </TouchableOpacity>
        </View>

        {/* Results List */}
        {/* <View style={styles.betsContainer}> */}
        <ScrollView style={styles.resultsList}>
          <View style={styles.betsContainer}>
            {selectedTab === "team"
              ? filteredTeamBets.map(renderTeamBet)
              : filteredTotalBets.map(renderTotalBet)}
            {filteredTeamBets.map((bet, index) => (
              <CompletedBet key={`spacer-${index}`} bet={bet} />
            ))}
            {filteredTotalBets.map((bet, index) => (
              <CompletedBet key={`spacer-${index}`} bet={bet} />
            ))}
          </View>
        </ScrollView>
        {/* </View> */}
      </View>
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
  statsContainer: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: "#000",
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
    elevation: 5,
  },
  statsTitle: {
    fontSize: 16,
    fontWeight: "bold",
    marginBottom: 12,
    textAlign: "center",
  },
  statsRow: {
    flexDirection: "row",
    justifyContent: "space-around",
  },
  statItem: {
    alignItems: "center",
  },
  statNumber: {
    fontSize: 24,
    fontWeight: "bold",
  },
  statLabel: {
    fontSize: 12,
    marginTop: 4,
  },
  dateSelectorContainer: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: "#000",
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
    elevation: 5,
  },
  dateSelectorTitle: {
    fontSize: 16,
    fontWeight: "bold",
    marginBottom: 12,
  },
  dropdownButton: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  dropdownButtonText: {
    fontSize: 16,
    fontWeight: "500",
  },
  dropdownArrow: {
    fontSize: 12,
    marginLeft: 8,
  },
  tabContainer: {
    flexDirection: "row",
    marginBottom: 16,
    borderRadius: 8,
    overflow: "hidden",
  },
  tab: {
    flex: 1,
    paddingVertical: 12,
    paddingHorizontal: 16,
    alignItems: "center",
  },
  tabText: {
    fontSize: 14,
    fontWeight: "500",
  },
  resultsList: {
    flex: 1,
  },
  betsContainer: {
    gap: 12,
    flexDirection: "row", // lays them out horizontally
    flexWrap: "wrap", // allows them to wrap to the next line
    justifyContent: "flex-start", // optional, controls alignment
  },
  betCard: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: "#000",
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
    elevation: 5,
  },
  betHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  betInfo: {
    flex: 1,
  },
  betType: {
    fontSize: 14,
    fontWeight: "600",
  },
  betDate: {
    fontSize: 12,
    marginTop: 2,
  },
  outcomeBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  outcomeText: {
    fontSize: 12,
    fontWeight: "bold",
    color: "#fff",
  },
  betMatchup: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  teamName: {
    fontSize: 16,
    fontWeight: "600",
  },
  vsText: {
    fontSize: 14,
    fontWeight: "500",
    fontStyle: "italic",
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
  resultDetails: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: "#E0E0E0",
  },
  resultText: {
    fontSize: 12,
    marginVertical: 2,
  },
});
