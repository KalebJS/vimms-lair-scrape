"""Game scraping service with async methods and progress tracking."""

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import datetime

import structlog
from bs4 import BeautifulSoup

from ..models.game import GameData, DiscInfo
from ..models.progress import ScrapingProgress
from .errors import ScrapingError, NetworkError, get_error_service
from .http_client import HttpClientService

log = structlog.stdlib.get_logger()


class GameScraperService:
    """Service for scraping game data from Vimm's Lair with progress tracking."""
    
    def __init__(self, http_client: HttpClientService, request_delay: float = 2.0) -> None:
        """Initialize the game scraper service.
        
        Args:
            http_client: HTTP client service for making requests
            request_delay: Delay between requests in seconds (set to 0 for testing)
        """
        self.http_client: HttpClientService = http_client
        self.site_base_url: str = "https://vimm.net/vault/Xbox"
        self.download_base_url: str = "https://download2.vimm.net"
        self.request_delay: float = request_delay
        
        # Progress tracking state
        self._current_letter: str = ""
        self._current_game: str = ""
        self._games_processed: int = 0
        self._total_games: int = 0
        self._errors: list[str] = []
        self._cancelled: bool = False
        
        log.info("Game scraper service initialized", base_url=self.site_base_url)
    
    async def scrape_category(
        self, 
        category: str, 
        letters: list[str]
    ) -> AsyncIterator[GameData]:
        """Scrape games from a specific category and letters.
        
        Args:
            category: The game category (e.g., "Xbox")
            letters: List of letters to scrape (e.g., ["J", "K", "L"])
            
        Yields:
            GameData objects for each successfully scraped game
            
        Raises:
            Exception: If scraping fails catastrophically
        """
        log.info(
            "Starting category scraping",
            category=category,
            letters=letters,
            total_letters=len(letters)
        )
        
        # Reset progress tracking
        self._games_processed = 0
        self._total_games = 0
        self._errors.clear()
        self._cancelled = False
        
        # First pass: count total games for progress tracking
        await self._count_total_games(letters)
        
        # Second pass: scrape actual game data
        for letter in letters:
            if self._cancelled:
                log.info("Scraping cancelled by user")
                break
                
            self._current_letter = letter
            
            try:
                async for game_data in self._scrape_letter_page(letter):
                    if self._cancelled:
                        break
                    yield game_data
                    
            except Exception as e:
                error_msg = f"Failed to scrape letter {letter}: {str(e)}"
                log.error("Letter scraping failed", letter=letter, error=str(e))
                self._errors.append(error_msg)
                # Continue with next letter instead of failing completely
                continue
        
        log.info(
            "Category scraping completed",
            games_processed=self._games_processed,
            total_errors=len(self._errors),
            cancelled=self._cancelled
        )
    
    async def scrape_game_details(self, game_url: str) -> GameData:
        """Scrape detailed information for a specific game.
        
        Args:
            game_url: Full URL to the game page
            
        Returns:
            GameData object with complete game information
            
        Raises:
            Exception: If game details cannot be scraped
        """
        log.debug("Scraping game details", game_url=game_url)
        
        try:
            response = await self.http_client.get(game_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract game title from the page
            title_element = soup.find('h1')
            if not title_element:
                raise ValueError("Game title not found on page")
            
            game_title = title_element.get_text(strip=True)
            
            # Extract discs information
            discs = await self._extract_disc_info(soup, game_title)
            
            # Determine category from URL
            category = self._extract_category_from_url(game_url)
            
            game_data = GameData(
                title=game_title,
                game_url=game_url,
                category=category,
                discs=discs,
                scraped_at=datetime.now()
            )
            
            log.info(
                "Game details scraped successfully",
                title=game_title,
                discs_count=len(discs),
                category=category
            )
            
            return game_data
            
        except Exception as e:
            log.error("Failed to scrape game details", game_url=game_url, error=str(e))
            raise
    
    def get_scraping_progress(self) -> ScrapingProgress:
        """Get current scraping progress information.
        
        Returns:
            ScrapingProgress object with current state
        """
        return ScrapingProgress(
            current_letter=self._current_letter,
            current_game=self._current_game,
            games_processed=self._games_processed,
            total_games=self._total_games,
            errors=self._errors.copy()
        )
    
    def cancel_scraping(self) -> None:
        """Cancel the current scraping operation."""
        self._cancelled = True
        log.info("Scraping cancellation requested")
    
    async def _count_total_games(self, letters: list[str]) -> None:
        """Count total games across all letters for progress tracking."""
        log.debug("Counting total games for progress tracking")
        
        total_count = 0
        for letter in letters:
            try:
                page_url = f"{self.site_base_url}/{letter}"
                response = await self.http_client.get(page_url)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                game_table = soup.find('table', {'class': 'rounded centered cellpadding1 hovertable striped'})
                if game_table:
                    game_links = game_table.find_all('a', href=True)
                    # Count only valid game links
                    valid_links = [
                        link for link in game_links 
                        if link['href'].startswith("/vault/") and link['href'][7:].isdigit()
                    ]
                    total_count += len(valid_links)
                    
            except Exception as e:
                log.warning("Failed to count games for letter", letter=letter, error=str(e))
                # Continue counting other letters
                continue
        
        self._total_games = total_count
        log.info("Total games counted", total_games=total_count)
    
    async def _scrape_letter_page(self, letter: str) -> AsyncIterator[GameData]:
        """Scrape all games from a specific letter page."""
        page_url = f"{self.site_base_url}/{letter}"
        log.debug("Scraping letter page", letter=letter, url=page_url)
        
        try:
            response = await self.http_client.get(page_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            game_table = soup.find('table', {'class': 'rounded centered cellpadding1 hovertable striped'})
            
            if not game_table:
                log.warning("Game table not found on page", letter=letter)
                return
            
            game_links = game_table.find_all('a', href=True)
            
            for link in game_links:
                if self._cancelled:
                    break
                    
                game_url = link['href']
                game_title = link.text.strip()
                
                # Filter for valid game links
                if game_url.startswith("/vault/") and game_url[7:].isdigit():
                    full_game_url = f"https://vimm.net{game_url}"
                    self._current_game = game_title
                    
                    try:
                        game_data = await self.scrape_game_details(full_game_url)
                        self._games_processed += 1
                        
                        log.debug(
                            "Game scraped successfully",
                            title=game_title,
                            progress=f"{self._games_processed}/{self._total_games}"
                        )
                        
                        yield game_data
                        
                        # Add delay between requests to be respectful
                        if self.request_delay > 0:
                            await asyncio.sleep(self.request_delay)
                        
                    except Exception as e:
                        error_msg = f"Failed to scrape game '{game_title}': {str(e)}"
                        log.error("Game scraping failed", title=game_title, error=str(e))
                        self._errors.append(error_msg)
                        # Continue with next game instead of failing completely
                        continue
                        
        except Exception as e:
            log.error("Failed to scrape letter page", letter=letter, error=str(e))
            raise
    
    async def _extract_disc_info(self, soup: BeautifulSoup, game_title: str) -> list[DiscInfo]:
        """Extract disc information from game page HTML."""
        discs: list[DiscInfo] = []
        
        try:
            # Check for disc selector dropdown and media IDs in JavaScript
            script_tags = soup.find_all('script')
            script_content = ' '.join(str(script) for script in script_tags)
            media_ids = re.findall(r'"ID":(\d+)', script_content)
            
            if media_ids:
                # Multiple discs found
                for idx, media_id in enumerate(media_ids, 1):
                    disc_number = f"Disc {idx}"
                    download_url = f"{self.download_base_url}/?mediaId={media_id}"
                    
                    disc_info = DiscInfo(
                        disc_number=disc_number,
                        media_id=media_id,
                        download_url=download_url
                    )
                    discs.append(disc_info)
                    
                log.debug("Multiple discs found", game_title=game_title, disc_count=len(media_ids))
                
            else:
                # Single disc - look for media ID input
                media_id_input = soup.find('input', {'name': 'mediaId'})
                if media_id_input and 'value' in media_id_input.attrs:
                    media_id = media_id_input['value']
                    download_url = f"{self.download_base_url}/?mediaId={media_id}"
                    
                    disc_info = DiscInfo(
                        disc_number="Single Disc",
                        media_id=media_id,
                        download_url=download_url
                    )
                    discs.append(disc_info)
                    
                    log.debug("Single disc found", game_title=game_title, media_id=media_id)
                    
                else:
                    log.warning("No media ID found for game", game_title=game_title)
                    
        except Exception as e:
            log.error("Failed to extract disc info", game_title=game_title, error=str(e))
            # Return empty list instead of failing completely
            
        return discs
    
    def _extract_category_from_url(self, game_url: str) -> str:
        """Extract category from game URL."""
        # For now, assume Xbox category based on the base URL
        # This could be made more dynamic in the future
        return "Xbox"