# -*- coding: utf-8 -*-
"""
Ottoneu Valuation
Andrew Cross
http://www.agcross.com

After entering your league number, this program will parse through all of the league's
auctions and profile those auctions.
"""

from bs4 import BeautifulSoup
from urllib import urlopen
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import os.path

if not (os.path.isfile('auction-profile.csv')):

    leagueID = 90 #UZR Friendly
    
    #Grab the Auctions page
    url = 'https://ottoneu.fangraphs.com/%s/auctions' % leagueID #Gametype 3 is for fangraphs points
    page = urlopen(url)
    soup = BeautifulSoup(page, "html.parser")
    
    completed = soup.find_all('table')[1] #The second table is the Completed Auctions listing
    completed = completed.find_all('tr',['even','odd']) #The first row *should* be the header and every row after that is classed as either even or odd
    
    #Because I do everything with pandas
    df = pd.DataFrame(columns=["name","link","ended","nominatedby","team","bid","winningbid"])
    i = 0 #use as an index for creating the dataframe
    
    for row in completed:
        link = row.find(string='Results').parent.get('href')
        url = 'https://ottoneu.fangraphs.com%s' % link
        page = urlopen(url)
        soup = BeautifulSoup(page, "html.parser") #no need to make a new variable as the 'completed' variable's been created
        
        name = soup.find_all('h2')[0].a.string
        ended = soup.find_all('h3')[0].string.partition("Ended on ")[2]
        ended = datetime.strptime(ended,'%B %d, %Y %I:%M %p')
        nominatedby = soup.find_all('h3')[1].a.string.encode('ascii','ignore').strip()
        
        print(name)         
        
        for bid in enumerate(soup.find_all('tr',['even','odd'])):
            df.loc[i,"name"] = name
            df.loc[i,"link"] = link
            df.loc[i,"ended"] = ended
            df.loc[i,"nominatedby"] = nominatedby
            df.loc[i,"team"] = bid[1].a.string.encode('ascii','ignore').strip()
            df.loc[i,"bid"] = int(bid[1].find_all('td')[1].string.strip('$'))
            
            if bid[0]==0:
                df.loc[i,"winningbid"] = True
            else:
                df.loc[i,"winningbid"] = False
                
            i=i+1

    df.to_csv('auction-profile.csv')

else:
    df = pd.read_csv('auction-profile.csv', index_col=0, parse_dates=['ended'])
    
#Analysis of the dataframe
tdf = df[(df['ended'] > datetime(2016,3,5)) & (df['winningbid']==True)]
nominated = tdf.groupby('nominatedby').link.nunique().sort_values(ascending=False)
won = tdf.groupby('team').link.nunique().sort_values(ascending=False)

nominated.rename('Nominated', inplace=True)
won.rename('Won', inplace=True)

g = pd.concat([nominated,won], axis=1)
g.sort_values(by='Nominated', ascending=False, inplace=True)

ind = np.arange(g.shape[0])
width = .35

plt.rcParams['figure.figsize'] = 12.458, 7.2
fig, ax = plt.subplots()
ax.yaxis.grid()
nominated_ = ax.bar(ind,g.Nominated.values, color='g', width=width)
won_ = ax.bar(ind+width,g.Won.values, color='r', width=width)

ax.set_ylabel('Team')
ax.set_title('League %i Auctions Nominated/Won during 2016 to Date' % leagueID)
ax.set_xticks(ind + width)
ax.set_xticklabels(g.index.values)

ax.legend((nominated_[0], won_[0]), ('Nominated', 'Won'))
plt.xticks(rotation=45, horizontalalignment='right')

plt.gcf().tight_layout()
plt.savefig('League%i_auction-profile.png' % leagueID)