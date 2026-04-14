import requests
from bs4 import BeautifulSoup, Tag
import datetime
import pandas as pd
from dotenv import load_dotenv
import os
import json


def return_hot_offenses():
    load_dotenv()
    weeks_prior = int(os.getenv("HOT_OFFENSE_WEEKS", 3))
    startdate = (datetime.datetime.today() - datetime.timedelta(weeks=weeks_prior)).strftime('%Y-%m-%d')
    url = f"https://www.fangraphs.com/leaders/major-league?pos=all&stats=bat&lg=all&qual=y&type=8&season=2026&month=1000&season1=2026&ind=0&team=0%2Cts&sortcol=19&sortdir=default&startdate={startdate}&enddate=2026-11-01"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    grid_div = soup.find('div', class_='fg-data-grid')
    table = grid_div.find('table') if isinstance(grid_div, Tag) else None

    hot_offenses = []
    if isinstance(table, Tag):
        for row in table.select('tbody tr'):
            off_td = row.find('td', {'data-stat': 'Off'})
            team_td = row.find('td', {'data-stat': 'Team'})
            if isinstance(off_td, Tag) and isinstance(team_td, Tag):
                try:
                    if float(off_td.text.strip()) > 0:
                        hot_offenses.append(team_td.text.strip())
                except ValueError:
                    continue

    today = datetime.datetime.today().strftime('%Y-%m-%d')
    try:
        with open('hot_offenses.json', 'r') as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {}
    existing[today] = hot_offenses
    with open('hot_offenses.json', 'w') as f:
        json.dump(existing, f)

    return hot_offenses
