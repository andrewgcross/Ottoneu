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
import urllib2 
import mechanize
from bs4 import BeautifulSoup
import pandas as pd
pd.set_option('expand_frame_repr', False) #for testing

# Browser 
br = mechanize.Browser() 

# Enable cookie support for urllib2 
cookiejar = cookielib.LWPCookieJar() 
br.set_cookiejar(cookiejar) 

# Broser options 
br.set_handle_equiv(True)
br.set_handle_gzip(True)
br.set_handle_redirect(True)
br.set_handle_referer(True)
br.set_handle_robots(False)

br.set_handle_refresh( mechanize._http.HTTPRefreshProcessor(), max_time = 1 ) 
br.addheaders = [ ( 'User-agent', 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Gecko/2008071615 Fedora/3.0.1-1.fc9 Firefox/3.0.1' ) ] 

# Authentication
br.open("http://www.fangraphs.com/blogs/wp-login.php?redirect_to=http%3A//www.fangraphs.com/redirect.aspx?s=ottoneu.fangraphs.com") 
br.select_form(name="loginform") 
br["log"] = "" #"log" corresponds to the name tag on the form
br["pwd"] = ""
res = br.submit() 


url = br.open("https://ottoneu.fangraphs.com/90/setlineups") 
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

 






      
#Made it all the way to the ajax call at line 74 on ottoneuSetLineups.js