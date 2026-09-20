# The database, and the read-only MCP server

Everything this project produces used to live as files that overwrote each
other. A backtest wrote `backtest_trades_mcl.csv`; the next run replaced it.
Comparing two runs was impossible, not difficult. This is the fix.

**Status 2026-09-07:** SQL Server 2025 Developer (Standard features) running
locally, database `Trading`, 13 tables, loaded and verified. The MCP server
passes its selftest. Registration with Claude Desktop is the last step.

---

## 1. Why SQL Server and not a folder of CSVs

Ben installed SQL Server 2025 locally and asked for the artefacts to be
organised. The decision recorded at the time, via explicit choice:

- **"Alongside now, replace later."** The loaders push existing files into the
  database. The analysis modules keep reading files for now and get migrated
  one at a time. Nothing had to be rewritten to get the data in.
- **"Load them too"** — minute bars go in the database, not just the metadata
  about them. 6.5 million daily bars are already there; minute bars are the
  larger job and are still pending.

**Edition matters.** Express caps at 50 GB per database, a **1,410 MB buffer
pool** and 4 cores — the buffer pool is the binding one for a table of minute
bars, not the disk cap. Standard Developer is free, carries Standard's limits
(256 GB, 32 cores), and is licensed for non-production use only. That is what
is installed. Note that SQL Server 2025 ships **two** Developer editions
(Standard and Enterprise), which is new — the download page offers both.

---

## 2. The schema — 13 tables

| Table | Holds | Filled by |
|---|---|---|
| `bar_daily` | Databento daily bars, per dataset | `--daily-bars` |
| `bar_minute` | Minute bars from the bar cache | `--minute-bars` |
| `day_dollar_volume` | Per symbol-day close, volume, $ volume | `--dollar-volume` |
| `screen_run` | One screener run and its parameters | `--screen` |
| `screen_candidate` | Survivors **and** rejects, flagged | `--screen` |
| `flex_execution` | Ben's raw fills | `--flex-executions` |
| `flex_round_trip` | Ben's positions, flat to flat | `--flex` |
| `backtest_run` | One strategy on one universe | `--backtests` |
| `backtest_trade` | Every trade of that run | `--backtests` |
| `backtest_coverage` | Every symbol-day attempted, and why it produced nothing | `--backtests` |
| `compound_run` | One compounding replay | `--compound` |
| `compound_sweep` | The (per-trade %, total %) grid | `--compound` |
| `load_run` | Which file produced which rows, and when | every load |

### Idempotence is the whole design

A loader that appends turns "I re-ran that" into duplicated rows and doubled
sums, and **nothing about the result looks wrong**: the tables are valid, the
queries return, the numbers are just twice what they should be.

So every artefact carries a `run_id` derived from its source path and that
file's modification time — `<kind>:<name>:<mtime to the second>` — and a load
**deletes that run_id before inserting it**. Re-running a load is a no-op.
Loading a file that has *changed* replaces its rows and leaves the older run
alone, which is what makes "compare two runs" possible at all.

### Every table must have a way in

Three tables shipped that nothing could ever fill: `flex_execution` had a
loader `main()` never called, and the two compound tables had no loader at all.
They were not empty because the load had not been run — they were empty because
there **was no load to run**, and an empty table looks identical either way.

`db_load.FILLED_BY` maps every table to the flag that fills it, and a test
fails if a table is added without one, if the map names a flag the CLI does not
have, or if it names a table that no longer exists.

### Two traps the loaders exist to avoid

- **Cache windows overlap.** Each `SYMBOL_DATE.csv.gz` holds three sessions
  ending on its own date, so consecutive files for one symbol share two of them.
  Loaded file by file, every bar would be stored about three times and
  `SUM(volume)` would read three times the market's volume while looking
  entirely reasonable. `minute_rows()` deduplicates per symbol, not per file.
- **The ET minute is measured, not derived.** `--flex-executions` parses
  through `common.flex`, which resolves the report's timezone by scoring
  candidate IANA zones. The true ET offset moves between 13 and 16 hours across
  the year because the US and Australia change DST on different dates — a
  constant offset applied to a stored timestamp is wrong for part of every year
  and looks right in the table.

---

## 3. The MCP server — read-only by login, not by good intentions

`common/mcp_sql.py` exposes three tools: `read_query`, `list_tables`,
`describe_table`.

**The control is the SQL Server login, not the code.** The server connects as a
`db_datareader`-only login. The statement guard in `check_select()` — reject
anything that is not `SELECT`/`WITH`, reject a second statement, strip comments
first so a line comment cannot smuggle one past — is **advisory**: it gives a
clear refusal instead of a driver error, and that is all it is for.

`--selftest` proves this rather than asserting it: it attempts an INSERT **with
the guard deliberately bypassed** and requires SQL Server itself to refuse.
A selftest that could only pass would be decoration. On 2026-09-07 it returned:

```
GOOD -- the server refused the write: The INSERT permission ...
```

`TRADING_DB_RO_URL` is deliberately a **different variable** from the loaders'
`TRADING_DB_URL`. Pointing the server at the read-write connection would hand
an agent exactly the rights this design exists to withhold, and a working
server would look identical either way. Two names, so the mistake has to be
typed. An unset `TRADING_DB_RO_URL` exits rather than falling back.

### Registering it with Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "trading-sql": {
      "command": "D:\\Trading\\.venv\\Scripts\\python.exe",
      "args": ["-m", "common.mcp_sql"],
      "cwd": "D:\\Trading"
    }
  }
}
```

The connection details go in the **user environment**, not in that file — a
password in a JSON file inside a roaming profile is a password in a synced
folder:

```powershell
setx TRADING_DB_RO_URL "mssql+pyodbc://trading-algo@localhost/Trading?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes"
setx TRADING_DB_RO_PASSWORD "<the read-only password>"
```

The URL carries **no password**; `TRADING_DB_RO_PASSWORD` supplies it
separately. Then quit Claude Desktop fully (tray → Quit) and reopen.

---

## 4. The password incident, 2026-09-07

Ben's SQL password contained an `@`. A connection URL splits on `@` to separate
credentials from host, so the URL broke at the wrong place, the driver reported
the password fragment **as the hostname**, and it reached the chat.

The scrubber did not catch it because it matched the pattern `:password@` and
assumed a well-formed URL. A URL that has already broken does not match the
pattern for a URL.

Three fixes:

1. `remember_secret()` — scrubbing is **value-based**, not pattern-based, and
   registers the URL-splittable fragments of a secret as well as the whole
   thing, because a broken URL is exactly how a fragment escapes alone.
2. `url_from_parts()` builds URLs with SQLAlchemy's `URL.create`, which escapes
   properly, instead of string concatenation.
3. `<VAR>_PASSWORD` — the password never goes in the URL at all.

**The password was rotated.** Anything with URL metacharacters is now covered
by a round-trip test.

---

## 5. Current state

| Table | Rows | Note |
|---|---|---|
| `bar_daily` | 6,468,996 | |
| `backtest_coverage` | 1,761 | |
| `flex_round_trip` | 1,658 | Ben's real positions |
| `backtest_trade` | 1,629 | |
| `day_dollar_volume` | 587 | |
| `backtest_run` | 3 | |
| `load_run` | 5 | |
| `screen_run`, `screen_candidate` | 0 | loader exists, not yet run |
| `bar_minute` | 0 | loader exists, not yet run |
| `flex_execution`, `compound_run`, `compound_sweep` | 0 | loaders **added 2026-09-07**, not yet run |

To fill the rest:

```powershell
python -m common.db_load --screen var\state\screen_pairs_consolidated.json var\state\screen_rejects.json
python -m common.db_load --minute-bars bar_cache_db
python -m common.db_load --flex-executions <the Flex report CSVs>
python -m common.db_load --compound var\reports\compound_run.csv var\reports\compound_sweep.csv
```

`--compound` needs `common.compound_sim` re-run first: the single-run mode did
not write a CSV until 2026-09-07, so the headline result — the one an actual
decision gets made on — was the only figure in that module that could not be
loaded, queried, or compared against a later run. The two modes also shared an
output filename, so whichever ran last silently replaced the other's results
under a name that still looked correct. They now default to
`compound_run.csv` and `compound_sweep.csv`, and the loader dispatches on the
CSV **header**, never the filename.
