# -*- coding: utf-8 -*-

"""
Ottoneu Auto Roster Set
Andrew Cross
http://www.agcross.com
v2.1

After entering your login credentials, and establishing the lineup you'd like to
prioritize, this script can be run to set your lineup depending on which players
are starting. It's best run automatically with a CRON job.

Optimized for Python 3.9.25 to be compatible with my Synology environment
"""

import requests
from bs4 import BeautifulSoup, Tag
import datetime
import pandas as pd
from dotenv import load_dotenv
from typing import Any, cast
import os
import json
from return_hot_offenses import return_hot_offenses

# This loads the variables from the .env file into the system environment
load_dotenv()
league_id = os.getenv("LEAGUE")
target_date = os.getenv("TARGET_DATE")  # Optional: override today's date (YYYY-MM-DD) for debugging
team_id = os.getenv("TEAM_ID")          # Optional: required to view a specific future date's lineup

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://blogs.fangraphs.com/wp-login.php'
})

# Maps US timezone abbreviations used by Ottoneu to their UTC offsets (during DST)
_TZ_OFFSETS = {
    'EDT': -4, 'CDT': -5, 'MDT': -6, 'PDT': -7,
    'EST': -5, 'CST': -6, 'MST': -7, 'PST': -8,
}

# Span classes whose text should be excluded from game info (indicators and screen-reader labels)
_EXCLUDED_SPAN_CLASSES = {'starting-indicator', 'not-starting-indicator', 'following-indicator', 'sr-only'}

def get_game_info_text(span: Tag) -> str:
    """Extract the game info string from a .lineup-game-info span.

    After a game starts, the time moves inside an <a> element, so .text alone
    mixes in indicator/sr-only text and misses the link text.  This walks the
    span's children directly: it skips indicator and sr-only spans, collects
    direct text nodes and <a> link text, then normalises whitespace (including
    non-breaking spaces from &nbsp;).
    """
    chunks = []
    for child in span.children:
        if isinstance(child, Tag):
            child_classes = set(child.get('class') or [])
            if not child_classes & _EXCLUDED_SPAN_CLASSES:
                chunks.append(child.get_text())
        else:
            chunks.append(str(child))
    return ' '.join(''.join(chunks).replace('\xa0', ' ').split())

def parse_start_time(time_str, date_str):
    """Parse a time string like '4:15 PM PDT' into a timezone-aware datetime.
    Combining with date_str (YYYY-MM-DD) makes the result sortable across timezones."""
    time_parts = time_str.rsplit(' ', 1)  # ['4:15 PM', 'PDT'] or ['4:15 PM'] if no tz
    if len(time_parts) == 2 and time_parts[1] in _TZ_OFFSETS:
        time_part, tz_abbr = time_parts
        offset_hours = _TZ_OFFSETS[tz_abbr]
    else:
        time_part = time_str  # no recognised timezone — parse as-is, treat as UTC
        offset_hours = 0
    tz = datetime.timezone(datetime.timedelta(hours=offset_hours))
    try:
        naive = datetime.datetime.strptime(f"{date_str} {time_part}", '%Y-%m-%d %I:%M %p')
        return naive.replace(tzinfo=tz)
    except ValueError:
        return None

def moveplayer(date,player_id,position_old,position_new):
  global df  
  
  #Keep the dataframe synched so that logical operations can continue
  #Bench slots are an imaginary position and there can be an (infinite) number, so add rows as necessary
  if position_new=='Bench':
    df.loc[df[df['id']==player_id].index,'pos'] = 'Bench'
    new_row = pd.DataFrame([{'pos': position_old}])
    df = pd.concat([df, new_row], ignore_index=True)
    callajax(date, player_id, position_old, position_new)
    
  elif position_new in lineupPositions: #the new position has to be a valid position
    if df[df['id']==player_id][position_new].values[0]: #Make sure the person being moved is eligible to be moved into the specified slot
      #Make sure the spot the player is being moved to is available
      if df[df['pos'] == position_new]['id'].isnull().values.any(): #lengthy construct due to the fact there are multiple OF slots
        callajax(date, player_id, position_old, position_new)
        df.loc[df[df['id'] == player_id].index[0], 'pos'] = position_new
        df.loc[df[(df['pos'] == position_new) & (df['id'].isnull())].index[0], 'pos'] = position_old

  print(f"{position_old} -> {position_new}, {df[df['id'] == player_id]['name'].values[0]}")

def callajax(date, player_id, position_old, position_new):
  # Constructing the exact payload the FanGraphs API now expects
  ajax_payload = {
    "method": "saveChanges",
    "data[Date]": date,
    "data[Changes][0][PlayerID]": player_id,
    "data[Changes][0][OldPosition]": position_old,
    "data[Changes][0][NewPosition]": position_new,
    "data[Changes][0][IsPitcherVersionOfTwoWayPlayer]": "false",
    "data[VisibleSplit]": "season"
  }

  # Adding the required AJAX and origin headers
  headers = {
    'Origin': 'https://ottoneu.fangraphs.com',
    'Referer': f'https://ottoneu.fangraphs.com/{league_id}/setlineups',
    'X-Requested-With': 'XMLHttpRequest'
  }

  url = f"https://ottoneu.fangraphs.com/{league_id}/ajax/setlineups"

  print(f"Executing move: {position_old} -> {position_new} for Player ID {player_id}")
  ajax_response = session.post(url, data=ajax_payload, headers=headers)

  # Quick error check to ensure the post didn't bounce
  if ajax_response.status_code != 200:
    print(f"Warning: Move failed with status code {ajax_response.status_code}. Response: {ajax_response.text}")


# --- Authentication ---
login_url = "https://blogs.fangraphs.com/wp-login.php"

print("Step 1: Fetching login page to capture cookies and security nonces...")
get_response = session.get(login_url)
soup_login = BeautifulSoup(get_response.text, "html.parser")

# Dynamically scrape all hidden fields from the login form (this captures the nonce and testcookie)
payload = {}
login_form = soup_login.find('form', id='loginform')

if isinstance(login_form, Tag):
    for input_tag in login_form.find_all('input', type='hidden'):
        if not isinstance(input_tag, Tag):
            continue
        name = input_tag.get('name')
        value = input_tag.get('value')
        if name:
            payload[str(name)] = value

# Inject your credentials and redirect preferences into the payload
payload["log"] = os.getenv("OTTONEU_USERNAME")
payload["pwd"] = os.getenv("OTTONEU_PASSWORD")
payload["wp-submit"] = "Log In"
payload["redirect_to"] = f"https://ottoneu.fangraphs.com/{league_id}/setlineups"

print("Step 2: Submitting login payload...")
response = session.post(login_url, data=payload)

# Verification: If successful, the final URL should be on the ottoneu subdomain
if "ottoneu.fangraphs.com" in response.url:
    print("Successfully authenticated via WordPress login.")
else:
    print(f"Login failed. Current URL: {response.url}")

# --- Date Handling ---
today = target_date if target_date else datetime.datetime.today().strftime('%Y-%m-%d')

# --- Scraping ---
lineup_url = f"https://ottoneu.fangraphs.com/{league_id}/setlineups?date={today}"
if team_id:
    lineup_url += f"&team={team_id}"
response = session.get(lineup_url)
soup = BeautifulSoup(response.text, "html.parser")

#These are the positions that the script concerns itself with
lineupPositions = ["C","1B","2B","SS","3B","OF","MI","Util"]

#Build a dictionary that relates the above positions to integers that can later be sorted
priority = {position: rank for rank, position in enumerate(lineupPositions)}

df = pd.DataFrame(columns=pd.Index(["pos","locked","starting","gamescheduled","name","id","posCount"]+lineupPositions))

#There's a header bar that gets placed on the page only when you're logged in
if soup.find(id="team-switcher-menu"):
    
  batter_table = soup.find('table', attrs={'class': 'lineup-table batter'})
  parsed_players = []

  if isinstance(batter_table, Tag):
    for row in batter_table.select('tbody tr'):

      if row.find(True, {"style": True}):  # skip separator rows
        continue

      pos_td = row.find('td', {'data-position': True})
      if not isinstance(pos_td, Tag):
        continue

      pos = pos_td.get('data-position')
      if pos in ('Minors', 'IL'):
        continue

      player_data = {
        "pos": pos,
        "locked": 'locked' in (pos_td.get('class') or []),
        "name": None, "id": None, "handedness": None,
        "gamescheduled": False, "location": None, "start_time": None,
        "facing": None, "starting": None, "batting": None, "posCount": 0,
      }

      name_cell = row.find('td', {'class': 'player-name'})
      if not isinstance(name_cell, Tag) or 'empty_slot' in (name_cell.get('class') or []):
        parsed_players.append(player_data)
        continue

      player_data["name"] = name_cell.a.text.strip() if name_cell.a else None
      player_id_raw = pos_td.get('data-player-id')
      if player_id_raw:
        player_data["id"] = int(str(player_id_raw))
      bio_span = row.select_one('.lineup-player-bio .strong.tinytext')
      if bio_span:
        player_data["handedness"] = bio_span.text.split()[-1].strip()

      # Game info — parsed from e.g. "@ATL 4:15 PM PDT" or "ATL 7:05 PM EDT"
      game_info_span = row.find('span', {'class': 'lineup-game-info'})
      game_info_text = get_game_info_text(game_info_span) if isinstance(game_info_span, Tag) else '---'
      player_data["gamescheduled"] = game_info_text != '---'
      if game_info_text != '---':
        player_data["location"] = "AWAY" if game_info_text.startswith('@') else "HOME"
        tokens = game_info_text.lstrip('@').split(maxsplit=1)  # ['ATL', '4:15 PM PDT']
        player_data["start_time"] = parse_start_time(tokens[1], today) if len(tokens) > 1 else None

      # Opposing pitcher
      facing_span = row.select_one('.lineup-opponent-info .tinytext')
      if facing_span:
        player_data["facing"] = facing_span.text.strip()

      # Starting status and batting order position
      if row.select_one('.starting-indicator'):
        player_data["starting"] = True
        sr_span = row.select_one('.lineup-game-info .sr-only')
        if sr_span:
          player_data["batting"] = int(sr_span.text.split()[-1])
      elif row.select_one('.not-starting-indicator'):
        player_data["starting"] = False

      # Positional eligibility — Niv splits data-player-positions on / in the official JS
      positions_raw = pos_td.get('data-player-positions')
      if positions_raw:
        positions = str(positions_raw).split("/")
        for p in positions:
          player_data[p] = True
          player_data["posCount"] += 1
        if "2B" in positions or "SS" in positions:
          player_data["MI"] = True
          player_data["posCount"] += 1
        player_data["Util"] = True

      parsed_players.append(player_data)

  df = pd.DataFrame(parsed_players)

  # Move active lineup players to the bench if unlocked and either has no game or is explicitly not starting
  for index, row in df[df['id'].notna()].query("pos in @lineupPositions and not locked and (not gamescheduled or starting == False)").iterrows():
    moveplayer(today, row['id'], row['pos'], 'Bench')
  
  # --- Fill starting lineup slots ---

  # Flex positions that must wait until their primary counterparts are resolved first
  FLEX_PREREQS = {'MI': {'SS', '2B'}, 'Util': set(lineupPositions) - {'MI', 'Util'}}

  def matchup_is_favorable(hand, facing):
    """True when the batter has a platoon advantage against the opposing pitcher."""
    if pd.isna(hand) or pd.isna(facing):
      return False
    if hand == 'S':
      return True  # switch hitters always have a platoon advantage
    # facing is the raw value from .tinytext: 'R' or 'L'
    pitcher_hand = facing if facing in ('R', 'L') else None
    return hand != pitcher_hand if pitcher_hand else False

  fill: pd.Series = df[df['pos'].isin(lineupPositions) & df['id'].isnull()]['pos']
  resolved = []

  while not fill.empty:
    needs = set(fill.unique())

    # Defer flex slots until their primary positions are resolved (or proven unfillable)
    deferred = {flex for flex, prereqs in FLEX_PREREQS.items() if flex in needs and needs & prereqs}
    active_needs = [p for p in lineupPositions if p in needs - deferred]
    if not active_needs:  # only deferred slots remain — attempt them anyway
      active_needs = [p for p in lineupPositions if p in needs]

    eligible_cols = [p for p in active_needs if p in df.columns]
    if not eligible_cols:
      break

    eligible = df[eligible_cols].any(axis='columns')

    available = df[
      df['pos'].isin(lineupPositions + ['Bench']) &
      (df['starting'] != False) &
      (df['gamescheduled'] != False) &
      (df['locked'] != True) &
      eligible &
      ~df['pos'].isin(resolved)
    ]

    if available.empty:
      break

    # Scarcity heuristic: fill the position with fewest eligible candidates first
    counts = available[eligible_cols].sum().astype(int)
    counts = counts[counts > 0]
    if counts.empty:
      break
    pos = counts.idxmin()

    # Candidates: eligible for pos, not already occupying it
    candidates = available[(available[pos] == True) & (available['pos'] != pos)].copy()

    if candidates.empty:
      resolved.append(pos)
      fill = cast(pd.Series, fill.drop(fill[fill == pos].head(1).index))
      continue

    # Player selection priority:
    # 1. Util occupant first — moving them frees the flex slot for a bench player
    # 2. Bench before other lineup positions
    # 3. Batting order ascending (1 is highest priority), unknown batting order last
    # 4. Platoon advantage as final tiebreaker
    candidates['_source'] = candidates['pos'].map(
      lambda slot: 0 if slot == 'Util' else (1 if slot == 'Bench' else 2)
    )
    candidates['_favorable'] = candidates.apply(
      lambda r: matchup_is_favorable(r.get('handedness'), r.get('facing')), axis=1
    )
    candidates = candidates.sort_values(
      by=['_source', 'batting', '_favorable'],
      ascending=[True, True, False],
      na_position='last'
    )

    tomove = candidates.iloc[0]
    from_pos = tomove['pos']

    if from_pos == 'Util':
      # Util opens up — swap it into fill in place of pos
      fill = cast(pd.Series, fill.drop(fill[fill == pos].head(1).index))
      fill = pd.concat([fill, pd.Series(['Util'])], ignore_index=True)
    elif from_pos in lineupPositions:
      # Pulling from another lineup slot — backfill that position
      fill = pd.concat([fill, pd.Series([from_pos])], ignore_index=True)

    moveplayer(today, tomove['id'], from_pos, pos)

    resolved.append(pos)
    fill = cast(pd.Series, fill.drop(fill[fill == pos].head(1).index))
    
  # --- Pitcher Table ---
  pitcherPositions = ["SP", "RP"]
  # Pitch count columns represent the last 5 days in reverse chronological order (most recent first)
  pc_cols = ["PC_1", "PC_2", "PC_3", "PC_4", "PC_5"]

  pitcher_table = soup.find('table', attrs={'class': 'lineup-table pitcher'})
  parsed_pitchers = []

  if isinstance(pitcher_table, Tag):
    for row in pitcher_table.select('tbody tr'):

      if row.find(True, {"style": True}):  # skip separator rows (same pattern as batter table)
        continue

      pos_td = row.find('td', {'data-position': True})
      if not isinstance(pos_td, Tag):
        continue

      pos = pos_td.get('data-position')
      if pos not in pitcherPositions + ['Bench']:
        continue

      pitcher_data: dict[str, Any] = {col: None for col in ["id", "pos", "locked", "gamescheduled", "Name", "SP", "RP", "Starting", "Following", "Location", "Opponent", "Start Time", "P/IP"] + pc_cols}
      pitcher_data["pos"] = pos
      pitcher_data["locked"] = 'locked' in (pos_td.get('class') or [])
      pitcher_data["SP"] = False
      pitcher_data["RP"] = False
      pitcher_data["Starting"] = False
      pitcher_data["Following"] = False
      pitcher_data["gamescheduled"] = False

      name_cell = row.find('td', {'class': 'player-name'})
      if not isinstance(name_cell, Tag) or 'empty_slot' in (name_cell.get('class') or []):
        parsed_pitchers.append(pitcher_data)
        continue

      pitcher_data["Name"] = name_cell.a.text.strip() if name_cell.a else None
      player_id_raw = pos_td.get('data-player-id')
      if player_id_raw:
        pitcher_data["id"] = int(str(player_id_raw))

      # Positional eligibility (SP / RP)
      positions_raw = pos_td.get('data-player-positions')
      if positions_raw:
        for p in str(positions_raw).split("/"):
          if p in ["SP", "RP"]:
            pitcher_data[p] = True

      # Starting / Following status
      if row.select_one('.starting-indicator'):
        pitcher_data["Starting"] = True
      elif row.select_one('.not-starting-indicator'):
        pitcher_data["Starting"] = False

      if row.select_one('.following-indicator'):
        pitcher_data["Following"] = True

      # Location, Opponent, Start Time, and game-scheduled flag
      game_info_span = row.find('span', {'class': 'lineup-game-info'})
      game_info_text = get_game_info_text(game_info_span) if isinstance(game_info_span, Tag) else '---'
      pitcher_data["gamescheduled"] = game_info_text != '---'
      if game_info_text != '---':
        if game_info_text.startswith('@'):
          pitcher_data["Location"] = "AWAY"
          game_info_text = game_info_text[1:]  # strip the leading '@'
        else:
          pitcher_data["Location"] = "HOME"
        parts = game_info_text.split(maxsplit=1)
        pitcher_data["Opponent"] = parts[0] if parts else None
        pitcher_data["Start Time"] = parts[1] if len(parts) > 1 else None

      # Last 5 days' pitch counts — day_1 is most recent, day_5 is five days ago
      pc_container = row.select_one('td.pitch_count_container .pitch_count_last_five_days')
      if isinstance(pc_container, Tag):
        for j, col in enumerate(pc_cols):
          pc_td = pc_container.find('td', class_=f'day_{j + 1}')
          if isinstance(pc_td, Tag):
            raw = pc_td.text.strip()
            pitcher_data[col] = int(raw) if raw.isdigit() else None

      # P/IP — the <td> immediately after the pitch_count_container (no class, always visible)
      pip_td = row.select_one('td.pitch_count_container + td')
      if pip_td:
        raw_pip = pip_td.text.strip()
        pitcher_data["P/IP"] = float(raw_pip) if raw_pip else None

      parsed_pitchers.append(pitcher_data)

  df_pitchers = pd.DataFrame(parsed_pitchers, columns=pd.Index(["id", "pos", "locked", "gamescheduled", "Name", "SP", "RP", "Starting", "Following", "Location", "Opponent", "Start Time", "P/IP"] + pc_cols))

  # Load today's hot-offense teams; fetch from FanGraphs if not yet cached for today
  try:
    with open('hot_offenses.json', 'r') as f:
      hot_offenses_data = json.load(f)
  except (FileNotFoundError, json.JSONDecodeError):
    hot_offenses_data = {}

  if today not in hot_offenses_data:
    print("Hot offense data not cached for today — fetching from FanGraphs...")
    hot_offense_teams = return_hot_offenses()
  else:
    hot_offense_teams = hot_offenses_data[today]

  # --- Bench out pitchers in the wrong slot ---

  # SP slot: bench anyone not confirmed as today's starter (not-starting, followers, no-game)
  for _, p_row in df_pitchers[df_pitchers['id'].notna()].query(
    "pos == 'SP' and not locked and Starting != True"
  ).iterrows():
    callajax(today, p_row['id'], 'SP', 'Bench')
    df_pitchers.loc[df_pitchers['id'] == p_row['id'], 'pos'] = 'Bench'
    df_pitchers = pd.concat([df_pitchers, pd.DataFrame([{'pos': 'SP'}])], ignore_index=True)
    print(f"SP -> Bench, {p_row['Name']}")

  # RP slot: bench confirmed starters (they need an SP slot) and fatigued relievers (pitched 2 days in a row)
  fatigued_mask = (df_pitchers['PC_1'].fillna(0) > 0) & (df_pitchers['PC_2'].fillna(0) > 0)
  for _, p_row in df_pitchers[
    df_pitchers['id'].notna() &
    (df_pitchers['pos'] == 'RP') &
    (df_pitchers['locked'] != True) &
    ((df_pitchers['Starting'] == True) | fatigued_mask)
  ].iterrows():
    callajax(today, p_row['id'], 'RP', 'Bench')
    df_pitchers.loc[df_pitchers['id'] == p_row['id'], 'pos'] = 'Bench'
    df_pitchers = pd.concat([df_pitchers, pd.DataFrame([{'pos': 'RP'}])], ignore_index=True)
    print(f"RP -> Bench, {p_row['Name']}")

  # --- Fill pitcher lineup slots ---

  # Fill SP slots: confirmed starters with SP eligibility, pulled from bench
  while df_pitchers[(df_pitchers['pos'] == 'SP') & df_pitchers['id'].isnull()].shape[0] > 0:
    sp_candidates = df_pitchers[
      (df_pitchers['SP'] == True) &
      (df_pitchers['Starting'] == True) &
      (df_pitchers['gamescheduled'] == True) &
      (df_pitchers['locked'] != True) &
      (df_pitchers['pos'] == 'Bench') &
      ~df_pitchers['Opponent'].isin(hot_offense_teams)
    ]
    if sp_candidates.empty:
      break
    tomove = sp_candidates.iloc[0]
    callajax(today, tomove['id'], 'Bench', 'SP')
    df_pitchers.loc[df_pitchers[df_pitchers['id'] == tomove['id']].index[0], 'pos'] = 'SP'
    df_pitchers.loc[df_pitchers[(df_pitchers['pos'] == 'SP') & df_pitchers['id'].isnull()].index[0], 'pos'] = 'Bench'
    print(f"Bench -> SP, {tomove['Name']}")

  # Fill RP slots: RP-eligible, not a confirmed starter, not fatigued; followers preferred, then highest P/IP
  while df_pitchers[(df_pitchers['pos'] == 'RP') & df_pitchers['id'].isnull()].shape[0] > 0:
    fatigued = (df_pitchers['PC_1'].fillna(0) > 0) & (df_pitchers['PC_2'].fillna(0) > 0)
    rp_candidates = df_pitchers[
      (df_pitchers['RP'] == True) &
      (df_pitchers['Starting'] != True) &
      (df_pitchers['gamescheduled'] == True) &
      (df_pitchers['locked'] != True) &
      ~fatigued &
      (df_pitchers['pos'] == 'Bench')
    ].copy()
    if rp_candidates.empty:
      break
    rp_candidates = rp_candidates.sort_values(
      by=['Following', 'P/IP'], ascending=[False, False], na_position='last'
    )
    tomove = rp_candidates.iloc[0]
    callajax(today, tomove['id'], 'Bench', 'RP')
    df_pitchers.loc[df_pitchers[df_pitchers['id'] == tomove['id']].index[0], 'pos'] = 'RP'
    df_pitchers.loc[df_pitchers[(df_pitchers['pos'] == 'RP') & df_pitchers['id'].isnull()].index[0], 'pos'] = 'Bench'
    print(f"Bench -> RP, {tomove['Name']}")

else:
  print("Authentication failed. Please check your .env file.")