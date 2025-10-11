export interface BetOnTeam {
  gameId: string;
  dateTime: Date;
  homeTeam: string;
  awayTeam: string;
  pick: string;
  // All bets are moneyline
  // type: 'spread' | 'moneyline';
  // spread: number;
  odds: number;
  result?: {
    outcome: "win" | "loss";
    finalScore: {
      home: number;
      away: number;
    };
  };
  // For now we will not display confidence level related info, but we will keep the fields here for future use
  // confidenceLevel: number;
  // projectedScoreDiff: number;
  // scoreDiffFromExpected: number;
  // projectedWinPercent: number;
  // winPercentDiffFromExpected: number;
}

export interface BetOnTotal {
  gameId: string;
  dateTime: Date;
  homeTeam: string;
  awayTeam: string;
  total: number;
  pick: "over" | "under";
  odds: number;
  result?: {
    outcome: "win" | "loss";
    // actualTotal: number;
    finalScore: {
      home: number;
      away: number;
    };
  };
}

// export interface HistoricalBetOnTeam extends BetOnTeam {
//     outcome: 'win' | 'loss' | 'pending';
//     finalScore?: {
//         home: number;
//         away: number;
//     };
// }

// export interface HistoricalBetOnTotal extends BetOnTotal {
//     outcome: 'win' | 'loss' | 'pending';
//     actualTotal?: number;
//     finalScore?: {
//         home: number;
//         away: number;
//     };
// }

// Helper functions for dates
const getTodayDate = (hour: number, minute: number = 0) => {
  const today = new Date();
  today.setHours(hour, minute, 0, 0);
  return today;
};

const getTomorrowDate = (hour: number, minute: number = 0) => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(hour, minute, 0, 0);
  return tomorrow;
};

// Helper functions for historical dates
const getHistoricalDate = (
  daysAgo: number,
  hour: number,
  minute: number = 0,
) => {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  date.setHours(hour, minute, 0, 0);
  return date;
};

// Mock data for demonstration
export const mockBetOnTeamData: BetOnTeam[] = [
  {
    gameId: "1",
    dateTime: getTodayDate(19, 5),
    homeTeam: "Yankees",
    awayTeam: "Red Sox",
    pick: "Yankees",
    odds: 120,
  },
  {
    gameId: "2",
    dateTime: getTodayDate(18, 0),
    homeTeam: "Dodgers",
    awayTeam: "Giants",
    pick: "Giants",
    odds: 150,
  },
  {
    gameId: "4",
    dateTime: getTomorrowDate(20, 10),
    homeTeam: "Rangers",
    awayTeam: "Astros",
    pick: "Astros",
    odds: 115,
  },
  {
    gameId: "5",
    dateTime: getTomorrowDate(19, 10),
    homeTeam: "Phillies",
    awayTeam: "Mets",
    pick: "Phillies",
    odds: -150,
  },
  {
    gameId: "hist-1",
    dateTime: getHistoricalDate(1, 19, 5),
    homeTeam: "Braves",
    awayTeam: "Marlins",
    pick: "Braves",
    odds: 110,
    result: { outcome: "win", finalScore: { home: 6, away: 3 } },
  },
  {
    gameId: "hist-2",
    dateTime: getHistoricalDate(1, 20, 0),
    homeTeam: "Twins",
    awayTeam: "Guardians",
    pick: "Guardians",
    odds: 125,
    result: { outcome: "loss", finalScore: { home: 5, away: 3 } },
  },
  {
    gameId: "hist-3",
    dateTime: getHistoricalDate(2, 18, 30),
    homeTeam: "Rays",
    awayTeam: "Orioles",
    pick: "Rays",
    odds: -130,
    result: { outcome: "win", finalScore: { home: 7, away: 3 } },
  },
  {
    gameId: "hist-4",
    dateTime: getHistoricalDate(2, 19, 15),
    homeTeam: "Blue Jays",
    awayTeam: "Red Sox",
    pick: "Blue Jays",
    odds: 115,
    result: { outcome: "loss", finalScore: { home: 4, away: 5 } },
  },
  {
    gameId: "hist-5",
    dateTime: getHistoricalDate(3, 20, 10),
    homeTeam: "Padres",
    awayTeam: "Diamondbacks",
    pick: "Diamondbacks",
    odds: -110,
    result: { outcome: "win", finalScore: { home: 3, away: 3 } },
  },
];

export const mockBetOnTotalData: BetOnTotal[] = [
  {
    gameId: "1",
    dateTime: getTodayDate(19, 5),
    homeTeam: "Yankees",
    awayTeam: "Red Sox",
    total: 8.5,
    pick: "over",
    odds: 110,
  },
  {
    gameId: "2",
    dateTime: getTodayDate(18, 0),
    homeTeam: "Dodgers",
    awayTeam: "Giants",
    total: 7.0,
    pick: "under",
    odds: 105,
  },
  {
    gameId: "3",
    dateTime: getTodayDate(14, 20),
    homeTeam: "Cubs",
    awayTeam: "Cardinals",
    total: 9.5,
    pick: "over",
    odds: 115,
  },
  {
    gameId: "4",
    dateTime: getTomorrowDate(20, 10),
    homeTeam: "Rangers",
    awayTeam: "Astros",
    total: 8.0,
    pick: "under",
    odds: 120,
  },
  {
    gameId: "5",
    dateTime: getTomorrowDate(19, 10),
    homeTeam: "Phillies",
    awayTeam: "Mets",
    total: 6.5,
    pick: "over",
    odds: 105,
  },
  {
    gameId: "hist-1",
    dateTime: getHistoricalDate(1, 19, 5),
    homeTeam: "Braves",
    awayTeam: "Marlins",
    total: 8.5,
    pick: "over",
    odds: 115,
    result: {
      outcome: "win",
      finalScore: { home: 6, away: 3 },
    },
  },
  {
    gameId: "hist-2",
    dateTime: getHistoricalDate(1, 20, 0),
    homeTeam: "Twins",
    awayTeam: "Guardians",
    total: 7.0,
    pick: "under",
    odds: 105,
    result: {
      outcome: "loss",
      finalScore: { home: 5, away: 3 },
    },
  },
  {
    gameId: "hist-3",
    dateTime: getHistoricalDate(2, 18, 30),
    homeTeam: "Rays",
    awayTeam: "Orioles",
    total: 9.0,
    pick: "over",
    odds: 110,
    result: {
      outcome: "win",
      finalScore: { home: 7, away: 3 },
    },
  },
  {
    gameId: "hist-4",
    dateTime: getHistoricalDate(2, 19, 15),
    homeTeam: "Blue Jays",
    awayTeam: "Red Sox",
    total: 8.5,
    pick: "under",
    odds: 120,
    result: {
      outcome: "loss",
      finalScore: { home: 4, away: 5 },
    },
  },
  {
    gameId: "hist-5",
    dateTime: getHistoricalDate(3, 20, 10),
    homeTeam: "Padres",
    awayTeam: "Diamondbacks",
    total: 6.0,
    pick: "under",
    odds: 100,
    result: {
      outcome: "win",
      finalScore: { home: 3, away: 3 },
    },
  },
];
