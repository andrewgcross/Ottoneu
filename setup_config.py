import os


def create_env_file():
    print("--- Ottoneu Project Setup ---")
    username = input("Enter your Ottoneu Username: ")
    password = input("Enter your Ottoneu Password: ")
    league = input("Enter your league number: ")

    with open(".env", "w") as f:
        f.write(f"OTTONEU_USERNAME={username}\n")
        f.write(f"OTTONEU_PASSWORD={password}\n")
        f.write(f"OTTONEU_LEAGUE={league}\n")

    print("\nSuccessfully created .env file!")
    print("Make sure '.env' is listed in your .gitignore file to stay secure.")

if __name__ == "__main__":
    create_env_file()