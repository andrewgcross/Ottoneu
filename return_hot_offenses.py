import requests
import datetime
from dotenv import load_dotenv
import os
import json


def return_hot_offenses(session=None):
    load_dotenv()
    weeks_prior = int(os.getenv("HOT_OFFENSE_WEEKS", 3))
    startdate = (datetime.datetime.today() - datetime.timedelta(weeks=weeks_prior)).strftime('%Y-%m-%d')
    url = f"https://www.fangraphs.com/api/leaders/major-league/data?pos=all&stats=bat&lg=all&qual=y&type=8&season=2026&month=1000&season1=2026&ind=0&team=0%2Cts&sortcol=19&sortdir=default&startdate={startdate}&enddate=2026-11-01"
    if session is not None:
        response = session.get(url)
    else:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})

    hot_offenses = []
    fetch_ok = False
    try:
        payload = response.json()
        rows = payload.get('data', []) if isinstance(payload, dict) else payload
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                if float(row.get('Off', 0)) > 0:
                    team = row.get('Team', '')
                    if team:
                        hot_offenses.append(team)
            except (ValueError, TypeError):
                continue
        fetch_ok = True
    except Exception as e:
        print(f"Warning: could not parse hot offenses response ({response.status_code}): {e}")
        print(f"Response preview: {response.text[:200]}")

    if fetch_ok:
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
