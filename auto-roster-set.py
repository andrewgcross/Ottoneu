# -*- coding: utf-8 -*-

"""
Ottoneu Auto Roster Set
Andrew Cross
http://www.agcross.com

After entering your login credentials, and establishing the lineup you'd like to
prioritize, this script can be run to set your lineup depending on which players
are starting. It's best run automatically with a CHRON job.

The script will only consider benched position players as being available to be moved into a starting slot
"""

import cookielib 
import urllib
import urllib2 
import mechanize
from bs4 import BeautifulSoup
import datetime
import pandas as pd
import credentials as crd

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

today = datetime.datetime.today().strftime('%Y-%m-%d')
url = br.open("https://ottoneu.fangraphs.com/90/setlineups?date=%s" % ('2016-07-06'))#today) 
page = url.read()
soup = BeautifulSoup(page, "html.parser") 

#These are the positions that the script concerns itself with
lineupPositions = ["C","1B","2B","SS","MI","3B","OF","Util"]
df = pd.DataFrame(columns=["pos","locked","starting","name","id"]+lineupPositions)


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
          df.loc[player[0],"id"] = player[1].find('td',{'data-player-id':True})['data-player-id']
        
          if player[1].find('span',{'class':'starting-indicator'}):
            df.loc[player[0],"starting"] = True
          elif player[1].find('span',{'class':'not-starting-indicator'}):
            df.loc[player[0],"starting"] = False        
        
          #Determine positional eligibility        
          #In the official javascript, Niv splits the data-player-positions container on / and uses that 
          for pos in player[1].find('td',{'data-player-positions':True})['data-player-positions'].split("/"):
            df.loc[player[0],pos] = True



#After the page has been scraped, you'll need to institute your logic for moving players around
def movePlayer(date,PlayerID,OldPosition,NewPosition):
  #The format the server is looking for is an array notation that I can't figure out how to efficiently convert to from a python dictionary
  data = "method=saveChanges&data[Date]=%s&data[Changes][0][PlayerID]=%s&data[Changes][0][OldPosition]=%s&data[Changes][0][NewPosition]=%s" % (date,PlayerID,OldPosition,NewPosition)
  data = urllib.quote(data,safe="=&")
  br.open("https://ottoneu.fangraphs.com/90/ajax/setlineups",data)

df.loc[0,'starting'] = False
df.loc[6,'starting'] = False
df.loc[10,'starting'] = False

#If there's anyone in the starting lineup that's that's not starting, move them
for index, row in df[(df['pos'].isin(lineupPositions)) & (df['starting']==False) &(df['locked']!=True)].iterrows():
  movePlayer(today,row['id'],row['pos'],'Bench')