# -*- coding: utf-8 -*-

"""
Ottoneu Auto Roster Set
Andrew Cross
http://www.agcross.com

After entering your login credentials, and establishing the lineup you'd like to
prioritize, this script can be run to set your lineup depending on which players
are starting. It's best run automatically with a CHRON job.

Made to be compatible with pandas 14.1-2
"""

import cookielib 
import urllib
import urllib2 
import mechanize
from bs4 import BeautifulSoup
import datetime
import pandas as pd
import credentials as crd

def movePlayer(date,PlayerID,OldPosition,NewPosition):
  global df  
  
  #Keep the dataframe synched so that logical operations can continue
  #Bench slots are an imaginary position and there can be an (infinite) number, so add rows as necessary
  if NewPosition=='Bench':
    df.loc[df[df['id']==PlayerID].index,'pos'] = 'Bench'
    df = df.append(pd.Series(), ignore_index=True)
    df.loc[df.tail(1).index,'pos'] = OldPosition   
    callAjax(date,PlayerID,OldPosition,NewPosition)
    
  elif NewPosition in lineupPositions: #the new position has to be a valid position
    
    if df[df['id']==PlayerID][NewPosition].values[0]: #Make sure the person being moved is eligible to be moved into the specified slot
      
      #Make sure the spot the player is being moved to is available
      if df[df['pos']==NewPosition]['id'].isnull().values.any(): #lengthy construct due to the fact there are multiple OF slots
        callAjax(date,PlayerID,OldPosition,NewPosition)
        df.loc[df[df['id']==PlayerID].index[0],'pos'] = NewPosition
        df.loc[df[(df['pos']==NewPosition) & (df['id'].isnull())].index[0],'pos'] = OldPosition
      else: #this shouldn't be used, as previous logic should be dictating whether a move-to position is already filled or not
        callAjax(date,df[df['pos']==NewPosition].head(1)['id'].values[0],NewPosition,'Bench')        
        callAjax(date,PlayerID,OldPosition,NewPosition)
        
  print "%s -> %s, %s" % (OldPosition, NewPosition, df[df['id']==PlayerID]['name'].values[0])

def callAjax(date,PlayerID,OldPosition,NewPosition):  
  #The format the server is looking for is an array notation that I can't figure out how to efficiently convert to from a python dictionary
  data = "method=saveChanges&data[Date]=%s&data[Changes][0][PlayerID]=%s&data[Changes][0][OldPosition]=%s&data[Changes][0][NewPosition]=%s" % (date,PlayerID,OldPosition,NewPosition)
  data = urllib.quote(data,safe="=&")
  br.open("https://ottoneu.fangraphs.com/90/ajax/setlineups",data)  

   
pd.set_option('expand_frame_repr', False) #for testing

# Browser 
br = mechanize.Browser() 

# Enable cookie support for urllib2 
cookiejar = cookielib.LWPCookieJar() 
br.set_cookiejar(cookiejar) 

# Browser options 
br.set_handle_equiv(True)
br.set_handle_gzip(True)
br.set_handle_redirect(True)
br.set_handle_referer(True)
br.set_handle_robots(False)

br.set_handle_refresh( mechanize._http.HTTPRefreshProcessor(), max_time = 1 ) 
br.addheaders = [ ( 'User-agent', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36' ) ] 

# Authentication
br.open("http://www.fangraphs.com/blogs/wp-login.php?redirect_to=http%3A//www.fangraphs.com/redirect.aspx?s=ottoneu.fangraphs.com") 
br.select_form(name="loginform") 
br["log"] = crd.credentials['user'] #"log" corresponds to the name tag on the form
br["pwd"] = crd.credentials['passwd']
res = br.submit() 

today = datetime.datetime.today().strftime('%Y-%m-%d') #'2016-08-21'
url = br.open("https://ottoneu.fangraphs.com/90/setlineups?date=%s" % today) 
page = url.read()
soup = BeautifulSoup(page, "html.parser") 

#These are the positions that the script concerns itself with
lineupPositions = ["C","1B","2B","SS","MI","3B","OF","Util"]
df = pd.DataFrame(columns=["pos","locked","starting","gamescheduled","name","id","posCount"]+lineupPositions)

#There's a header bar that gets placed on the page only when you're logged in
if soup.find(id="team-switcher-menu"):
    
  table = soup.find('table', attrs={'class':'lineup-table batter'}) #Only mess with batters
  players = table.find_all('tr')[2:] #The first two table rows will always be the two header lines
  
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
          
        if player[1].find_all('td')[3].text == '---': #Opponent is always the 4th column
          df.loc[player[0],"gamescheduled"] = False
      
        #Determine positional eligibility        
        #In the official javascript, Niv splits the data-player-positions container on / and uses that
        df.loc[player[0],"posCount"] = 1
        for pos in player[1].find('td',{'data-player-positions':True})['data-player-positions'].split("/"):
          df.loc[player[0],pos] = True
          if pos in ["SS","2B"]:
            df.loc[player[0],"MI"] = True
            df.loc[player[0],"posCount"] = df.loc[player[0],"posCount"] + 1

          df.loc[player[0],"posCount"] = df.loc[player[0],"posCount"] + 1
        df.loc[player[0],'Util'] = True
  
  #Testing purposes
  #df.loc[4,'starting'] = False
  #df.loc[6,'starting'] = False
  #df.loc[10,'starting'] = False
  
  #If there's anyone in the starting lineup, that's not starting (or who doesn't have a game scheduled), and hasn't yet been locked, move them to the bench
  for index, row in df[(df['pos'].isin(lineupPositions)) & (df['locked']!=True) & (~df['name'].isnull()) & ((df['starting']==False) | (df['gamescheduled']==False))].iterrows():
    movePlayer(today,row['id'],row['pos'],'Bench')    
  
  #Move players into the starting lineup
  #First determine which slots need to be filled
  fill = df[df['pos'].isin(lineupPositions) & df['id'].isnull()]['pos']
  
  while True: 
    #Can't use a pandas query select statement since the 1B, 2B, 3B aren't valid python expressions (they start with a numeral)
    #http://stackoverflow.com/questions/27787264/pandas-query-throws-error-when-column-name-starts-with-a-number
    first = True
    for need in fill.unique():
        if first:
            first = False
            filt = "(df['%s']==True)" % need
        else:
            filt = filt + " | (df['%s']==True)" % need
    
    #These are the bench players that can fill empty roster spots
    #available = df[(df['pos']=='Bench') & ~(df['starting']==False) & ~(df['gamescheduled']==False) & ~(df['locked']==True) & (eval(filt))]
    available = df[(df['pos'].isin(lineupPositions+['Bench'])) & ~(df['starting']==False) & ~(df['gamescheduled']==False) & ~(df['locked']==True) & (eval(filt))]
    
    if not available.empty:
      #Move the eligible players into the needed spot, but make sure to identify when there's no further moving around possible
      pos = available.count()[fill.unique()].order(ascending=True).index[0]
      if available.count()[pos]: #very real possibility there won't be any available players to fill in the needs
        
        #Someone taking up the utility spot shoud be the first person moved      
        if len(available[(available[pos]==True) & (available['pos']=='Util')]):
          movePlayer(today,available[available['pos']=='Util']['id'].values[0],'Util',pos)
          fill = fill.drop(fill[fill==pos].head(1).index)
          fill = fill.append(pd.Series(['Util']))
        elif len(available[(available[pos]==True) & (available['pos']!=pos)]):
  
          #this is where advanced logic will be placed to pick you exactly should be moved into a slot        
          if pos=='Util':
            tomove = available[(available['pos']=='Bench')].sort('posCount').head(1)
          else:
            tomove = available[(available[pos]==True) & (available['pos']!=pos)].sort(columns=['pos','posCount'], ascending=[False,True]).head(1)
          movePlayer(today,tomove['id'].values[0],tomove['pos'].values[0],pos)
          fill=fill.drop(fill[fill==pos].head(1).index)
      else:
        fill=fill.drop(fill[fill==pos].head(1).index)
    else:
      break
    
    if len(fill)==0:
      break
    
else:
  print "Was not able to successfully log in. Check that credentials are properly entered."