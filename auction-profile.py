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
    df = pd.read_csv('auction-profile.csv', index_col=0)
    
#Analysis of the dataframe
    tdf = df[(df['ended'] > datetime(2016,3,5)) & (df['winningbid']==True)]
    cnt_nominatedby = tdf.groupby('nominatedby').link.nunique().sort_values(ascending=False)
    cnt_wonby = tdf.groupby('team').link.nunique().sort_values(ascending=False)