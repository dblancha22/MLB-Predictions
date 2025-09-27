export interface BaseballGame {
    id: string;
    gameMetadata: {
        status: 'scheduled' | 'live' | 'final';
        dateTime: Date;
        venue: string;
        homeTeam: string;
        awayTeam: string;
        odds?: {
            spread?: {
              home: number;
              away: number;
            };
            moneyline?: {
              home: number;
              away: number;
            };
          };
    }
    homeTeamData: {
        homeTeam: string;
        homePitcher?: string;
    }
    awayTeamData: {
        awayTeam: string;
        awayPitcher?: string;
    }
    gameRealTimeData: {
        homeScore?: number;
        awayScore?: number;
        inning?: number;
        inningHalf?: 'top' | 'bottom';
        balls?: number;
        strikes?: number;
        outs?: number;
    }
  }
  
// Mock data for demonstration
export const mockGamesData: Record<string, BaseballGame[]> = {
'2025-09-24': [
    {
    id: '1',
    gameMetadata: {
      status: 'scheduled',
      dateTime: new Date('2025-09-24T19:05:00'),
      venue: 'Yankee Stadium',
      homeTeam: 'Yankees',
      awayTeam: 'Red Sox',
      odds: {
        spread: { home: -1.5, away: 1.5 },
        moneyline: { home: -120, away: 100 }
      }
    },
    homeTeamData: {
      homeTeam: 'Yankees',
      homePitcher: 'Gerrit Cole'
    },
    awayTeamData: {
      awayTeam: 'Red Sox',
      awayPitcher: 'Chris Sale'
    },
    gameRealTimeData: {}
    },
    {
    id: '2',
    gameMetadata: {
      status: 'live',
      dateTime: new Date('2025-09-24T18:00:00'),
      venue: 'Dodger Stadium',
      homeTeam: 'Dodgers',
      awayTeam: 'Giants',
      odds: {
        spread: { home: -2.5, away: 2.5 },
        moneyline: { home: -180, away: 150 }
      }
    },
    homeTeamData: {
      homeTeam: 'Dodgers',
      homePitcher: 'Walker Buehler'
    },
    awayTeamData: {
      awayTeam: 'Giants',
      awayPitcher: 'Logan Webb'
    },
    gameRealTimeData: {
      homeScore: 3,
      awayScore: 2,
      inning: 6,
      inningHalf: 'top',
      balls: 2,
      strikes: 1,
      outs: 1
    }
    },
    {
    id: '3',
    gameMetadata: {
      status: 'final',
      dateTime: new Date('2025-09-24T14:20:00'),
      venue: 'Wrigley Field',
      homeTeam: 'Cubs',
      awayTeam: 'Cardinals',
      odds: {
        spread: { home: -1.0, away: 1.0 },
        moneyline: { home: -110, away: -110 }
      }
    },
    homeTeamData: {
      homeTeam: 'Cubs',
      homePitcher: 'Marcus Stroman'
    },
    awayTeamData: {
      awayTeam: 'Cardinals',
      awayPitcher: 'Adam Wainwright'
    },
    gameRealTimeData: {
      homeScore: 5,
      awayScore: 4,
      inning: 9,
      inningHalf: 'bottom',
      balls: 0,
      strikes: 2,
      outs: 3
    }
    }
],
'2025-09-25': [
    {
    id: '4',
    gameMetadata: {
      status: 'scheduled',
      dateTime: new Date('2025-09-25T20:10:00'),
      venue: 'Minute Maid Park',
      homeTeam: 'Astros',
      awayTeam: 'Rangers',
      odds: {
        spread: { home: -0.5, away: 0.5 },
        moneyline: { home: -105, away: -115 }
      }
    },
    homeTeamData: {
      homeTeam: 'Astros',
      homePitcher: 'Framber Valdez'
    },
    awayTeamData: {
      awayTeam: 'Rangers',
      awayPitcher: 'Nathan Eovaldi'
    },
    gameRealTimeData: {}
    },
    {
    id: '5',
    gameMetadata: {
      status: 'scheduled',
      dateTime: new Date('2025-09-25T19:10:00'),
      venue: 'Citi Field',
      homeTeam: 'Mets',
      awayTeam: 'Phillies',
      odds: {
        spread: { home: 1.5, away: -1.5 },
        moneyline: { home: 130, away: -150 }
      }
    },
    homeTeamData: {
      homeTeam: 'Mets',
      homePitcher: 'Jacob deGrom'
    },
    awayTeamData: {
      awayTeam: 'Phillies',
      awayPitcher: 'Aaron Nola'
    },
    gameRealTimeData: {}
    }
],
'2025-09-26': [
    {
    id: '6',
    gameMetadata: {
      status: 'scheduled',
      dateTime: new Date('2025-09-26T21:40:00'),
      venue: 'Petco Park',
      homeTeam: 'Padres',
      awayTeam: 'Diamondbacks',
      odds: {
        spread: { home: -3.0, away: 3.0 },
        moneyline: { home: -200, away: 170 }
      }
    },
    homeTeamData: {
      homeTeam: 'Padres',
      homePitcher: 'Yu Darvish'
    },
    awayTeamData: {
      awayTeam: 'Diamondbacks',
      awayPitcher: 'Zac Gallen'
    },
    gameRealTimeData: {}
    }
]
};
