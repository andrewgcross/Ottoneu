# -*- coding: utf-8 -*-

"""
Ottoneu Auto Roster Set
Andrew Cross
http://www.agcross.com
v2.0

After entering your login credentials, and establishing the lineup you'd like to
prioritize, this script can be run to set your lineup depending on which players
are starting. It's best run automatically with a CHRON job.

Updated to Python 3.9.25 to be compatible with my Synology
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

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://blogs.fangraphs.com/wp-login.php'
})

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
today = datetime.datetime.today().strftime('%Y-%m-%d')

# --- Scraping ---
response = session.get(f"https://ottoneu.fangraphs.com/{league_id}/setlineups?date={today}")
soup = BeautifulSoup(response.text, "html.parser")

#These are the positions that the script concerns itself with
lineupPositions = ["C","1B","2B","SS","3B","OF","MI","Util"]

#Build a dictionary that relates the above positions to integers that can later be sorted
priority = {position: rank for rank, position in enumerate(lineupPositions)}

df = pd.DataFrame(columns=["pos","locked","starting","gamescheduled","name","id","posCount"]+lineupPositions)

#There's a header bar that gets placed on the page only when you're logged in
if soup.find(id="team-switcher-menu"):
    
  table = soup.find('table', attrs={'class':'lineup-table batter'}) #Only mess with batters
  players = table.select('tbody tr') #Grab the rows
  
  for player in enumerate(players):
    
    if not player[1].find(True,{"style":True}): #there's a table row between the starts and the bench that doesn't include any player info, and simply seperates the two sections
    
      df.loc[player[0],"pos"] = player[1].find('td',{'data-position':True}).text #position
      
      if player[1].find(True,{'class':'locked'}):
        df.loc[player[0],"locked"] = True
        
      if player[1].find('td',{'class':'player-name'}).text != 'Empty': #if there's someone assigned to the slot
        df.loc[player[0],"name"] = player[1].find('td',{'class':'player-name'}).a.text
        df.loc[player[0],"id"] = int(player[1].find('td',{'data-player-id':True})['data-player-id'])
      
        if player[1].find('span',{'class':'starting-indicator'}):
          df.loc[player[0],"starting"] = True
        elif player[1].find('span',{'class':'not-starting-indicator'}):
          df.loc[player[0],"starting"] = False
          
        if player[1].find_all('td')[2].text.strip() == '---': #Opponent is the 3rd column
          df.loc[player[0],"gamescheduled"] = False
        else:
          df.loc[player[0], "gamescheduled"] = True
      
        #Determine positional eligibility        
        #In the official JavaScript, Niv splits the data-player-positions container on / and uses that
        df.loc[player[0],"posCount"] = 1
        for pos in player[1].find('td',{'data-player-positions':True})['data-player-positions'].split("/"):
          df.loc[player[0],pos] = True
          if pos in ["SS","2B"]:
            df.loc[player[0],"MI"] = True
            df.loc[player[0],"posCount"] = df.loc[player[0],"posCount"] + 1

          df.loc[player[0],"posCount"] = df.loc[player[0],"posCount"] + 1
        df.loc[player[0],'Util'] = True

  # --- Resolve NaN values for logical filtering ---
  # If a player isn't explicitly locked, they are unlocked (False)
  #df['locked'] = df['locked'].fillna(False)

  # If there is no starting indicator, treat them as not starting (False)
  #df['starting'] = df['starting'].fillna(False)

  # If the opponent column wasn't '---', it means they DO have a game (True)
  #df['gamescheduled'] = df['gamescheduled'].fillna(True)
  
  #Testing purposes
  #df.loc[4,'starting'] = False
  #df.loc[6,'starting'] = False
  #df.loc[10,'starting'] = False
  
  #If there's anyone in the starting lineup, that's not starting (or who doesn't have a game scheduled), and hasn't yet been locked, move them to the bench
  for index, row in df[(df['pos'].isin(lineupPositions)) & (df['locked']!=True) & (~df['name'].isnull()) & ((df['starting']!=True) | (df['gamescheduled']!=True))].iterrows():
    moveplayer(today,row['id'],row['pos'],'Bench')
  
  #Move players into the starting lineup
  #Determine which slots need to be filled, in the order specified by the lineupPositions variable above
  fill = df[df['pos'].isin(lineupPositions) & df['id'].isnull()]['pos']
  
  resolved = []
  while True: 
    #Can't use a pandas query select statement since the 1B, 2B, 3B aren't valid python expressions (they start with a numeral)
    #http://stackoverflow.com/questions/27787264/pandas-query-throws-error-when-column-name-starts-with-a-number
    first = True
    for need in fill.unique():
        if first:
            first = False
            filt = "((df['%s']==True)" % need
        else:
            filt = filt + " | (df['%s']==True)" % need
    filt = filt + ")" #the OR statements above need to be all grouped together
    
    #Since the order by which players are assigned positions is based on "rarity", one a more "rare" position has been filled (C, for example)
    #you don't want to use that person to fill an OF slot, so exclude them from being available
    if len(resolved):
      for resolve in resolved:
          filt = filt + " & (df['pos']!='%s')" % resolve
          
    #These are the players available to fill empty roster spots
    available = df[(df['pos'].isin(lineupPositions+['Bench'])) & (df['starting']!=False) & (df['gamescheduled']!=False) & (df['locked']!=True) & eval(filt)]
    
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
    
else:
  print("Authentication failed. Please check your .env file.")