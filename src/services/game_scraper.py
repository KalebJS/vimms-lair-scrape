"""Game scraping service with async methods and progress tracking."""

import asyncio
import base64
import re
from collections.abc import AsyncIterator
from datetime import datetime

import structlog
from bs4 import BeautifulSoup

from ..models.game import GameData, DiscInfo
from ..models.progress import ScrapingProgress
from .http_client import HttpClientService

log = structlog.stdlib.get_logger()


class GameScraperService:
    """Service for scraping game data from Vimm's Lair with progress tracking."""
    
    def __init__(
        self,
        http_client: HttpClientService,
        request_delay: float = 2.0,
        minimum_score: float | None = None,
        concurrent_scrapes: int = 3,
    ) -> None:
        """Initialize the game scraper service.
        
        Args:
            http_client: HTTP client service for making requests
            request_delay: Delay between requests in seconds (set to 0 for testing)
            minimum_score: Minimum rating score (0-100) to include games, None = no filter
            concurrent_scrapes: Maximum concurrent metadata scraping requests (default: 3)
        """
        self.http_client: HttpClientService = http_client
        self.site_base_url: str = "https://vimm.net/vault"
        self.download_base_url: str = "https://dl3.vimm.net"
        self.request_delay: float = request_delay
        self.minimum_score: float | None = minimum_score
        self._concurrent_scrapes: int = concurrent_scrapes
        self._scrape_semaphore: asyncio.Semaphore = asyncio.Semaphore(concurrent_scrapes)
        self._current_category: str = ""
        
        # Progress tracking state
        self._current_letter: str = ""
        self._current_game: str = ""
        self._games_processed: int = 0
        self._games_skipped: int = 0  # Games skipped due to low score
        self._total_games: int = 0
        self._errors: list[str] = []
        self._cancelled: bool = False
        
        log.info(
            "Game scraper service initialized",
            base_url=self.site_base_url,
            minimum_score=minimum_score,
            concurrent_scrapes=concurrent_scrapes,
        )
    
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
        self._games_skipped = 0
        self._total_games = 0
        self._errors.clear()
        self._cancelled = False
        
        # First pass: count total games for progress tracking
        await self._count_total_games(letters, category)
        
        # Store category for use in helper methods
        self._current_category = category
        
        # Second pass: scrape actual game data
        for letter in letters:
            if self._cancelled:
                log.info("Scraping cancelled by user")
                break
                
            self._current_letter = letter
            
            try:
                async for game_data in self._scrape_letter_page(letter, category):
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
            games_skipped=self._games_skipped,
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
            
            # Extract game title - try multiple sources
            game_title = self._extract_game_title(soup)
            if not game_title:
                raise ValueError("Game title not found on page")
            
            # Extract discs information
            discs = await self._extract_disc_info(soup, game_title)
            
            # Extract rating information
            rating, rating_count = self._extract_rating(soup)
            
            # Determine category from URL
            category = self._extract_category_from_url(game_url)
            
            game_data = GameData(
                title=game_title,
                game_url=game_url,
                category=category,
                discs=discs,
                scraped_at=datetime.now(),
                rating=rating,
                rating_count=rating_count,
            )
            
            log.info(
                "Game details scraped successfully",
                title=game_title,
                discs_count=len(discs),
                category=category,
                rating=rating,
                rating_count=rating_count,
            )
            
            return game_data
            
        except Exception as e:
            log.error("Failed to scrape game details", game_url=game_url, error=str(e))
            raise
    
    def _extract_game_title(self, soup: BeautifulSoup) -> str | None:
        """Extract game title from page using multiple fallback methods.
        
        The site renders titles via canvas with base64-encoded data-v attribute,
        so we need to try multiple extraction methods.
        
        Args:
            soup: BeautifulSoup parsed HTML
            
        Returns:
            Game title string or None if not found
        """
        # Method 1: Try canvas element with base64-encoded title (id="canvas")
        canvas = soup.find('canvas', {'id': 'canvas'})
        if canvas and canvas.get('data-v'):
            try:
                data_v = canvas['data-v']
                if isinstance(data_v, list):
                    data_v = data_v[0]
                decoded = base64.b64decode(data_v).decode('utf-8')
                if decoded:
                    log.debug("Title extracted from canvas data-v", title=decoded)
                    return decoded
            except Exception as e:
                log.debug("Failed to decode canvas data-v", error=str(e))
        
        # Method 2: Try og:title meta tag
        og_title = soup.find('meta', {'property': 'og:title'})
        if og_title and og_title.get('content'):
            title = og_title['content']
            if isinstance(title, list):
                title = title[0]
            log.debug("Title extracted from og:title", title=title)
            return str(title)
        
        # Method 3: Try page title tag and extract game name
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            # Format: "The Vault: Game Name (System)"
            if title_text.startswith("The Vault:"):
                # Extract game name between "The Vault: " and " ("
                match = re.match(r"The Vault:\s*(.+?)\s*\([^)]+\)$", title_text)
                if match:
                    title = match.group(1)
                    log.debug("Title extracted from page title", title=title)
                    return title
        
        # Method 4: Try h1 tag (original method, may not work on current site)
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
            if title:
                log.debug("Title extracted from h1", title=title)
                return title
        
        return None
    
    def _extract_rating(self, soup: BeautifulSoup) -> tuple[float | None, int | None]:
        """Extract rating information from game page.
        
        Vimm's Lair displays ratings in a table with Graphics, Sound, Gameplay, Overall.
        The Overall score is on a 1-10 scale with vote count in parentheses.
        
        Example HTML structure:
        <td>Overall</td><td></td><td>7.67&nbsp;<span...>(6 votes)</span>
        
        Args:
            soup: BeautifulSoup parsed HTML
            
        Returns:
            Tuple of (rating as 0-100 scale, number of ratings) or (None, None) if not found
        """
        try:
            # Method 1: Look for Vimm's Lair rating table structure
            # Format: <td>Overall</td><td></td><td>SCORE&nbsp;<span>(N votes)</span>
            html_str = str(soup)
            
            # Pattern to match: Overall</td><td></td><td>SCORE&nbsp;<span...>(N vote(s))</span>
            overall_pattern = re.compile(
                r'Overall</td><td></td><td>(\d+(?:\.\d+)?)\s*(?:&nbsp;)?(?:<span[^>]*>\((\d+)\s*votes?\)</span>)?',
                re.IGNORECASE,
            )
            match = overall_pattern.search(html_str)
            if match:
                score = float(match.group(1))
                # Convert 1-10 scale to 0-100 percentage
                rating = score * 10
                rating_count = int(match.group(2)) if match.group(2) else None
                log.debug(
                    "Rating extracted from Overall score",
                    raw_score=score,
                    rating=rating,
                    count=rating_count,
                )
                return rating, rating_count
            
            # Method 2: Alternative - find all td elements and look for Overall row
            all_tds = soup.find_all('td')
            for i, td in enumerate(all_tds):
                if td.get_text(strip=True) == 'Overall' and i + 2 < len(all_tds):
                    # The score is typically 2 cells after "Overall"
                    score_td = all_tds[i + 2]
                    score_text = score_td.get_text(strip=True)
                    
                    # Extract score (e.g., "7.67" from "7.67(6 votes)")
                    score_match = re.match(r'(\d+(?:\.\d+)?)', score_text)
                    if score_match:
                        score = float(score_match.group(1))
                        rating = score * 10  # Convert to 0-100 scale
                        
                        # Try to extract vote count
                        vote_match = re.search(r'\((\d+)\s*votes?\)', score_text)
                        rating_count = int(vote_match.group(1)) if vote_match else None
                        
                        log.debug(
                            "Rating extracted from table cells",
                            raw_score=score,
                            rating=rating,
                            count=rating_count,
                        )
                        return rating, rating_count
            
            log.debug("No rating found on page")
            return None, None
            
        except Exception as e:
            log.warning("Failed to extract rating", error=str(e))
            return None, None
    
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
            errors=self._errors.copy(),
            games_skipped=self._games_skipped,
        )
    
    def cancel_scraping(self) -> None:
        """Cancel the current scraping operation."""
        self._cancelled = True
        log.info("Scraping cancellation requested")
    
    async def _count_total_games(self, letters: list[str], category: str = "") -> None:
        """Count total games across all letters for progress tracking."""
        log.debug("Counting total games for progress tracking")
        
        cat = category or self._current_category
        total_count = 0
        for letter in letters:
            try:
                page_url = f"{self.site_base_url}/{cat}/{letter}"
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
    
    async def _scrape_letter_page(self, letter: str, category: str = "") -> AsyncIterator[GameData]:
        """Scrape all games from a specific letter page with concurrent metadata fetching."""
        cat = category or self._current_category
        page_url = f"{self.site_base_url}/{cat}/{letter}"
        log.debug("Scraping letter page", letter=letter, url=page_url)
        
        try:
            response = await self.http_client.get(page_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            game_table = soup.find('table', {'class': 'rounded centered cellpadding1 hovertable striped'})
            
            if not game_table:
                log.warning("Game table not found on page", letter=letter)
                return
            
            game_links = game_table.find_all('a', href=True)
            
            # Collect valid game URLs for concurrent scraping
            game_urls: list[tuple[str, str]] = []  # (full_url, title)
            for link in game_links:
                game_url = link['href']
                game_title = str(link.text).strip() if link.text else ""
                
                # Filter for valid game links
                if isinstance(game_url, str) and game_url.startswith("/vault/") and game_url[7:].isdigit():
                    full_game_url = f"https://vimm.net{game_url}"
                    game_urls.append((full_game_url, game_title))
            
            log.debug(
                "Found games to scrape",
                letter=letter,
                game_count=len(game_urls),
                concurrent_limit=self._concurrent_scrapes,
            )
            
            # Process games concurrently with semaphore limiting
            async def scrape_single_game(url: str, title: str) -> GameData | None:
                """Scrape a single game with semaphore control."""
                if self._cancelled:
                    return None
                
                async with self._scrape_semaphore:
                    if self._cancelled:
                        return None
                    
                    self._current_game = title
                    
                    try:
                        # Add delay before request to respect rate limits
                        if self.request_delay > 0:
                            await asyncio.sleep(self.request_delay)
                        
                        game_data = await self.scrape_game_details(url)
                        
                        # Filter by minimum score if configured
                        if self.minimum_score is not None:
                            if game_data.rating is None:
                                log.debug(
                                    "Game has no rating, including anyway",
                                    title=title,
                                )
                            elif game_data.rating < self.minimum_score:
                                self._games_skipped += 1
                                log.info(
                                    "Game skipped due to low score",
                                    title=title,
                                    rating=game_data.rating,
                                    minimum_score=self.minimum_score,
                                )
                                return None
                        
                        self._games_processed += 1
                        
                        log.debug(
                            "Game scraped successfully",
                            title=title,
                            rating=game_data.rating,
                            progress=f"{self._games_processed}/{self._total_games}",
                        )
                        
                        return game_data
                        
                    except Exception as e:
                        error_msg = f"Failed to scrape game '{title}': {str(e)}"
                        log.error("Game scraping failed", title=title, error=str(e))
                        self._errors.append(error_msg)
                        return None
            
            # Create tasks for all games
            tasks = [
                asyncio.create_task(scrape_single_game(url, title))
                for url, title in game_urls
            ]
            
            # Yield results as they complete
            for coro in asyncio.as_completed(tasks):
                if self._cancelled:
                    # Cancel remaining tasks
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    break
                
                result = await coro
                if result is not None:
                    yield result
                        
        except Exception as e:
            log.error("Failed to scrape letter page", letter=letter, error=str(e))
            raise
    
    async def _extract_disc_info(self, soup: BeautifulSoup, game_title: str) -> list[DiscInfo]:
        """Extract disc information from game page HTML."""
        discs: list[DiscInfo] = []
        
        try:
            # Extract download server from form action (e.g., //dl2.vimm.net/ or //dl3.vimm.net/)
            download_form = soup.find('form', {'id': 'dl_form'})
            download_base = "https://dl3.vimm.net"  # Default fallback
            if download_form and download_form.get('action'):
                action = download_form['action']
                if isinstance(action, list):
                    action = action[0]
                # Convert //dl2.vimm.net/ to https://dl2.vimm.net
                if action.startswith('//'):
                    download_base = f"https:{action.rstrip('/')}"
                elif action.startswith('http'):
                    download_base = action.rstrip('/')
                log.debug("Download server extracted", server=download_base)
            
            # Check for disc selector dropdown and media IDs in JavaScript
            script_tags = soup.find_all('script')
            script_content = ' '.join(str(script) for script in script_tags)
            media_ids = re.findall(r'"ID":(\d+)', script_content)
            
            if media_ids:
                # Multiple discs found (or single disc with version variants)
                # For single-disc games, there may be multiple IDs for different versions
                # We typically want the first one (default selected)
                for idx, media_id in enumerate(media_ids, 1):
                    disc_number = f"Disc {idx}" if len(media_ids) > 1 else "Disc 1"
                    download_url = f"{download_base}/?mediaId={media_id}"
                    
                    disc_info = DiscInfo(
                        disc_number=disc_number,
                        media_id=media_id,
                        download_url=download_url
                    )
                    discs.append(disc_info)
                    
                    # For single-disc games with multiple versions, only take the first
                    if len(media_ids) == 1:
                        break
                    
                log.debug("Discs found", game_title=game_title, disc_count=len(discs))
                
            else:
                # Single disc - look for media ID input
                media_id_input = soup.find('input', {'name': 'mediaId'})
                if media_id_input and 'value' in media_id_input.attrs:
                    media_id = str(media_id_input['value'])
                    if isinstance(media_id, list):
                        media_id = media_id[0]
                    download_url = f"{download_base}/?mediaId={media_id}"
                    
                    disc_info = DiscInfo(
                        disc_number="Disc 1",
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
        # Return the current category being scraped
        return self._current_category or "Unknown"