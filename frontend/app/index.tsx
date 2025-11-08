import Matchup from "@/components/Matchup";
import { useTheme } from "@/contexts/ThemeContext";
import { mockGamesData, RealTimeGameData } from "@/schema/BaseballGame";
import React, { useState } from "react";
import {
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from "react-native";

export default function Index() {
  const [selectedDate, setSelectedDate] = useState(
    new Date().toISOString().split("T")[0],
  );

  // Get all theme colors from context
  const { colors } = useTheme();

  const getDateString = (date: Date) => {
    return date.toISOString().split("T")[0];
  };

  const getDisplayDate = (dateString: string) => {
    const date = new Date(dateString);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);

    if (dateString === getDateString(today)) {
      return "Today";
    } else if (dateString === getDateString(tomorrow)) {
      return "Tomorrow";
    } else if (dateString === getDateString(yesterday)) {
      return "Yesterday";
    } else {
      return date.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
    }
  };

  const getAvailableDates = () => {
    const dates = [];
    const today = new Date();

    // Generate dates for the past 7 days and next 7 days
    for (let i = -7; i <= 7; i++) {
      const date = new Date(today);
      date.setDate(today.getDate() + i);
      dates.push(getDateString(date));
    }

    return dates;
  };

  const currentGames = mockGamesData[selectedDate] || [];

  const getStatusColor = (status: string) => {
    switch (status) {
      case "live":
        return colors.gameLive;
      case "final":
        return colors.gameFinal;
      case "scheduled":
        return colors.gameScheduled;
      default:
        return colors.gameScheduled;
    }
  };

  const formatGameTime = (
    dateTime?: Date,
    status?: string,
    gameRealTimeData?: RealTimeGameData,
  ) => {
    if (status === "live" && gameRealTimeData?.inning) {
      const inningHalf =
        gameRealTimeData.inningHalf === "top" ? "Top" : "Bottom";
      return `${inningHalf} ${gameRealTimeData.inning}${gameRealTimeData.inning === 1 ? "st" : gameRealTimeData.inning === 2 ? "nd" : gameRealTimeData.inning === 3 ? "rd" : "th"}`;
    }
    if (status === "final") return "Final";
    return dateTime?.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      {/* Date Selector */}
      <View
        style={[
          styles.dateSelectorContainer,
          {
            backgroundColor: colors.cardBackground,
            borderBottomColor: colors.cardBorder,
          },
        ]}
      >
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.dateScrollView}
          contentContainerStyle={styles.dateScrollContent}
        >
          {getAvailableDates().map((dateString) => (
            <TouchableOpacity
              key={dateString}
              style={[
                styles.dateButton,
                {
                  backgroundColor:
                    selectedDate === dateString
                      ? colors.dateSelectorSelected
                      : colors.dateSelectorBackground,
                },
              ]}
              onPress={() => setSelectedDate(dateString)}
            >
              <Text
                style={[
                  styles.dateButtonText,
                  { color: selectedDate === dateString ? "#fff" : colors.text },
                ]}
              >
                {getDisplayDate(dateString)}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Games Table */}
      <View style={styles.tableContainer}>
        <Text style={[styles.tableTitle, { color: colors.text }]}>
          Baseball Games - {getDisplayDate(selectedDate)}
        </Text>

        {currentGames.length > 0 ? (
          <ScrollView style={styles.gamesScrollView}>
            {currentGames.map((game) => (
              <View
                key={game.id}
                style={[
                  styles.gameRow,
                  { backgroundColor: colors.cardBackground },
                ]}
              >
                <Matchup game={game} />

                <View style={styles.gameInfo}>
                  <Text
                    style={[styles.timeText, { color: colors.secondaryText }]}
                  >
                    {formatGameTime(
                      game.gameMetadata.dateTime,
                      game.gameMetadata.status,
                      game.gameRealTimeData,
                    )}
                  </Text>
                  <Text
                    style={[styles.venueText, { color: colors.tertiaryText }]}
                  >
                    {game.gameMetadata.venue}
                  </Text>

                  {/* Real-time Game Data for Live Games */}
                  {game.gameMetadata.status === "live" &&
                    game.gameRealTimeData && (
                      <View style={styles.realtimeContainer}>
                        {game.gameRealTimeData.balls !== undefined &&
                          game.gameRealTimeData.strikes !== undefined && (
                            <Text
                              style={[
                                styles.realtimeText,
                                { color: colors.secondaryText },
                              ]}
                            >
                              Count: {game.gameRealTimeData.balls}-
                              {game.gameRealTimeData.strikes}
                            </Text>
                          )}
                        {game.gameRealTimeData.outs !== undefined && (
                          <Text
                            style={[
                              styles.realtimeText,
                              { color: colors.secondaryText },
                            ]}
                          >
                            Outs: {game.gameRealTimeData.outs}
                          </Text>
                        )}
                      </View>
                    )}

                  {/* Odds Section */}
                  {game.picks && game.picks.length > 0 ? (
                    <View style={styles.betSection}>
                      <View style={styles.betsContainer}>
                        {game.picks.map((bet, index) => (
                          <View key={index} style={styles.betHeader}>
                            <View
                              style={[
                                styles.pickBadge,
                                { backgroundColor: colors.gameScheduled },
                              ]}
                            >
                              <Text style={styles.pickText}>
                                {`${bet.pick.toUpperCase()} ML (${bet.odds > 0 ? "+" : ""}${bet.odds})`}
                              </Text>
                            </View>
                          </View>
                        ))}
                      </View>
                    </View>
                  ) : (
                    <View style={styles.noBetsContainer}>
                      <Text
                        style={[
                          styles.noBetsText,
                          { color: colors.secondaryText },
                        ]}
                      >
                        {game.gameMetadata.dateTime &&
                        game.gameMetadata.dateTime > new Date()
                          ? "This game hasn't been predicted yet, check back later!"
                          : "Stay away! No bets for this game."}
                      </Text>
                    </View>
                  )}
                </View>
              </View>
            ))}
          </ScrollView>
        ) : (
          <View style={styles.noGamesContainer}>
            <Text style={[styles.noGamesText, { color: colors.secondaryText }]}>
              No games scheduled for this date
            </Text>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
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
  betSection: {
    padding: 16,
    marginBottom: 8,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: "bold",
    marginBottom: 12,
  },
  betsContainer: {
    gap: 12,
    flexDirection: "row", // lays them out horizontally
    flexWrap: "wrap", // allows them to wrap to the next line
    justifyContent: "flex-start", // optional, controls alignment
  },
  noBetsContainer: {
    padding: 20,
    alignItems: "center",
  },
  noBetsText: {
    fontSize: 14,
    fontStyle: "italic",
  },
  container: {
    flex: 1,
  },
  dateSelectorContainer: {
    paddingVertical: 15,
    borderBottomWidth: 1,
  },
  dateScrollView: {
    flexGrow: 0,
  },
  dateScrollContent: {
    paddingHorizontal: 10,
  },
  dateButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    marginHorizontal: 4,
    borderRadius: 20,
    minWidth: 80,
    alignItems: "center",
  },
  dateButtonText: {
    fontSize: 14,
    fontWeight: "500",
  },
  tableContainer: {
    flex: 1,
    padding: 16,
  },
  tableTitle: {
    fontSize: 20,
    fontWeight: "bold",
    marginBottom: 16,
  },
  gamesScrollView: {
    flex: 1,
  },
  gameRow: {
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
    width: "40%",
  },
  teamInfo: {
    marginBottom: 12,
  },
  teamVsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
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
  gameInfo: {
    alignItems: "center",
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    marginBottom: 8,
  },
  statusText: {
    fontSize: 12,
    fontWeight: "bold",
    color: "#fff",
  },
  timeText: {
    fontSize: 14,
    fontWeight: "500",
    marginBottom: 4,
  },
  venueText: {
    fontSize: 12,
    marginBottom: 8,
  },
  realtimeContainer: {
    marginTop: 4,
    marginBottom: 8,
    alignItems: "center",
  },
  realtimeText: {
    fontSize: 11,
    fontWeight: "500",
    marginVertical: 1,
  },
  oddsContainer: {
    marginTop: 8,
    alignItems: "center",
  },
  oddsRow: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 2,
  },
  oddsLabel: {
    fontSize: 11,
    fontWeight: "500",
    marginRight: 8,
    minWidth: 60,
  },
  oddsValues: {
    flexDirection: "row",
    alignItems: "center",
  },
  oddsValue: {
    fontSize: 12,
    fontWeight: "600",
    minWidth: 35,
    textAlign: "center",
  },
  oddsSeparator: {
    fontSize: 12,
    marginHorizontal: 8,
  },
  noGamesContainer: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
  },
  noGamesText: {
    fontSize: 16,
    fontStyle: "italic",
  },
});
