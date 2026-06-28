# Ottoneu Auto Roster Set

Automates daily lineup management for an Ottoneu fantasy baseball team. Authenticates to FanGraphs via WordPress login, scrapes the current lineup page, then benches non-starters and fills empty slots with the best available confirmed starters. Handles both batters and pitchers. Intended to run several times per day as a scheduled task.

## Requirements

- Python 3.9+
- `requests`, `beautifulsoup4`, `pandas`, `python-dotenv`

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
pip install requests beautifulsoup4 pandas python-dotenv
```

## Setup

```bash
python setup_config.py
```

Creates `.env` with your credentials and initializes `hot_offenses.json` and `movement_log.txt`. Never commit `.env`.

## Configuration

All settings live in `.env`:

| Variable | Required | Description |
|---|---|---|
| `OTTONEU_USERNAME` | Yes | FanGraphs login email |
| `OTTONEU_PASSWORD` | Yes | FanGraphs password |
| `LEAGUE` | Yes | Ottoneu league ID (from the URL) |
| `TEAM_ID` | No | Your team ID — required to view a future date's lineup |
| `TARGET_DATE` | No | Override today's date (YYYY-MM-DD) for debugging |
| `HOT_OFFENSE_WEEKS` | No | Lookback window for hot offense detection (default: 3) |
| `CATCHER_SLOTS_TO_FILL` | No | How many C slots to fill: 1 or 2 (default: 2) |
| `PITCHER_OVERRIDE_STRICT` | No | If `true`, strict mode evicts SP-override pitchers even when Starting=True (default: false) |

## Running

```bash
python auto-roster-set.py
```

Moves are logged to `movement_log.txt`. Run this several times per day — lineup confirmations trickle in throughout the morning.

## Pitcher Role Overrides

Two-way players who have both SP and RP Ottoneu eligibility but are currently used in only one MLB role can be pinned in `pitcher_role_overrides.txt`:

```
# Format: Display Name = SP or RP
Cristopher Sanchez = RP
Paul Skenes = SP
```

Set `PITCHER_OVERRIDE_STRICT=true` in `.env` to also evict these players from the wrong slot even after lineup lock.

## How It Works

**Batter logic**

1. Bench any active lineup player who has no game, is confirmed not starting, or is not yet confirmed (the script re-runs will catch them later once confirmed).
2. Fill empty slots using a scarcity heuristic: players eligible at fewer positions are placed first so that flexible players remain available for flex slots (MI, Util). Batting order and platoon advantage break ties.

**Pitcher logic**

1. Bench SPs not confirmed as today's starter.
2. Bench RPs who are confirmed starters with SP eligibility (they belong in an SP slot), are fatigued (pitched on each of the last two days), or have no game.
3. Fill SP slots with confirmed starters — skipping pitchers facing a hot offense (positive team Offense value over the last `HOT_OFFENSE_WEEKS` weeks per FanGraphs).
4. Fill RP slots with relievers not facing fatigue; Following status takes priority over P/IP.

**Caching**

`hot_offenses.json` and `games_played.json` cache daily data so repeated runs don't re-fetch from FanGraphs. Both files are only written on a successful fetch — a network failure won't poison the cache and block future retries.

## Deployment on Synology NAS

The production environment is a Synology NAS running the script on a schedule via DSM Task Scheduler (User-Defined Script):

```bash
cd /volume1/Assorted/multimedia/scripts/Ottoneu
git pull origin main >> run_log.txt
/volume1/Assorted/multimedia/scripts/Ottoneu/synology_env/bin/python auto-roster-set.py >> run_log.txt 2>&1
```

To push local changes to the NAS, run `push-to-nas.bat` (Windows only, path is gitignored). It uses robocopy with `/XO` so newer files on the NAS (logs, JSON caches) are never overwritten by older local copies.

## Files

| File | Description |
|---|---|
| `auto-roster-set.py` | Main script |
| `return_hot_offenses.py` | Fetches team Offense rankings from FanGraphs API; caches to `hot_offenses.json` |
| `return_games_played.py` | Scrapes the Ottoneu games-played tracker; caches to `games_played.json` |
| `setup_config.py` | Interactive setup — creates `.env` and initializes data files |
| `pitcher_role_overrides.txt` | Manual SP/RP role pins for two-way eligible pitchers |
| `hot_offenses.json` | Daily cache of hot offense teams (one entry per date) |
| `games_played.json` | Daily cache of projected games-played counts per position |
| `movement_log.txt` | Append-only log of every lineup move with timestamp |