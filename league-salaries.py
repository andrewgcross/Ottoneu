# -*- coding: utf-8 -*-
"""
Ottoneu Valuation
Andrew Cross
http://www.agcross.com

After entering your league number, this program will examine all the players on
every roster, and compare each player's contract against the average value of
that player across the entire Ottoneu Universe
"""

from bs4 import BeautifulSoup
from urllib import urlopen
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

leagueID = 90 #UZR Friendly

#Grab the Average Values page
url = 'http://ottoneu.fangraphs.com/averageValues?gameType=3' #Gametype 3 is for fangraphs points
page = urlopen(url)
soup = BeautifulSoup(page)
averageValues = soup.find('table', attrs={'id': 'averageValues'})
averageValues = pd.read_html(str(averageValues))[0]
averageValues = averageValues.rename(columns={'Name':'Player', 'Salary':'AvgSalary'})
averageValues = averageValues.drop('POS', axis=1)
averageValues = averageValues.rename(columns = {'Player':'Name'}) #Want to merge on this column in a moment

#At some point, Niv put in the ability to quickly acquire a league's roster in csv format
url = 'https://ottoneu.fangraphs.com/%i/rosterexport' % leagueID
rosters = pd.read_csv(url, encoding='utf-8')

#Unfortunately, the average values pages identifies players by their name, but not by any ID
#This is inevitably result in problems where there are two players with the same name (ie, Matt Duffy) 
df = pd.merge(rosters,averageValues,on='Name')

#Take the $ signs out of the dataframe, so numbers can be treated as such
#Take out the emojii characters
df['Salary'] = df['Salary'].replace( '[\$,)]','', regex=True ).astype(int)
df['AvgSalary'] = df['AvgSalary'].replace( '[\$,)]','', regex=True ).astype(float)

#A couple more columns for plotting purposes
df['delta'] = df['Salary']-df['AvgSalary']
df['labels'] = df['Name'] + ' ($' + df['delta'].astype('str') + ')'

#Plot Each Team's Chart
for team in df['Team'].unique():

  fig, ax = plt.subplots()
  ax.yaxis.grid()
  
  fltr = (df['Team'] == team) & (df['delta'] < 0)
  numCheaperContracts = df[fltr].shape[0]
  plt.bar(np.arange(0,numCheaperContracts,1),
          df[fltr].sort('delta')['delta'].values, 
          width=1.0, align='center', color='g')

  fltr = (df['Team'] == team) & (df['delta'] >= 0)
  numExpensiverContracts = df[fltr].shape[0]
  plt.bar(np.arange(numCheaperContracts,df[df['Team'] == team].shape[0],1),
          df[fltr].sort('delta')['delta'].values, 
          width=1.0, align='center', color='r')
  
  ax.autoscale(tight=True)
  fltr = (df['Team'] == team)
  plt.xticks(np.arange(0,df[fltr].shape[0],1))
  ax.xaxis.set_ticklabels(df[fltr].sort('delta')['labels'].values)
  plt.xticks(rotation='vertical')
    
  plt.title('League %i - %s - Player Salaries Compared to Universe Average\n(Lower Numbers Better)' % (leagueID,team))
  plt.ylabel('Salary Difference ($)')
  
  props = dict(boxstyle='round', facecolor='white', alpha=1)
  textstr = ('Num Contracts Cheaper than Avg: %i\n' % numCheaperContracts + 
             'Num Contracts More Expensive than Avg: %i\n' % numExpensiverContracts +
             'Dollars Spent Compared to Avg: $%0.2f\n' % df[fltr]['delta'].sum() +
             'Cost of Average Salaries: $%0.2f' % df[fltr]['AvgSalary'].sum())
             
  ax.text(0.02, 0.95, textstr, transform=ax.transAxes,
          verticalalignment='top', horizontalalignment='left', fontsize=12, bbox=props)
  
  fig.set_size_inches(8/.72, 4.944/.72, forward=True)
  plt.tight_layout()
  plt.savefig('%s.png' % "".join(x for x in team if x.isalnum()))
  plt.show()
