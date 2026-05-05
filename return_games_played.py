from bs4 import BeautifulSoup, Tag
import datetime
import json


def _parse_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def return_games_played(session, league_id, today=None, soup=None):
    if today is None:
        today = datetime.datetime.today().strftime('%Y-%m-%d')

    try:
        with open('games_played.json', 'r') as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {}

    if today in existing:
        return existing[today]

    if soup is None:
        url = f"https://ottoneu.fangraphs.com/{league_id}/setlineups?date={today}"
        response = session.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

    result = {"batters": {}, "pitchers": {}}

    games_section = next(
        (s for s in soup.find_all('section', class_='section-container')
         if isinstance(s.find('h2'), Tag) and 'Games Played' in s.find('h2').get_text()),
        None
    )

    if games_section is not None:
        batter_h3 = next(
            (h for h in games_section.find_all('h3') if 'Position Players' in h.get_text()),
            None
        )
        if isinstance(batter_h3, Tag):
            batter_table = batter_h3.find_next('table', class_='lineup-table')
            if isinstance(batter_table, Tag):
                for row in batter_table.select('tbody tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        pos = cells[0].get_text(strip=True)
                        result["batters"][pos] = {
                            "games_played": _parse_int(cells[1].get_text(strip=True)),
                            "projected": _parse_int(cells[2].get_text(strip=True)),
                            "max_allowed": _parse_int(cells[3].get_text(strip=True)),
                        }

        pitcher_h3 = next(
            (h for h in games_section.find_all('h3') if 'Pitcher' in h.get_text()),
            None
        )
        if isinstance(pitcher_h3, Tag):
            pitcher_table = pitcher_h3.find_next('table', class_='lineup-table')
            if isinstance(pitcher_table, Tag):
                for row in pitcher_table.select('tbody tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        pos = cells[0].get_text(strip=True)
                        result["pitchers"][pos] = {
                            "innings_pitched": _parse_float(cells[1].get_text(strip=True)),
                            "projected": _parse_float(cells[2].get_text(strip=True)),
                            "max_allowed": _parse_float(cells[3].get_text(strip=True)),
                        }

    existing[today] = result
    with open('games_played.json', 'w') as f:
        json.dump(existing, f)

    return result
