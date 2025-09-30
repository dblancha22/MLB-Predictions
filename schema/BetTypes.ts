export interface BetOnTeam {
    gameId: string;
    dateTime: Date;
    favoriteTeam: string;
    underdogTeam: string;
    type: 'spread' | 'moneyline';
    spread: number;
    pick: 'favorite' | 'underdog';
    odds: {
        plusMinus: '+' | '-';
        value: number;
    };
    // Not sure if these are needed
    projectedScoreDiff: number;
    scoreDiffFromExpected: number;
    projectedWinPercent: number;
    winPercentDiffFromExpected: number;
}

export interface BetOnTotal {
    gameId: string;
    dateTime: Date;
    total: number;
    pick: 'over' | 'under';
    odds: {
        plusMinus: '+' | '-';
        value: number;
    };
}

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

// Mock data for demonstration
export const mockBetOnTeamData: BetOnTeam[] = [
    {
        gameId: '1',
        dateTime: getTodayDate(19, 5),
        favoriteTeam: 'Yankees',
        underdogTeam: 'Red Sox',
        type: 'spread',
        spread: -1.5,
        pick: 'favorite',
        odds: {
            plusMinus: '-',
            value: 120
        },
        projectedScoreDiff: -2.3,
        scoreDiffFromExpected: -0.8,
        projectedWinPercent: 68.5,
        winPercentDiffFromExpected: 3.2
    },
    {
        gameId: '1',
        dateTime: getTodayDate(19, 5),
        favoriteTeam: 'Yankees',
        underdogTeam: 'Red Sox',
        type: 'moneyline',
        spread: -1.5,
        pick: 'favorite',
        odds: {
            plusMinus: '-',
            value: 120
        },
        projectedScoreDiff: -2.3,
        scoreDiffFromExpected: -0.8,
        projectedWinPercent: 68.5,
        winPercentDiffFromExpected: 3.2
    },
    {
        gameId: '2',
        dateTime: getTodayDate(18, 0),
        favoriteTeam: 'Dodgers',
        underdogTeam: 'Giants',
        type: 'spread',
        spread: -2.5,
        pick: 'underdog',
        odds: {
            plusMinus: '+',
            value: 150
        },
        projectedScoreDiff: -1.8,
        scoreDiffFromExpected: 0.7,
        projectedWinPercent: 45.2,
        winPercentDiffFromExpected: -2.1
    },
    {
        gameId: '4',
        dateTime: getTomorrowDate(20, 10),
        favoriteTeam: 'Rangers',
        underdogTeam: 'Astros',
        type: 'moneyline',
        spread: 0.5,
        pick: 'underdog',
        odds: {
            plusMinus: '-',
            value: 115
        },
        projectedScoreDiff: 0.3,
        scoreDiffFromExpected: -0.2,
        projectedWinPercent: 52.1,
        winPercentDiffFromExpected: 1.8
    },
    {
        gameId: '5',
        dateTime: getTomorrowDate(19, 10),
        favoriteTeam: 'Phillies',
        underdogTeam: 'Mets',
        type: 'spread',
        spread: -1.5,
        pick: 'favorite',
        odds: {
            plusMinus: '-',
            value: 150
        },
        projectedScoreDiff: -2.1,
        scoreDiffFromExpected: -0.6,
        projectedWinPercent: 72.3,
        winPercentDiffFromExpected: 4.1
    }
];

export const mockBetOnTotalData: BetOnTotal[] = [
    {
        gameId: '1',
        dateTime: getTodayDate(19, 5),
        total: 8.5,
        pick: 'over',
        odds: {
            plusMinus: '-',
            value: 110
        }
    },
    {
        gameId: '2',
        dateTime: getTodayDate(18, 0),
        total: 7.0,
        pick: 'under',
        odds: {
            plusMinus: '+',
            value: 105
        }
    },
    {
        gameId: '3',
        dateTime: getTodayDate(14, 20),
        total: 9.5,
        pick: 'over',
        odds: {
            plusMinus: '-',
            value: 115
        }
    },
    {
        gameId: '4',
        dateTime: getTomorrowDate(20, 10),
        total: 8.0,
        pick: 'under',
        odds: {
            plusMinus: '+',
            value: 120
        }
    },
    {
        gameId: '5',
        dateTime: getTomorrowDate(19, 10),
        total: 6.5,
        pick: 'over',
        odds: {
            plusMinus: '-',
            value: 105
        }
    }
];