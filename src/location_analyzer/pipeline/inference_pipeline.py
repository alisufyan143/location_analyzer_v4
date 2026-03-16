import logging
import asyncio
from typing import Dict, Any

from location_analyzer.data.united_resolver import UnitedResolver

logger = logging.getLogger(__name__)

class InferencePipeline:
    """Orchestrates 100% Offline UK-wide feature resolution and display assembly."""
    
    def __init__(self):
        # Scrapers decomissioned (Architectural Shift: Zero Scraper)
        # Offline-first UK resolver (handles England, Wales, Scotland, NI)
        self.united_resolver = UnitedResolver()

    def _get_outercode(self, postcode: str) -> str:
        """Extracts the outercode from a standard UK format postcode."""
        return postcode.strip().split()[0].upper()

    def run(self, postcode: str) -> Dict[str, Any]:
        """
        100% Offline Feature resolution pipeline for one postcode.
        Bypasses all external scrapers using the local UK Master DB.
        """
        postcode = postcode.strip().upper()
        outercode = self._get_outercode(postcode)

        logger.info(
            "\n"
            "┌──────────────────────────────────────────────────────────┐\n"
            "│  INFERENCE PIPELINE START (ZERO SCRAPER)   %-14s│\n"
            "└──────────────────────────────────────────────────────────┘",
            postcode,
        )

        # ── OFFLINE-ONLY RESOLUTION (UnitedResolver) ────────────────────────
        logger.info("  [OFFLINE] Resolving Features from Master UK Database...")
        features = self.united_resolver.get_features(postcode)

        if not features or features.get("population", 0) == 0:
            logger.error("  [OFFLINE] ❌ Failed: No demographic coverage for %s", postcode)
            return {}

        logger.info("  [OFFLINE] ✅ Success! Features resolved.")

        # coordinates are already in features from UnitedResolver
        if "lat" not in features or "lng" not in features:
            logger.warning("  [OFFLINE] ⚠ Lat/Lng missing from Master DB for %s", postcode)
        else:
            logger.info("  [OFFLINE] Using high-fidelity coordinates from Master DB.")

        # Build display data for frontend panels (Amenities, Occupation, Affluence)
        logger.info("  [OFFLINE] Assembling Display Data...")
        features["_display"] = self.united_resolver.get_display_data(postcode)

        logger.info(
            "\n"
            "┌──────────────────────────────────────────────────────────┐\n"
            "│  INFERENCE PIPELINE COMPLETE (100% OFFLINE)              │\n"
            "└──────────────────────────────────────────────────────────┘\n"
        )
        return features
