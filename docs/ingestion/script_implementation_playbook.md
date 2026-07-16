# Raw Ingestion Script Implementation Playbook

Use this process when adding or materially changing a script that writes an MLB
raw table. It captures the workflow proven while building
`scripts/ingest_games_raw.py`. Table-specific requirements remain in the source
map, schema catalog, raw-data plan, and acceptance checklist.

## 1. Define The Table Contract

Before writing code, record:

- target table and purpose
- source endpoint and parameters
- canonical primary/upsert key
- required foreign keys and dependency order
- whether each field is pregame-safe, mutable, or postgame-only
- expected nulls and source fields that are unavailable
- routine cadence, recovery window, and backfill behavior

Do not infer a cadence from another table. For example, the routine
`games_raw` job processes only the previous calendar day, while another table
may eventually have a different approved schedule.

Update these documents before or alongside implementation:

- `mlb_stats_api_sources.md` for endpoint and source-field behavior
- `supabase_table_catalog.md` for the live table contract
- `raw_data_plan.md` for ordering, cadence, and idempotency
- `data_timing_and_leakage.md` when field availability affects future modeling

## 2. Inspect Live State And Probe The API

Inspect the live Supabase table rather than relying only on repository notes:

- columns, types, defaults, nullability, keys, and constraints
- existing row counts and date coverage
- foreign-key dependencies
- RLS and advisor findings

Probe the MLB endpoint with representative real examples:

- an ordinary completed game
- a no-game date
- a doubleheader when relevant
- postponed, suspended, resumed, or otherwise unusual records
- records with missing optional fields

Confirm exact field paths and codes from responses. Preserve MLB identifiers and
raw categorical codes unless a documented conversion is necessary.

## 3. Decide Schema Changes Explicitly

Add columns only when they preserve useful raw source data or are required for
durable ingestion. Prefer:

- `timestamptz` for absolute instants
- `date` for MLB's local/official game date
- integer MLB IDs as canonical identifiers
- nullable columns for genuinely optional source data
- raw text codes when a boolean would discard source meaning

Apply schema changes before deploying a writer that depends on them. Record the
live change immediately in `supabase_table_catalog.md` and relevant source docs.

## 4. Implement A Narrow, Resumable Writer

Keep each script limited to raw ingestion. It should:

- load secrets from environment configuration
- refuse to write to the wrong Supabase project
- support one date and an inclusive date range
- support a dry run before broad writes
- use retries for transient MLB requests
- insert dependency rows before rows with foreign keys
- use documented primary keys for idempotent upserts
- avoid erasing previously stored final or optional values with incomplete data
- log the date, source, table action, skipped records, and summary counts

Treat repeated source occurrences carefully. Compare canonical IDs across dates,
not only within one response. A postponed or resumed game may appear on more than
one schedule date with the same `gamePk` and different contextual fields.

## 5. Test Transform And Write Behavior

Add unit tests before a live backfill. Cover:

- normal field mapping and type conversion
- missing optional fields
- final versus non-final data rules
- dependency deduplication and insertion order
- idempotent upsert behavior
- time-zone normalization
- table-specific edge cases observed in real API responses
- preservation of existing values during partial updates

Tests should use compact source-shaped fixtures and fake database clients. Do not
make routine unit tests depend on live MLB or Supabase availability.

## 6. Validate With A Small Live Slice

Use this sequence:

1. Run tests.
2. Dry-run one representative date.
3. Run that date live.
4. Run it live again to confirm idempotency.
5. Compare source fields with stored rows, not only row counts.
6. Check duplicates, nulls, scores, foreign keys, and unexpected source codes.

Do not begin a broad backfill until the small live slice passes.

## 7. Backfill In Bounded Ranges

Before starting, document the intended range and expected overlap with existing
rows. Backfill in ranges that are easy to retry and audit. Track:

- source occurrences found
- intentionally skipped records and reasons
- rows upserted
- new dependency rows inserted
- transient failures and successful retries

Distinguish source occurrences from unique canonical rows. The same MLB ID may
appear on multiple dates, so the expected table count is the unique upsert-key
count after documented skip and merge rules.

## 8. Audit The Result

After the backfill, query the database for:

- total and distinct primary-key counts
- date coverage
- status distribution
- required-field and expected-null counts
- final rows missing final values
- invalid or unexpected categorical codes
- invalid numeric ranges
- broken foreign keys
- newly inserted dependency rows and their completeness

Investigate discrepancies instead of explaining them away. If an audit reveals
an API quirk or partial-update problem:

1. inspect the exact source responses
2. add a regression test
3. fix preservation or merge logic
4. rerun only the affected range
5. repeat the full database audit
6. document the learning in the source map and table catalog

## 9. Completion Gate

An ingestion script is complete only when:

- the relevant items in `acceptance_checklist.md` pass
- tests pass
- a live rerun is idempotent
- source-to-database comparisons pass
- the backfill audit has no unexplained discrepancies
- unavailable source fields are documented rather than invented
- live schema, row coverage, cadence, and API quirks are reflected in repo docs

Report known unrelated advisor findings separately. Do not silently broaden the
task to security-policy or index changes without an approved access/query design.
