import { useState } from "react";
import { 
  Text, 
  TextInput, 
  StyleSheet, 
  View, 
  ScrollView, 
  TouchableOpacity,
  Dimensions 
} from "react-native";
import { mockGamesData } from "@/schema/BaseballGame";
import { mockBetOnTeamData, mockBetOnTotalData, BetOnTeam, BetOnTotal } from "@/schema/BetTypes";
import { useTheme } from "@/contexts/ThemeContext";

export default function BestBets() {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const { colors } = useTheme();

  const getDateString = (date: Date) => {
    return date.toISOString().split('T')[0];
  };

  const getDisplayDate = (dateString: string) => {
    const date = new Date(dateString);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);
    
    if (dateString === getDateString(today)) {
      return 'Today';
    } else if (dateString === getDateString(tomorrow)) {
      return 'Tomorrow';
    } else if (dateString === getDateString(yesterday)) {
      return 'Yesterday';
    } else {
      return date.toLocaleDateString('en-US', { 
        weekday: 'short', 
        month: 'short', 
        day: 'numeric' 
      });
    }
  };
  
  const getAvailableDates = () => {
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(today.getDate() + 1);
    return [getDateString(today), getDateString(tomorrow)];
  };
  
  const currentGames = mockGamesData[selectedDate] || [];
  
  // Filter bets by selected date
  const getBetsForDate = (bets: (BetOnTeam | BetOnTotal)[]) => {
    return bets.filter(bet => {
      const betDate = bet.dateTime.toISOString().split('T')[0];
      return betDate === selectedDate;
    });
  };
  
  const currentTeamBets = getBetsForDate(mockBetOnTeamData) as BetOnTeam[];
  const currentTotalBets = getBetsForDate(mockBetOnTotalData) as BetOnTotal[];
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'live': return colors.gameLive;
      case 'final': return colors.gameFinal;
      case 'scheduled': return colors.gameScheduled;
      default: return colors.gameScheduled;
    }
  };

  const formatGameTime = (dateTime: Date, status: string, gameRealTimeData?: any) => {
    if (status === 'live' && gameRealTimeData?.inning) {
      const inningHalf = gameRealTimeData.inningHalf === 'top' ? 'Top' : 'Bottom';
      return `${inningHalf} ${gameRealTimeData.inning}${gameRealTimeData.inning === 1 ? 'st' : gameRealTimeData.inning === 2 ? 'nd' : gameRealTimeData.inning === 3 ? 'rd' : 'th'}`;
    }
    if (status === 'final') return 'Final';
    return dateTime.toLocaleTimeString('en-US', { 
      hour: 'numeric', 
      minute: '2-digit',
      hour12: true 
    });
  };

  const formatOdds = (odds: { plusMinus: '+' | '-'; value: number }) => {
    return `${odds.plusMinus}${odds.value}`;
  };

  const getPickColor = (pick: string) => {
    return pick === 'favorite' || pick === 'over' ? colors.gameLive : colors.gameScheduled;
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <View style={[styles.dateSelectorContainer, { backgroundColor: colors.cardBackground, borderBottomColor: colors.cardBorder }]}>
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
                { backgroundColor: selectedDate === dateString ? colors.dateSelectorSelected : colors.dateSelectorBackground }
              ]}
              onPress={() => setSelectedDate(dateString)}
            >
              <Text style={[
                styles.dateButtonText,
                { color: selectedDate === dateString ? '#fff' : colors.text }
              ]}>
                {getDisplayDate(dateString)}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      <ScrollView style={styles.mainScrollView}>
        {/* Team Bets Section */}
        <View style={styles.betSection}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>Team Bets - {getDisplayDate(selectedDate)}</Text>
          {currentTeamBets.length > 0 ? (
            <View style={styles.betsContainer}>
              {currentTeamBets.map((bet, index) => (
                <View key={`team-${bet.gameId}-${index}`} style={[styles.betCard, { backgroundColor: colors.cardBackground }]}>
                  <View style={styles.betHeader}>
                    <Text style={[styles.betType, { color: colors.text }]}>{bet.type.toUpperCase()}</Text>
                    <View style={[styles.pickBadge, { backgroundColor: getPickColor(bet.pick) }]}>
                      <Text style={styles.pickText}>{bet.pick.toUpperCase()}</Text>
                    </View>
                  </View>
                  
                  <View style={styles.betMatchup}>
                    <Text style={[styles.teamName, { color: colors.text }]}>{bet.favoriteTeam}</Text>
                    <Text style={[styles.vsText, { color: colors.secondaryText }]}>vs</Text>
                    <Text style={[styles.teamName, { color: colors.text }]}>{bet.underdogTeam}</Text>
                  </View>
                  
                  <View style={styles.betDetails}>
                    <Text style={[styles.betLabel, { color: colors.secondaryText }]}>Spread: {bet.spread}</Text>
                    <Text style={[styles.betLabel, { color: colors.secondaryText }]}>Odds: {formatOdds(bet.odds)}</Text>
                  </View>
                  
                  <View style={styles.betStats}>
                    <Text style={[styles.statText, { color: colors.tertiaryText }]}>
                      Projected Win%: {bet.projectedWinPercent.toFixed(1)}%
                    </Text>
                    <Text style={[styles.statText, { color: colors.tertiaryText }]}>
                      Score Diff: {bet.projectedScoreDiff.toFixed(1)}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <View style={styles.noBetsContainer}>
              <Text style={[styles.noBetsText, { color: colors.secondaryText }]}>No team bets for this date</Text>
            </View>
          )}
        </View>

        {/* Total Bets Section */}
        <View style={styles.betSection}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>Total Bets - {getDisplayDate(selectedDate)}</Text>
          {currentTotalBets.length > 0 ? (
            <View style={styles.betsContainer}>
              {currentTotalBets.map((bet, index) => (
                <View key={`total-${bet.gameId}-${index}`} style={[styles.betCard, { backgroundColor: colors.cardBackground }]}>
                  <View style={styles.betHeader}>
                    <Text style={[styles.betType, { color: colors.text }]}>TOTAL</Text>
                    <View style={[styles.pickBadge, { backgroundColor: getPickColor(bet.pick) }]}>
                      <Text style={styles.pickText}>{bet.pick.toUpperCase()}</Text>
                    </View>
                  </View>
                  
                  <View style={styles.betDetails}>
                    <Text style={[styles.betLabel, { color: colors.secondaryText }]}>Total: {bet.total}</Text>
                    <Text style={[styles.betLabel, { color: colors.secondaryText }]}>Odds: {formatOdds(bet.odds)}</Text>
                  </View>
                  
                  <Text style={[styles.timeText, { color: colors.tertiaryText }]}>
                    {bet.dateTime.toLocaleTimeString('en-US', { 
                      hour: 'numeric', 
                      minute: '2-digit',
                      hour12: true 
                    })}
                  </Text>
                </View>
              ))}
            </View>
          ) : (
            <View style={styles.noBetsContainer}>
              <Text style={[styles.noBetsText, { color: colors.secondaryText }]}>No total bets for this date</Text>
            </View>
          )}
        </View>

        {/* Games Section */}
        <View style={styles.betSection}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>Games - {getDisplayDate(selectedDate)}</Text>
          {currentGames.length > 0 ? (
            <View style={styles.gamesContainer}>
              {currentGames.map((game) => (
                <View key={game.id} style={[styles.gameRow, { backgroundColor: colors.cardBackground }]}>
                  <View style={styles.teamInfo}>
                    <View style={styles.teamVsRow}>
                      <View style={styles.teamContainer}>
                        <Text style={[styles.teamName, { color: colors.text }]}>{game.gameMetadata.homeTeam}</Text>
                        <Text style={styles.score}>
                          {game.gameMetadata.status === 'scheduled' ? '' : game.gameRealTimeData.homeScore || 0}
                        </Text>
                        {game.homeTeamData.homePitcher && (
                          <Text style={[styles.pitcherName, { color: colors.tertiaryText }]}>
                            {game.homeTeamData.homePitcher}
                          </Text>
                        )}
                      </View>
                      <Text style={[styles.vsText, { color: colors.secondaryText }]}>vs.</Text>
                      <View style={styles.teamContainer}>
                        <Text style={[styles.teamName, { color: colors.text }]}>{game.gameMetadata.awayTeam}</Text>
                        <Text style={styles.score}>
                          {game.gameMetadata.status === 'scheduled' ? '' : game.gameRealTimeData.awayScore || 0}
                        </Text>
                        {game.awayTeamData.awayPitcher && (
                          <Text style={[styles.pitcherName, { color: colors.tertiaryText }]}>
                            {game.awayTeamData.awayPitcher}
                          </Text>
                        )}
                      </View>
                    </View>
                  </View>
                  
                  <View style={styles.gameInfo}>
                    <View style={[styles.statusBadge, { backgroundColor: getStatusColor(game.gameMetadata.status) }]}>
                      <Text style={styles.statusText}>{game.gameMetadata.status.toUpperCase()}</Text>
                    </View>
                    <Text style={[styles.timeText, { color: colors.secondaryText }]}>
                      {formatGameTime(game.gameMetadata.dateTime, game.gameMetadata.status, game.gameRealTimeData)}
                    </Text>
                    <Text style={[styles.venueText, { color: colors.tertiaryText }]}>{game.gameMetadata.venue}</Text>
                    {game.gameMetadata.status === 'live' && game.gameRealTimeData && (
                      <View style={styles.realtimeContainer}>
                        {game.gameRealTimeData.balls !== undefined && game.gameRealTimeData.strikes !== undefined && (
                          <Text style={[styles.realtimeText, { color: colors.secondaryText }]}>Count: {game.gameRealTimeData.balls}-{game.gameRealTimeData.strikes}</Text>
                        )}
                        {game.gameRealTimeData.outs !== undefined && (
                          <Text style={[styles.realtimeText, { color: colors.secondaryText }]}>Outs: {game.gameRealTimeData.outs}</Text>
                        )}
                      </View>
                    )}
                    {game.gameMetadata.odds && (
                      <View style={styles.oddsContainer}>
                        {game.gameMetadata.odds.spread && (
                          <View style={styles.oddsRow}>
                            <Text style={[styles.oddsLabel, { color: colors.secondaryText }]}>Spread:</Text>
                            <View style={styles.oddsValues}>
                              <Text style={[styles.oddsValue, { color: colors.text }]}>
                                {game.gameMetadata.odds.spread.home > 0 ? '+' : ''}{game.gameMetadata.odds.spread.home}
                              </Text>
                              <Text style={[styles.oddsSeparator, { color: colors.tertiaryText }]}>|</Text>
                              <Text style={[styles.oddsValue, { color: colors.text }]}>
                                {game.gameMetadata.odds.spread.away > 0 ? '+' : ''}{game.gameMetadata.odds.spread.away}
                              </Text>
                            </View>
                          </View>
                        )}
                        {game.gameMetadata.odds.moneyline && (
                          <View style={styles.oddsRow}>
                            <Text style={[styles.oddsLabel, { color: colors.secondaryText }]}>Moneyline:</Text>
                            <View style={styles.oddsValues}>
                              <Text style={[styles.oddsValue, { color: colors.text }]}>
                                {game.gameMetadata.odds.moneyline.home > 0 ? '+' : ''}{game.gameMetadata.odds.moneyline.home}
                              </Text>
                              <Text style={[styles.oddsSeparator, { color: colors.tertiaryText }]}>|</Text>
                              <Text style={[styles.oddsValue, { color: colors.text }]}>
                                {game.gameMetadata.odds.moneyline.away > 0 ? '+' : ''}{game.gameMetadata.odds.moneyline.away}
                              </Text>
                            </View>
                          </View>
                        )}
                      </View>
                    )}
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <View style={styles.noGamesContainer}>
              <Text style={[styles.noGamesText, { color: colors.secondaryText }]}>No games scheduled for this date</Text>
            </View>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
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
    alignItems: 'center',
  },
  dateButtonText: {
    fontSize: 14,
    fontWeight: '500',
  },
  mainScrollView: {
    flex: 1,
  },
  betSection: {
    padding: 16,
    marginBottom: 8,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 12,
  },
  betsContainer: {
    gap: 12,
  },
  gamesContainer: {
    gap: 12,
  },
  betCard: {
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
    elevation: 5,
  },
  betHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  betType: {
    fontSize: 14,
    fontWeight: '600',
  },
  pickBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  pickText: {
    fontSize: 12,
    fontWeight: 'bold',
    color: '#fff',
  },
  betMatchup: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  betDetails: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  betLabel: {
    fontSize: 12,
    fontWeight: '500',
  },
  betStats: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  statText: {
    fontSize: 11,
    fontWeight: '400',
  },
  noBetsContainer: {
    padding: 20,
    alignItems: 'center',
  },
  noBetsText: {
    fontSize: 14,
    fontStyle: 'italic',
  },
  gameRow: {
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
    elevation: 5,
  },
  teamInfo: {
    marginBottom: 12,
  },
  teamVsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
  },
  teamContainer: {
    flex: 1,
    alignItems: 'center',
  },
  teamName: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  score: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#007AFF',
    textAlign: 'center',
    marginBottom: 2,
  },
  pitcherName: {
    fontSize: 11,
    fontWeight: '400',
    textAlign: 'center',
    fontStyle: 'italic',
    marginTop: 2,
  },
  vsText: {
    fontSize: 14,
    fontWeight: '500',
    marginHorizontal: 16,
    fontStyle: 'italic',
  },
  gameInfo: {
    alignItems: 'center',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 12,
    marginBottom: 8,
  },
  statusText: {
    fontSize: 12,
    fontWeight: 'bold',
    color: '#fff',
  },
  timeText: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 4,
  },
  venueText: {
    fontSize: 12,
    marginBottom: 8,
  },
  realtimeContainer: {
    marginTop: 4,
    marginBottom: 8,
    alignItems: 'center',
  },
  realtimeText: {
    fontSize: 11,
    fontWeight: '500',
    marginVertical: 1,
  },
  oddsContainer: {
    marginTop: 8,
    alignItems: 'center',
  },
  oddsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 2,
  },
  oddsLabel: {
    fontSize: 11,
    fontWeight: '500',
    marginRight: 8,
    minWidth: 60,
  },
  oddsValues: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  oddsValue: {
    fontSize: 12,
    fontWeight: '600',
    minWidth: 35,
    textAlign: 'center',
  },
  oddsSeparator: {
    fontSize: 12,
    marginHorizontal: 8,
  },
  noGamesContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  noGamesText: {
    fontSize: 16,
    fontStyle: 'italic',
  },
});

