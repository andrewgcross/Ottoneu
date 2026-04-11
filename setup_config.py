import os


def create_env_file():
    print("--- Ottoneu Project Setup ---")
    username = input("Enter your Ottoneu Username: ")
    password = input("Enter your Ottoneu Password: ")
    league = input("Enter your league number: ")
    team = input("Enter your team ID (leave blank if unknown): ").strip()
    target_date = input("Enter a target date to override today (YYYY-MM-DD, leave blank for today): ").strip()

    with open(".env", "w") as f:
        f.write(f"OTTONEU_USERNAME={username}\n")
        f.write(f"OTTONEU_PASSWORD={password}\n")
        f.write(f"LEAGUE={league}\n")
        if team:
            f.write(f"TEAM_ID={team}\n")
        if target_date:
            f.write(f"TARGET_DATE={target_date}\n")

    print("\nSuccessfully created .env file!")
    print("Make sure '.env' is listed in your .gitignore file to stay secure.")

if __name__ == "__main__":
    create_env_file()