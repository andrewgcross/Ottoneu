# Pitcher Role Override Design

**Date:** 2026-06-23

## Problem

Some pitchers have both SP and RP Ottoneu eligibility. Ottoneu only awards points when the pitcher is in the slot matching their actual MLB usage — a starter in an RP slot earns nothing, and vice versa. The script cannot infer a pitcher's current real-world role from the daily `Starting` indicator alone (e.g., a rotation pitcher on a non-start day has `Starting = False` and could be incorrectly placed in an RP slot).

## Solution

A manually-maintained text file (`pitcher_role_overrides.txt`) lets the user pin specific pitchers to SP-only or RP-only. The script strips the unwanted eligibility flag from `df_pitchers` before any bench/fill logic runs, so all downstream decisions naturally respect the override.

## Override File Format

File: `pitcher_role_overrides.txt` (repo root, alongside `hot_offenses.json` and `.env`)

```
# Lines starting with # are comments
# Format: Display Name = SP or RP
Spencer Strider = SP
Cristopher Sanchez = RP
Paul Skenes = SP
```

- Role value is case-insensitive
- Blank lines are ignored
- File absence is a silent no-op
- Malformed lines (missing `=`, unrecognized role) print a warning and are skipped

## Implementation

### 1. `load_pitcher_overrides(filepath)` function

Returns `dict[str, str]` mapping display name → `"SP"` or `"RP"`. Called once, result applied immediately after `df_pitchers` is built (currently line 598).

### 2. Apply overrides to `df_pitchers`

```
overrides = load_pitcher_overrides("pitcher_role_overrides.txt")
for name, role in overrides.items():
    mask = df_pitchers['Name'] == name
    if not mask.any():
        print(f"Warning: override name '{name}' not found on roster")
        continue
    if role == 'SP':
        df_pitchers.loc[mask, 'RP'] = False
    elif role == 'RP':
        df_pitchers.loc[mask, 'SP'] = False
```

### 3. Fix SP fill to check `SP == True`

The SP fill candidates filter currently requires only `Starting == True` — it does not check `SP == True`. This means a pure-RP pitcher who unexpectedly has `Starting == True` (emergency spot start) could be placed in an SP slot. Adding `(df_pitchers['SP'] == True)` to the filter closes this gap and makes RP-only overrides effective on days when `Starting` happens to be True.

## Data Flow

```
soup parsed → df_pitchers built
                    ↓
         load_pitcher_overrides()
                    ↓
         apply: strip RP/SP flag
                    ↓
    bench/fill logic runs (unchanged)
```

## What Is Not Changing

- Bench logic for SP/RP slots is unchanged — it operates on `Starting`, `gamescheduled`, and fatigue, not on eligibility flags.
- No new columns added to `df_pitchers`.
- The override file is gitignored-candidate (personal roster knowledge), but can be checked in if the user prefers.
