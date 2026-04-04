import re
from typing import Dict, Optional

class BrandMatcher:
    """
    Utility to map user-provided branch names to the production V4 model's 
    Inferred_Brand categorical IDs.
    
    The V4 model expects integers (1-7) for known high-volume brands, 
    and -1/0 for Generic/Unknown.
    """
    
    # Standard Production Brand Mapping (V4 TargetEncoder Calibrated)
    # Punctuation and spacing MUST match exactly.
    BRAND_MAP = {
        "pepe": "Pepe's",
        "rio": "Rio's",
        "maeme": "Maeme's",
        "galo": "Galos",
        "grill peri": "Grill Peri Peri",
        "grillo": "Grillo",
        "jojo": "Jojo's",
    }

    @staticmethod
    def get_brand_id(branch_name: str) -> str:
        """
        Extracts and maps the brand string from a branch name.
        Example: "Maeme's Piri Piri - London" -> "Maeme's"
        """
        if not branch_name:
            return "Unknown"

        name_clean = branch_name.lower()
        
        for key, exact_brand in BrandMatcher.BRAND_MAP.items():
            if key in name_clean:
                return exact_brand
                
        return "Unknown"
