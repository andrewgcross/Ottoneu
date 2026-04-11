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
from bs4 import BeautifulSoup
import datetime
import pandas as pd
from dotenv import load_dotenv
import os

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

def parse_start_time(time_str, date_str):
    """Parse a time string like '4:15 PM PDT' into a timezone-aware datetime.
    Combining with date_str (YYYY-MM-DD) makes the result sortable across timezones."""
    parts = time_str.rsplit(' ', 1)  # ['4:15 PM', 'PDT']
    if len(parts) != 2:
        return None
    time_part, tz_abbr = parts
    offset_hours = _TZ_OFFSETS.get(tz_abbr, 0)
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
  payload = {
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
  response = session.post(url, data=payload, headers=headers)

  # Quick error check to ensure the post didn't bounce
  if response.status_code != 200:
    print(f"Warning: Move failed with status code {response.status_code}. Response: {response.text}")


# --- Authentication ---
login_url = "https://blogs.fangraphs.com/wp-login.php"

print("Step 1: Fetching login page to capture cookies and security nonces...")
get_response = session.get(login_url)
soup_login = BeautifulSoup(get_response.text, "html.parser")

# Dynamically scrape all hidden fields from the login form (this captures the nonce and testcookie)
payload = {}
login_form = soup_login.find('form', id='loginform')

if login_form:
    for input_tag in login_form.find_all('input', type='hidden'):
        name = input_tag.get('name')
        value = input_tag.get('value')
        if name:
            payload[name] = value

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

df = pd.DataFrame(columns=["pos","locked","starting","gamescheduled","name","id","posCount"]+lineupPositions)

#There's a header bar that gets placed on the page only when you're logged in
if soup.find(id="team-switcher-menu"):
    
  batter_table = soup.find('table', attrs={'class': 'lineup-table batter'})
  parsed_players = []

  if batter_table:
    for row in batter_table.select('tbody tr'):

      if row.find(True, {"style": True}):  # skip separator rows
        continue

      pos_td = row.find('td', {'data-position': True})
      if not pos_td:
        continue

      pos = pos_td.get('data-position')
      if pos in ('Minors', 'IL'):
        continue

      player_data = {
        "pos": pos,
        "locked": bool(row.find(True, {'class': 'locked'})),
        "name": None, "id": None, "handedness": None,
        "gamescheduled": False, "location": None, "start_time": None,
        "facing": None, "starting": None, "batting": None, "posCount": 0,
      }

      name_cell = row.find('td', {'class': 'player-name'})
      if not (name_cell and name_cell.a):
        parsed_players.append(player_data)
        continue

      player_data["name"] = name_cell.a.text.strip()
      player_data["id"] = int(row.find('td', {'data-player-id': True})['data-player-id'])
      player_data["handedness"] = row.select_one('.lineup-player-bio .strong.tinytext').text.split()[-1].strip()

      # Game info — parsed from e.g. "@ATL 4:15 PM PDT" or "ATL 7:05 PM EDT"
      game_info_span = row.find('span', {'class': 'lineup-game-info'})
      game_info_text = game_info_span.text.strip() if game_info_span else '---'
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
      positions_td = row.find('td', {'data-player-positions': True})
      if positions_td:
        positions = positions_td['data-player-positions'].split("/")
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
  
  #Move players into the starting lineup
  #Determine which slots need to be filled, in the order specified by the lineupPositions variable above
  fill = df[df['pos'].isin(lineupPositions) & df['id'].isnull()]['pos']
  
  resolved = []
  while True: 
    needs = fill.unique()

    # eligible: player can fill at least one of the still-needed positions
    # not_resolved: exclude players already sitting in a position that has been filled,
    #               so a rare-position player (e.g. C) isn't reused to fill OF
    eligible = df[needs].any(axis='columns')

    available = df[
      df['pos'].isin(lineupPositions + ['Bench']) &
      (df['starting'] != False) &
      (df['gamescheduled'] != False) &
      (df['locked'] != True) &
      eligible &
      ~df['pos'].isin(resolved)
    ]
    
    if not available.empty:
      #Move the eligible players into the needed spot, but make sure to identify when there's no further moving around possible
      counts = available.count()[fill.unique()].sort_values(ascending=True)
      pos = counts.index[0]

      if counts[pos]: #very real possibility there won't be any available players to fill in the needs
        
        #Someone taking up the utility spot should be the first person moved
        if len(available[(available[pos]==True) & (available['pos']=='Util')]):
          moveplayer(today,available[available['pos']=='Util']['id'].values[0],'Util',pos)
          fill = fill.drop(fill[fill==pos].head(1).index)
          fill = pd.concat([fill, pd.Series(['Util'])], ignore_index=True)

        elif len(available[(available[pos]==True) & (available['pos']!=pos)]):
          #this is where advanced logic will be placed to pick who exactly should be moved into a slot
          #Don't fill a flex spot (UTIL or MI) with someone that's already in a rigid lineup position
          if pos in ['Util']:
            if not available[(available['pos']=='Bench')].empty:
              tomove = available[(available['pos']=='Bench')].sort_values('posCount').head(1)
              moveplayer(today,tomove['id'].values[0],tomove['pos'].values[0],pos)
          else:
            tomove = available[(available[pos]==True) & (available['pos']!=pos)].sort_values(by=['pos','posCount'], ascending=[False,True]).head(1)
            
            if tomove['pos'].isin(lineupPositions).values[0]: #if you take a guy out of the lineup to fill a more "rare" position, be sure to try ot backfill his position
              fill = pd.concat([fill, pd.Series([tomove['pos'].values[0]])], ignore_index=True)
              
            moveplayer(today,tomove['id'].values[0],tomove['pos'].values[0],pos)
    else:
      break

    resolved.extend([pos])
    fill=fill.drop(fill[fill==pos].head(1).index)
    
    if len(fill)==0:
      break
    
  # --- Pitcher Table ---
  pitcherPositions = ["SP", "RP"]
  # Pitch count columns represent the last 5 days in reverse chronological order (most recent first)
  pc_cols = ["PC_1", "PC_2", "PC_3", "PC_4", "PC_5"]

  pitcher_table = soup.find('table', attrs={'class': 'lineup-table pitcher'})
  parsed_pitchers = []

  if pitcher_table:
    for row in pitcher_table.select('tbody tr'):

      if row.find(True, {"style": True}):  # skip separator rows (same pattern as batter table)
        continue

      pos_td = row.find('td', {'data-position': True})
      if not pos_td:
        continue

      pos = pos_td.get('data-position')
      if pos not in pitcherPositions + ['Bench']:
        continue

      pitcher_data = {col: None for col in ["pos", "Name", "SP", "RP", "Starting", "Following", "Location", "Opponent", "Start Time"] + pc_cols}
      pitcher_data["pos"] = pos
      pitcher_data["SP"] = False
      pitcher_data["RP"] = False
      pitcher_data["Starting"] = False
      pitcher_data["Following"] = False

      name_cell = row.find('td', {'class': 'player-name'})
      if not (name_cell and name_cell.a):
        parsed_pitchers.append(pitcher_data)
        continue

      pitcher_data["Name"] = name_cell.a.text.strip()

      # Positional eligibility (SP / RP)
      positions_td = row.find('td', {'data-player-positions': True})
      if positions_td:
        for p in positions_td['data-player-positions'].split("/"):
          if p in ["SP", "RP"]:
            pitcher_data[p] = True

      # Starting / Following status
      if row.select_one('.starting-indicator'):
        pitcher_data["Starting"] = True
      elif row.select_one('.not-starting-indicator'):
        pitcher_data["Starting"] = False

      if row.select_one('.following-indicator'):
        pitcher_data["Following"] = True

      # Location, Opponent, and Start Time — parsed from e.g. "@ATL 4:15 PM PDT" or "ATL 7:05 PM EDT"
      game_info_span = row.find('span', {'class': 'lineup-game-info'})
      game_info_text = game_info_span.text.strip() if game_info_span else '---'
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
      pc_container = row.find(class_='pitch_count_last_five_days')
      if pc_container:
        for j, col in enumerate(pc_cols):
          pc_td = pc_container.find('td', class_=f'day_{j + 1}')
          if pc_td:
            raw = pc_td.text.strip()
            pitcher_data[col] = int(raw) if raw.isdigit() else None

      parsed_pitchers.append(pitcher_data)

  df_pitchers = pd.DataFrame(parsed_pitchers, columns=["pos", "Name", "SP", "RP", "Starting", "Following", "Location", "Opponent", "Start Time"] + pc_cols)

else:
  print("Authentication failed. Please check your .env file.")