"""Tests for ES-DE compatibility service."""

from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from src.services.esde_compat import (
    ESDECompatibilityService,
    SystemMapping,
    VIMM_TO_ESDE_MAPPING,
)


class TestSystemMappings:
    """Tests for system mapping configuration."""
    
    def test_all_mappings_have_required_fields(self) -> None:
        """All system mappings should have all required fields."""
        for vimm_cat, mapping in VIMM_TO_ESDE_MAPPING.items():
            assert isinstance(mapping, SystemMapping)
            assert mapping.vimm_category == vimm_cat
            assert mapping.esde_folder, f"Missing esde_folder for {vimm_cat}"
            assert mapping.full_name, f"Missing full_name for {vimm_cat}"
            assert mapping.file_extensions, f"Missing file_extensions for {vimm_cat}"
    
    def test_esde_folders_are_lowercase(self) -> None:
        """ES-DE folder names should be lowercase."""
        for vimm_cat, mapping in VIMM_TO_ESDE_MAPPING.items():
            assert mapping.esde_folder == mapping.esde_folder.lower(), (
                f"ES-DE folder for {vimm_cat} should be lowercase: {mapping.esde_folder}"
            )
    
    def test_common_systems_are_mapped(self) -> None:
        """Common gaming systems should have mappings."""
        expected_systems = [
            "NES", "SNES", "N64", "GameCube", "Wii",
            "Genesis", "Saturn", "Dreamcast",
            "PlayStation", "PS2", "PSP",
            "Xbox", "Xbox 360",
            "Game Boy", "GBA", "DS",
        ]
        for system in expected_systems:
            assert system in VIMM_TO_ESDE_MAPPING, f"Missing mapping for {system}"


class TestESDECompatibilityService:
    """Tests for ESDECompatibilityService."""
    
    @pytest.fixture
    def service(self, tmp_path: Path) -> ESDECompatibilityService:
        """Create a service instance with a temp directory."""
        return ESDECompatibilityService(tmp_path)
    
    def test_get_esde_folder_known_system(self, service: ESDECompatibilityService) -> None:
        """Known systems should return correct ES-DE folder names."""
        assert service.get_esde_folder("PlayStation") == "psx"
        assert service.get_esde_folder("PS2") == "ps2"
        assert service.get_esde_folder("GameCube") == "gc"
        assert service.get_esde_folder("Nintendo 64") == "n64"
        assert service.get_esde_folder("Xbox") == "xbox"
    
    def test_get_esde_folder_unknown_system(self, service: ESDECompatibilityService) -> None:
        """Unknown systems should return a sanitized fallback folder name."""
        result = service.get_esde_folder("Unknown System")
        assert result == "unknown_system"
        assert result.islower()
    
    def test_get_system_mapping_known(self, service: ESDECompatibilityService) -> None:
        """Known systems should return full mapping."""
        mapping = service.get_system_mapping("PlayStation")
        assert mapping is not None
        assert mapping.esde_folder == "psx"
        assert mapping.full_name == "Sony PlayStation"
    
    def test_get_system_mapping_unknown(self, service: ESDECompatibilityService) -> None:
        """Unknown systems should return None."""
        mapping = service.get_system_mapping("Unknown System")
        assert mapping is None


class TestFilenameSanitization:
    """Tests for filename sanitization."""
    
    @pytest.fixture
    def service(self, tmp_path: Path) -> ESDECompatibilityService:
        """Create a service instance."""
        return ESDECompatibilityService(tmp_path)
    
    def test_sanitize_simple_title(self, service: ESDECompatibilityService) -> None:
        """Simple titles should remain unchanged."""
        assert service.sanitize_filename("Super Mario Bros") == "Super Mario Bros"
    
    def test_sanitize_removes_invalid_chars(self, service: ESDECompatibilityService) -> None:
        """Invalid filesystem characters should be replaced."""
        result = service.sanitize_filename('Game: The "Best" One?')
        assert ":" not in result
        assert '"' not in result
        assert "?" not in result
    
    def test_sanitize_preserves_region_tags(self, service: ESDECompatibilityService) -> None:
        """Region tags in parentheses should be preserved."""
        result = service.sanitize_filename("Game Name (USA)")
        assert "(USA)" in result
    
    def test_sanitize_collapses_spaces(self, service: ESDECompatibilityService) -> None:
        """Multiple spaces should be collapsed."""
        result = service.sanitize_filename("Game   Name")
        assert "   " not in result
    
    def test_sanitize_strips_dots(self, service: ESDECompatibilityService) -> None:
        """Leading/trailing dots should be stripped."""
        result = service.sanitize_filename("...Game Name...")
        assert not result.startswith(".")
        assert not result.endswith(".")
    
    def test_sanitize_empty_returns_default(self, service: ESDECompatibilityService) -> None:
        """Empty titles should return a default name."""
        result = service.sanitize_filename("")
        assert result == "Unknown Game"
    
    @given(st.text(min_size=1, max_size=300))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_sanitize_always_returns_valid_filename(
        self, service: ESDECompatibilityService, title: str
    ) -> None:
        """Sanitized filenames should always be valid."""
        result = service.sanitize_filename(title)
        
        # Should not be empty
        assert result
        
        # Should not exceed max length
        assert len(result) <= 200
        
        # Should not contain invalid characters
        invalid_chars = set('\\/:*?"<>|')
        assert not any(c in result for c in invalid_chars)
        
        # Should not start or end with dots or spaces
        assert not result.startswith(".")
        assert not result.endswith(".")
        assert not result.startswith(" ")
        assert not result.endswith(" ")


class TestRomPathGeneration:
    """Tests for ROM path generation."""
    
    @pytest.fixture
    def service(self, tmp_path: Path) -> ESDECompatibilityService:
        """Create a service instance."""
        return ESDECompatibilityService(tmp_path)
    
    def test_generate_rom_path_single_disc(
        self, service: ESDECompatibilityService, tmp_path: Path
    ) -> None:
        """Single disc games should not have disc suffix."""
        path = service.generate_rom_path(
            vimm_category="PlayStation",
            game_title="Final Fantasy VII",
            disc_number="Single Disc",
            extension=".chd",
        )
        
        assert path.parent == tmp_path / "psx"
        assert path.name == "Final Fantasy VII.chd"
    
    def test_generate_rom_path_multi_disc(
        self, service: ESDECompatibilityService, tmp_path: Path
    ) -> None:
        """Multi-disc games should have disc suffix."""
        path = service.generate_rom_path(
            vimm_category="PlayStation",
            game_title="Final Fantasy VII",
            disc_number="Disc 2",
            extension=".chd",
        )
        
        assert path.parent == tmp_path / "psx"
        assert path.name == "Final Fantasy VII (Disc 2).chd"
    
    def test_generate_rom_path_adds_extension_dot(
        self, service: ESDECompatibilityService, tmp_path: Path
    ) -> None:
        """Extension without dot should have dot added."""
        path = service.generate_rom_path(
            vimm_category="N64",
            game_title="Mario 64",
            extension="z64",
        )
        
        assert path.suffix == ".z64"
    
    def test_generate_extraction_directory(
        self, service: ESDECompatibilityService, tmp_path: Path
    ) -> None:
        """Extraction directory should be the system folder."""
        extract_dir = service.generate_extraction_directory(
            vimm_category="GameCube",
            game_title="Some Game",
        )
        
        assert extract_dir == tmp_path / "gc"
    
    def test_get_expected_extensions_known_system(
        self, service: ESDECompatibilityService
    ) -> None:
        """Known systems should return their expected extensions."""
        extensions = service.get_expected_extensions("PlayStation")
        assert ".chd" in extensions
        assert ".cue" in extensions
    
    def test_get_expected_extensions_unknown_system(
        self, service: ESDECompatibilityService
    ) -> None:
        """Unknown systems should return default extensions."""
        extensions = service.get_expected_extensions("Unknown")
        assert ".zip" in extensions
        assert ".7z" in extensions


class TestSupportedSystems:
    """Tests for supported systems list."""
    
    def test_get_supported_systems_returns_list(self) -> None:
        """Should return a list of supported system names."""
        systems = ESDECompatibilityService.get_supported_systems()
        assert isinstance(systems, list)
        assert len(systems) > 0
    
    def test_get_supported_systems_contains_common_systems(self) -> None:
        """Should contain common gaming systems."""
        systems = ESDECompatibilityService.get_supported_systems()
        assert "PlayStation" in systems
        assert "N64" in systems
        assert "GameCube" in systems
