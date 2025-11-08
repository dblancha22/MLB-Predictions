import { boolean, date, integer, numeric, pgTable, serial, text, timestamp } from "drizzle-orm/pg-core";

export const bets = pgTable("bets", {
  id: serial('id').primaryKey(),
  game_id: text('game_id'),
  pick: text('pick'),
  odds: integer('odds'),
  super_bet: boolean('super_bet'),
  created_at: timestamp('created_at'),
});

export const games = pgTable('games', {
  game_id: text('game_id').primaryKey(),
  home_team: text('home_team'),
  away_team: text('away_team'),
  date: date('date'),
  created_at: timestamp('created_at'),
});

export const historicalGames = pgTable('historical_games', {
  id: serial('id').primaryKey(),
  game_id: text('game_id'),
  date: date('date').notNull(),
  team: text('team').notNull(),
  opponent_team: text('opponent_team').notNull(),
  is_home: boolean('is_home'),
  team_win_pct: numeric('team_win_pct'),
  team_total_games: integer('team_total_games'),
  closing_moneyline_odds: integer('closing_moneyline_odds'),
  opp_win_pct: numeric('opp_win_pct'),
  opp_pitcher_era: numeric('opp_pitcher_era'),
  opp_pitcher_is_lefty: boolean('opp_pitcher_is_lefty'),
  runs_scored: integer('runs_scored'),
  hits: integer('hits'),
  game_ops: numeric('game_ops'),
  created_at: timestamp('created_at'),
});

export const historicalPredictions = pgTable('historical_predictions', {
  id: serial('id').primaryKey(),
  game_id: text('game_id'),
  date: date('date').notNull(),
  prediction_type: text('prediction_type').notNull(),
  projected_score_diff: numeric('projected_score_diff'),
  odds_implied_score_diff: numeric('odds_implied_score_diff'),
  projected_win_pct: numeric('projected_win_pct'),
  odds_implied_win_pct: numeric('odds_implied_win_pct'),
  total_diff: numeric('total_diff'),
  units_won: numeric('units_won'),
  odds: integer('odds'),
  pick: text('pick'),
  best_bet: boolean('best_bet'),
  created_at: timestamp('created_at'),
});
