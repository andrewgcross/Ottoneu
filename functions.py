from bs4 import BeautifulSoup
from urllib import urlopen
import pandas as pd

def tabletopandas(table):
  #Converts a beautifulsoup table to a pandas dataframe for easier post-processing
  header = [th.text for th in table.find('thead').select('th')]
  rows   = [[td.text for td in row.select('td')] for row in table.findAll('tr')[1:]] #first row is always the header
             
  return pd.DataFrame(data=rows, columns=header)

class player(object):
  
  def __init__(self, leagueID, playerID):
    self.leagueID = leagueID
    self.playerID = playerID
    self.scrape()
    
  def scrape(self):
    #Scrapes the player's page for the specified league
    url = 'https://ottoneu.fangraphs.com/%i/playercard?id=%i' % (self.leagueID, self.playerID)
    page = urlopen(url)
    soup = BeautifulSoup(page)
    
    #Status box is one of the first pieces of information available on the page
    #h3 array contains [Birthdate, positions, next year projected position, current situation]
    self.bioStatus = soup.find('div', attrs={'id': 'bio-and-status'})
    
    #Use the Last 10 MLB games text as the identifier for the subsequent table
    last10 = soup.find('h2',text='Last 10 MLB Games').findNext('table')
    last10 = tabletopandas(last10)
    last10 = last10.iloc[:-1] #the last row includes the merged 'totals' cell
    
    #The table is read as text, so convert to numeric as necessary
    last10['Points'] = last10['Points'].astype(float)
    last10['PA'] = last10['PA'].astype(int)
    self.last10 = last10
    
  def PPPA(self,PA):
    #Returns the points per plate appearance over the last specified number of appearances
    return self.last10['Points'][:PA].sum()/self.last10['PA'][:PA].sum()

      
    
test = player(90,2933)