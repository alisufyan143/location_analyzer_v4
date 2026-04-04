import re
from typing import Dict, Optional

class BrandMatcher:
    """
    Utility to map user-provided branch names to the production V4 model's 
    Inferred_Brand categorical IDs.
    
    The V4 model expects integers (1-7) for known high-volume brands, 
    and -1/0 for Generic/Unknown.
    """
    
    # Standard UK Brand Mapping (Production calibrated to training strings)
    BRAND_MAP = {
        "mcdonalds": "McDonald's",
        "mcd": "McDonald's",
        "kfc": "KFC",
        "kentucky fried": "KFC",
        "burger king": "Burger King",
        "bk": "Burger King",
        "maemes": "Maeme's",
        "maeme": "Maeme's",
        "pepes": "Pepe's",
        "pepe's": "Pepe's",
        "rios": "Rio's",
        "rio's": "Rio's",
        "subway": "Subway",
    }

    @staticmethod
    def get_brand_id(branch_name: str) -> str:
        """
        Extracts and maps the brand name from a branch name.
        V4 model expects strings matching its categorical training keys.
        """
        if not branch_name:
            return "Independent"

        name_clean = branch_name.lower()
        
        for brand_key, brand_name in BrandMatcher.BRAND_MAP.items():
            if brand_key in name_clean:
                return brand_name
                
        return "Independent"
