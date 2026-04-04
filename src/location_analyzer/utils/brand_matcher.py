import re
from typing import Dict, Optional

class BrandMatcher:
    """
    Utility to map user-provided branch names to the production V4 model's 
    Inferred_Brand categorical IDs.
    
    The V4 model expects integers (1-7) for known high-volume brands, 
    and -1/0 for Generic/Unknown.
    """
    
    # Standard UK Brand Mapping (Production calibrated)
    # Order: McDonalds, KFC, Burger King, Maemes, Pepes, Rios, Subway
    BRAND_MAP = {
        "mcdonalds": 1,
        "mcd": 1,
        "kfc": 2,
        "kentucky fried": 2,
        "burger king": 3,
        "bk": 3,
        "maemes": 4,
        "maeme": 4,
        "pepes": 5,
        "pepe's": 5,
        "rios": 6,
        "rio's": 6,
        "subway": 7,
    }

    @staticmethod
    def get_brand_id(branch_name: str) -> int:
        """
        Extracts and maps the brand ID from a branch name.
        Example: "Maeme's - London" -> 4
        """
        if not branch_name:
            return -1 # Generic

        name_clean = branch_name.lower()
        
        # Exact match or substring match for known brands
        for brand, brand_id in BrandMatcher.BRAND_MAP.items():
            if brand in name_clean:
                return brand_id
                
        return -1 # Generic / Unknown
