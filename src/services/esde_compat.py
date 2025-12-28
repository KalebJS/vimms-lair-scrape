"""ES-DE (EmulationStation Desktop Edition) compatibility service.

Provides folder structure and filename conventions compatible with ES-DE
for seamless drag-and-drop to Android devices.

ES-DE expects ROMs in system-specific folders with standardized names.
Reference: https://gitlab.com/es-de/emulationstation-de/-/blob/master/USERGUIDE.md
"""

from dataclasses import dataclass
from pathlib import Path
import re

import structlog

log = structlog.stdlib.get_logger()


@dataclass(frozen=True)
class SystemMapping:
    """Mapping between Vimm's Lair category and ES-DE system."""
    
    vimm_category: str
    esde_folder: str
    full_name: str
    file_extensions: tuple[str, ...]


# Mapping from Vimm's Lair categories to ES-DE folder names
# Based on ES-DE's es_systems.xml standard folder names
VIMM_TO_ESDE_MAPPING: dict[str, SystemMapping] = {
    # Nintendo Consoles
    "NES": SystemMapping("NES", "nes", "Nintendo Entertainment System", (".nes", ".zip", ".7z")),
    "Nintendo": SystemMapping("Nintendo", "nes", "Nintendo Entertainment System", (".nes", ".zip", ".7z")),
    "SNES": SystemMapping("SNES", "snes", "Super Nintendo", (".sfc", ".smc", ".zip", ".7z")),
    "Super Nintendo": SystemMapping("Super Nintendo", "snes", "Super Nintendo", (".sfc", ".smc", ".zip", ".7z")),
    "N64": SystemMapping("N64", "n64", "Nintendo 64", (".n64", ".z64", ".v64", ".zip", ".7z")),
    "Nintendo 64": SystemMapping("Nintendo 64", "n64", "Nintendo 64", (".n64", ".z64", ".v64", ".zip", ".7z")),
    "GameCube": SystemMapping("GameCube", "gc", "Nintendo GameCube", (".iso", ".gcm", ".gcz", ".rvz", ".ciso", ".7z")),
    "Wii": SystemMapping("Wii", "wii", "Nintendo Wii", (".iso", ".wbfs", ".rvz", ".wia", ".gcz")),
    "WiiWare": SystemMapping("WiiWare", "wii", "Nintendo Wii", (".wad",)),
    
    # Nintendo Handhelds
    "GB": SystemMapping("GB", "gb", "Nintendo Game Boy", (".gb", ".zip", ".7z")),
    "Game Boy": SystemMapping("Game Boy", "gb", "Nintendo Game Boy", (".gb", ".zip", ".7z")),
    "GBC": SystemMapping("GBC", "gbc", "Nintendo Game Boy Color", (".gbc", ".zip", ".7z")),
    "Game Boy Color": SystemMapping("Game Boy Color", "gbc", "Nintendo Game Boy Color", (".gbc", ".zip", ".7z")),
    "GBA": SystemMapping("GBA", "gba", "Nintendo Game Boy Advance", (".gba", ".zip", ".7z")),
    "Game Boy Advance": SystemMapping("Game Boy Advance", "gba", "Nintendo Game Boy Advance", (".gba", ".zip", ".7z")),
    "DS": SystemMapping("DS", "nds", "Nintendo DS", (".nds", ".zip", ".7z")),
    "Nintendo DS": SystemMapping("Nintendo DS", "nds", "Nintendo DS", (".nds", ".zip", ".7z")),
    "3DS": SystemMapping("3DS", "n3ds", "Nintendo 3DS", (".3ds", ".cia", ".cxi", ".app")),
    "Nintendo 3DS": SystemMapping("Nintendo 3DS", "n3ds", "Nintendo 3DS", (".3ds", ".cia", ".cxi", ".app")),
    "Virtual Boy": SystemMapping("Virtual Boy", "virtualboy", "Nintendo Virtual Boy", (".vb", ".vboy", ".zip", ".7z")),
    
    # Sega Consoles
    "Genesis": SystemMapping("Genesis", "genesis", "Sega Genesis", (".md", ".gen", ".bin", ".zip", ".7z")),
    "Mega Drive": SystemMapping("Mega Drive", "megadrive", "Sega Mega Drive", (".md", ".gen", ".bin", ".zip", ".7z")),
    "Master System": SystemMapping("Master System", "mastersystem", "Sega Master System", (".sms", ".zip", ".7z")),
    "Sega CD": SystemMapping("Sega CD", "segacd", "Sega CD", (".chd", ".cue", ".iso")),
    "Mega-CD": SystemMapping("Mega-CD", "megacd", "Sega Mega-CD", (".chd", ".cue", ".iso")),
    "32X": SystemMapping("32X", "sega32x", "Sega 32X", (".32x", ".zip", ".7z")),
    "Sega 32X": SystemMapping("Sega 32X", "sega32x", "Sega 32X", (".32x", ".zip", ".7z")),
    "Saturn": SystemMapping("Saturn", "saturn", "Sega Saturn", (".chd", ".cue", ".iso", ".zip", ".7z")),
    "Dreamcast": SystemMapping("Dreamcast", "dreamcast", "Sega Dreamcast", (".chd", ".cdi", ".gdi", ".cue")),
    "Game Gear": SystemMapping("Game Gear", "gamegear", "Sega Game Gear", (".gg", ".zip", ".7z")),
    
    # Sony Consoles
    "PS1": SystemMapping("PS1", "psx", "Sony PlayStation", (".chd", ".cue", ".bin", ".iso", ".pbp", ".m3u")),
    "PlayStation": SystemMapping("PlayStation", "psx", "Sony PlayStation", (".chd", ".cue", ".bin", ".iso", ".pbp", ".m3u")),
    "PS2": SystemMapping("PS2", "ps2", "Sony PlayStation 2", (".chd", ".iso", ".cso", ".gz")),
    "PlayStation 2": SystemMapping("PlayStation 2", "ps2", "Sony PlayStation 2", (".chd", ".iso", ".cso", ".gz")),
    "PS3": SystemMapping("PS3", "ps3", "Sony PlayStation 3", (".iso", ".pkg")),
    "PlayStation 3": SystemMapping("PlayStation 3", "ps3", "Sony PlayStation 3", (".iso", ".pkg")),
    "PSP": SystemMapping("PSP", "psp", "Sony PlayStation Portable", (".iso", ".cso", ".pbp", ".chd")),
    "PlayStation Portable": SystemMapping("PlayStation Portable", "psp", "Sony PlayStation Portable", (".iso", ".cso", ".pbp", ".chd")),
    
    # Microsoft Consoles
    "Xbox": SystemMapping("Xbox", "xbox", "Microsoft Xbox", (".iso",)),
    "Xbox 360": SystemMapping("Xbox 360", "xbox360", "Microsoft Xbox 360", (".iso", ".xex")),
    "Xbox 360 (Digital)": SystemMapping("Xbox 360 (Digital)", "xbox360", "Microsoft Xbox 360", (".iso", ".xex")),
    
    # Atari Consoles
    "Atari 2600": SystemMapping("Atari 2600", "atari2600", "Atari 2600", (".a26", ".bin", ".zip", ".7z")),
    "Atari 5200": SystemMapping("Atari 5200", "atari5200", "Atari 5200", (".a52", ".bin", ".zip", ".7z")),
    "Atari 7800": SystemMapping("Atari 7800", "atari7800", "Atari 7800", (".a78", ".bin", ".zip", ".7z")),
    "Jaguar": SystemMapping("Jaguar", "atarijaguar", "Atari Jaguar", (".j64", ".jag", ".zip", ".7z")),
    "Jaguar CD": SystemMapping("Jaguar CD", "atarijaguarcd", "Atari Jaguar CD", (".cdi", ".cue")),
    "Lynx": SystemMapping("Lynx", "atarilynx", "Atari Lynx", (".lnx", ".zip", ".7z")),
    
    # NEC Consoles
    "TurboGrafx-16": SystemMapping("TurboGrafx-16", "tg16", "NEC TurboGrafx-16", (".pce", ".zip", ".7z")),
    "TurboGrafx-CD": SystemMapping("TurboGrafx-CD", "tg-cd", "NEC TurboGrafx-CD", (".chd", ".cue")),
    "PC Engine": SystemMapping("PC Engine", "pcengine", "NEC PC Engine", (".pce", ".zip", ".7z")),
    "PC Engine CD": SystemMapping("PC Engine CD", "pcenginecd", "NEC PC Engine CD", (".chd", ".cue")),
    
    # SNK Consoles
    "Neo Geo": SystemMapping("Neo Geo", "neogeo", "SNK Neo Geo", (".zip", ".7z")),
    "Neo Geo CD": SystemMapping("Neo Geo CD", "neogeocd", "SNK Neo Geo CD", (".chd", ".cue")),
    "Neo Geo Pocket": SystemMapping("Neo Geo Pocket", "ngp", "SNK Neo Geo Pocket", (".ngp", ".zip", ".7z")),
    "Neo Geo Pocket Color": SystemMapping("Neo Geo Pocket Color", "ngpc", "SNK Neo Geo Pocket Color", (".ngc", ".zip", ".7z")),
    
    # Other Systems
    "CD-i": SystemMapping("CD-i", "cdimono1", "Philips CD-i", (".chd", ".cue", ".iso")),
    "3DO": SystemMapping("3DO", "3do", "3DO Interactive Multiplayer", (".chd", ".cue", ".iso")),
}


class ESDECompatibilityService:
    """Service for ES-DE compatible file organization.
    
    Handles:
    - Mapping Vimm's Lair categories to ES-DE folder names
    - Sanitizing filenames for cross-platform compatibility
    - Generating proper output paths for downloads
    """
    
    base_rom_directory: Path
    
    def __init__(self, base_rom_directory: Path) -> None:
        """Initialize the ES-DE compatibility service.
        
        Args:
            base_rom_directory: Root directory for ROM storage (e.g., ~/ROMs)
        """
        self.base_rom_directory = base_rom_directory
        log.info("ES-DE compatibility service initialized", base_path=str(base_rom_directory))
    
    def get_esde_folder(self, vimm_category: str) -> str:
        """Get the ES-DE folder name for a Vimm's Lair category.
        
        Args:
            vimm_category: Category name from Vimm's Lair
            
        Returns:
            ES-DE compatible folder name
        """
        mapping = VIMM_TO_ESDE_MAPPING.get(vimm_category)
        if mapping:
            return mapping.esde_folder
        
        # Fallback: convert to lowercase and replace spaces with underscores
        fallback = vimm_category.lower().replace(" ", "_").replace("-", "")
        log.warning(
            "Unknown Vimm category, using fallback folder name",
            vimm_category=vimm_category,
            fallback_folder=fallback,
        )
        return fallback
    
    def get_system_mapping(self, vimm_category: str) -> SystemMapping | None:
        """Get the full system mapping for a Vimm's Lair category.
        
        Args:
            vimm_category: Category name from Vimm's Lair
            
        Returns:
            SystemMapping if found, None otherwise
        """
        return VIMM_TO_ESDE_MAPPING.get(vimm_category)
    
    def sanitize_filename(self, title: str, preserve_region: bool = True) -> str:  # noqa: ARG002
        """Sanitize a game title for use as a filename.
        
        ES-DE and most emulators work best with clean filenames that:
        - Don't contain special characters that cause filesystem issues
        - Preserve region tags like (USA), (Europe), (Japan)
        - Preserve version info like (Rev 1), (v1.1)
        - Are readable and match scraper databases
        
        Args:
            title: Original game title
            preserve_region: Whether to keep region/version tags in parentheses (reserved for future use)
            
        Returns:
            Sanitized filename (without extension)
        """
        # Characters that are problematic on various filesystems
        # Windows: \ / : * ? " < > |
        # macOS/Linux: / and null
        # Android: Similar to Windows restrictions
        invalid_chars = r'[\\/:*?"<>|]'
        
        # Replace invalid characters with safe alternatives
        sanitized = re.sub(invalid_chars, "_", title)
        
        # Collapse multiple underscores/spaces
        sanitized = re.sub(r"[_\s]+", " ", sanitized)
        
        # Remove leading/trailing whitespace and dots (Windows issue)
        sanitized = sanitized.strip(" .")
        
        # Ensure the filename isn't empty
        if not sanitized:
            sanitized = "Unknown Game"
        
        # Limit length (most filesystems support 255 chars, but be conservative)
        max_length = 200
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip(" .")
        
        log.debug("Filename sanitized", original=title, sanitized=sanitized)
        return sanitized
    
    def generate_rom_path(
        self,
        vimm_category: str,
        game_title: str,
        disc_number: str | None = None,
        extension: str = "",
    ) -> Path:
        """Generate the full path for a ROM file in ES-DE structure.
        
        ES-DE structure:
        {base_rom_directory}/
        └── {system_folder}/
            └── {game_title}{disc_suffix}.{extension}
        
        For multi-disc games, ES-DE supports:
        - Individual files: "Game Name (Disc 1).chd", "Game Name (Disc 2).chd"
        - M3U playlists for multi-disc games (optional)
        
        Args:
            vimm_category: Category from Vimm's Lair
            game_title: Original game title
            disc_number: Disc identifier (e.g., "Disc 1", "1", or None for single disc)
            extension: File extension (with or without leading dot)
            
        Returns:
            Full path to the ROM file
        """
        # Get ES-DE folder name
        esde_folder = self.get_esde_folder(vimm_category)
        
        # Sanitize the game title
        safe_title = self.sanitize_filename(game_title)
        
        # Handle disc numbering for multi-disc games
        if disc_number and disc_number.lower() not in ("single disc", "single", "1", "disc 1"):
            # Extract just the number if it's like "Disc 2"
            disc_match = re.search(r"(\d+)", disc_number)
            if disc_match:
                disc_num = disc_match.group(1)
                safe_title = f"{safe_title} (Disc {disc_num})"
        
        # Ensure extension has leading dot
        if extension and not extension.startswith("."):
            extension = f".{extension}"
        
        # Build the full path
        filename = f"{safe_title}{extension}"
        rom_path = self.base_rom_directory / esde_folder / filename
        
        log.debug(
            "ROM path generated",
            category=vimm_category,
            esde_folder=esde_folder,
            title=game_title,
            filename=filename,
            full_path=str(rom_path),
        )
        
        return rom_path
    
    def generate_extraction_directory(
        self,
        vimm_category: str,
        game_title: str,  # noqa: ARG002
        disc_number: str | None = None,  # noqa: ARG002
    ) -> Path:
        """Generate the directory where extracted files should be placed.
        
        For ES-DE, extracted files go directly into the system folder,
        not into game-specific subfolders.
        
        Args:
            vimm_category: Category from Vimm's Lair
            game_title: Original game title (reserved for future use)
            disc_number: Disc identifier for multi-disc games (reserved for future use)
            
        Returns:
            Directory path for extracted files
        """
        esde_folder = self.get_esde_folder(vimm_category)
        return self.base_rom_directory / esde_folder
    
    def get_expected_extensions(self, vimm_category: str) -> tuple[str, ...]:
        """Get expected file extensions for a system.
        
        Args:
            vimm_category: Category from Vimm's Lair
            
        Returns:
            Tuple of expected file extensions
        """
        mapping = VIMM_TO_ESDE_MAPPING.get(vimm_category)
        if mapping:
            return mapping.file_extensions
        return (".zip", ".7z")  # Default fallback
    
    @staticmethod
    def get_supported_systems() -> list[str]:
        """Get list of all supported Vimm's Lair categories.
        
        Returns:
            List of category names that have ES-DE mappings
        """
        return list(VIMM_TO_ESDE_MAPPING.keys())
