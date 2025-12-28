import requests
from bs4 import BeautifulSoup
import time
import re
import json

# Base URLs
site_base_url = "https://vimm.net/vault/GBC"
download_base_url = "https://download2.vimm.net"

# Define the letters (J to Q) to scrape
target_letters = ['J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q']

# Dictionary to hold game data
games_data = {}

# Function to gather a specific game disc's download link
def get_disc_download_link(media_id, disc_number, game_title):
    download_url = f"{download_base_url}/?mediaId={media_id}"
    return {
        "disc": disc_number,
        "download_url": download_url
    }

# Scraping function to gather download links and save them in JSON
def scrape_data():
    print("Starting scraping process...")
    for letter in target_letters:
        page_url = f"{site_base_url}/{letter}"
        print(f"Scraping page: {page_url}")
        
        response = requests.get(page_url, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        game_table = soup.find('table', {'class': 'rounded centered cellpadding1 hovertable striped'})
        
        if game_table:
            game_links = game_table.find_all('a', href=True)
            
            for link in game_links:
                game_url = link['href']
                game_title = link.text.strip()
                
                if game_url.startswith("/vault/") and game_url[7:].isdigit():
                    full_game_url = f"https://vimm.net{game_url}"
                    print(f"Game: {game_title}, URL: {full_game_url}")
                    
                    # Initialize game entry in dictionary
                    games_data[game_title] = {
                        "game_url": full_game_url,
                        "discs": []
                    }
                    
                    game_page_response = requests.get(full_game_url, verify=False)
                    game_soup = BeautifulSoup(game_page_response.text, 'html.parser')
                    
                    # Check for disc selector dropdown and media IDs in JavaScript
                    script_tags = game_soup.find_all('script')
                    media_ids = re.findall(r'"ID":(\d+)', str(script_tags))
                    
                    if media_ids:
                        for idx, media_id in enumerate(media_ids, 1):
                            disc_number = f"Disc {idx}"
                            games_data[game_title]["discs"].append(
                                get_disc_download_link(media_id, disc_number, game_title)
                            )
                    else:
                        media_id_input = game_soup.find('input', {'name': 'mediaId'})
                        if media_id_input:
                            media_id = media_id_input['value']
                            games_data[game_title]["discs"].append(
                                get_disc_download_link(media_id, "Single Disc", game_title)
                            )
                        else:
                            print(f"No media ID found for {game_title}")
                    
                    # Write current data to JSON file after each game
                    with open("games_data.json", "w") as file:
                        json.dump(games_data, file, indent=4)
                    
                    time.sleep(2)  # Wait briefly between requests
        else:
            print("Game table not found on this page.")
    
    print("Scraping complete. Data saved to 'games_data.json'.")

# Load games data from JSON file
def load_game_data():
    with open("games_data.json", "r") as file:
        return json.load(file)

# Function to download games based on the loaded data
def start_downloads(games_data):
    for game_title, data in games_data.items():
        for disc in data["discs"]:
            download_disc(disc["download_url"], game_title, disc["disc"])
            time.sleep(1)  # Optional delay to avoid overloading the server

# Download function for each game disc
def download_disc(download_url, game_title, disc_number):
    headers = {
        "Referer": "https://vimm.net/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36"
    }
    try:
        print(f"Downloading {game_title} - {disc_number} from {download_url}")
        response = requests.get(download_url, headers=headers, stream=True, verify=False)
        response.raise_for_status()
        
        # Save the downloaded file
        file_path = f"{game_title}_{disc_number}.iso"
        with open(file_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        
        print(f"Downloaded {game_title} - {disc_number} successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to download {game_title} - {disc_number}: {e}")

# Main execution
if __name__ == "__main__":
    # Prompt user for scraping or downloading
    user_choice = input("Would you like to (1) scrape for new download links or (2) download using 'games_data.json'? (Enter 1 or 2): ").strip()
    
    if user_choice == "1":
        scrape_data()
    elif user_choice == "2":
        try:
            games_data = load_game_data()
            start_downloads(games_data)
        except FileNotFoundError:
            print("Error: 'games_data.json' not found. Please run the scraping process first.")
    else:
        print("Invalid choice. Exiting program.")
