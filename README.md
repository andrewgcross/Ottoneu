# ottoneu-tools

I first wrote this  roster-setting script in ~2014 to help me compete in a competitive league. I resurrected it in 2026 with a refresh to make it Python3 compatible.

## Usage

1. It is recommended to use a virtual environment; dependencies inclue requests, beautifulsoup4, pandas, python-dotenv
2. Clone the repo to a location where you can set a chron job or tash scheduler to run it several times throughout the day as lineup changes are reported by each team
3. Run setup_config.py to add login credentials and league information to environment variables in the same folder
4. Monitor and set your pitchers manually

## Updates

v2.0 (26-Mar-2026)
- A setup_config.py now allows you to include login credentials as environment variables
- Code was updated from Python2 to Python3
- The moveplayers function was updated to accomodate changes made to the site over the last decade