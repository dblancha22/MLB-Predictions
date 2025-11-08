// src/db/db.ts
import "dotenv/config"; // Loads .env variables
import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";

// Make sure DATABASE_URL exists
const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
  throw new Error("DATABASE_URL environment variable not set");
}

// Create Postgres client
const sqlClient = postgres(connectionString, {
  ssl: "require", // Supabase requires SSL
  prepare: false,
});

// Create Drizzle instance
export const drizzy = drizzle(sqlClient);

// Export raw sql client if needed for raw queries
export default sqlClient;
