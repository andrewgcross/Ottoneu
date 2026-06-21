# Known Gaps & Future Work

## 1. Name collision risk in Savant search fallback

`_resolveViaPages()` searches Baseball Savant by last name and picks the first result whose
first name starts with the same 3 letters. This is fragile for:
- Common surnames (e.g. "Martinez", "Ramirez", "Garcia") with multiple active players
- Players whose display name differs from their Savant registration name
- Name suffixes (Jr./III) that may or may not appear in Savant search results

**Mitigation:** The ✏️ manual override link on every player row lets you set the MLBAM ID
directly. Once set, it's cached permanently and the search fallback never runs again for
that player.

---

## 2. Remaining high-value page targets

`otto-statcast.user.js` currently covers setlineups, search, roster (`/*/team`), and individual player pages. Still missing:

- **Trade analyser** — comparing player values across teams
- **Roster add page** (`/roster/add`) — if separate from `/search`
