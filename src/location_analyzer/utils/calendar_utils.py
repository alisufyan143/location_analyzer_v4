import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Dict

class CalendarUtility:
    """
    Unified utility for generating the 15 V4 temporal and situational flags.
    Supports historical dates (COVID) and future projections (Ramadan, Eids).
    """
    
    # Accurate Eid/Ramadan dates for 2024-2026 for production forecasting
    HOLIDAY_MAP = {
        2023: {"ramadan": ("2023-03-22", "2023-04-20"), "eid_fitr": "2023-04-21", "eid_adha": "2023-06-28"},
        2024: {"ramadan": ("2024-03-10", "2024-04-08"), "eid_fitr": "2024-04-09", "eid_adha": "2024-06-16"},
        2025: {"ramadan": ("2025-02-28", "2025-03-29"), "eid_fitr": "2025-03-30", "eid_adha": "2025-06-06"},
        2026: {"ramadan": ("2026-02-17", "2026-03-19"), "eid_fitr": "2026-03-20", "eid_adha": "2026-05-26"},
    }

    @staticmethod
    def get_features_for_date(dt: datetime, situational: Dict[str, int] = None) -> Dict[str, int]:
        """
        Generates all V4 temporal flags for a specific datetime.
        situational: Optional overrides for is_logistics_strike, is_delivery_crackdown.
        """
        if situational is None:
            situational = {}

        y, m, d = dt.year, dt.month, dt.day
        day_of_week = dt.weekday() # 0=Mon, 6=Sun
        
        # 1. Standard Calendar Flags
        is_nye = 1 if (m == 12 and d == 31) else 0
        is_nyd = 1 if (m == 1 and d == 1) else 0
        is_christmas = 1 if (m == 12 and d == 25) else 0
        is_boxing_day = 1 if (m == 12 and d == 26) else 0
        is_month_start = 1 if (d == 1) else 0
        
        # 2. Payday Window (25th to end of month)
        is_payday = 1 if d >= 25 else 0
        
        # 3. COVID Lockdown Logic (Historical)
        is_lockdown = 0
        # Main UK Lockdowns: 2020-03-23 to 2020-07-04, 2020-11-05 to 2020-12-02, 2021-01-04 to 2021-07-19
        if (date(2020, 3, 23) <= dt.date() <= date(2020, 7, 4)) or \
           (date(2020, 11, 5) <= dt.date() <= date(2020, 12, 2)) or \
           (date(2021, 1, 4) <= dt.date() <= date(2021, 7, 19)):
            is_lockdown = 1

        # 4. Islamic Holidays
        is_ramadan = 0
        is_fitr = 0
        is_adha = 0
        
        if y in CalendarUtility.HOLIDAY_MAP:
            h = CalendarUtility.HOLIDAY_MAP[y]
            # Ramadan check
            r_start = datetime.strptime(h["ramadan"][0], "%Y-%m-%d").date()
            r_end = datetime.strptime(h["ramadan"][1], "%Y-%m-%d").date()
            if r_start <= dt.date() <= r_end:
                is_ramadan = 1
            
            # Eid Fitr
            if dt.date() == datetime.strptime(h["eid_fitr"], "%Y-%m-%d").date():
                is_fitr = 1
            
            # Eid Adha
            if dt.date() == datetime.strptime(h["eid_adha"], "%Y-%m-%d").date():
                is_adha = 1
        
        # 5. Situational Flags (Strike / Crackdown)
        # Default to 0 unless specifically provided in the request
        is_strike = situational.get("is_logistics_strike", 0)
        is_crackdown = situational.get("is_delivery_crackdown", 0)

        return {
            "is_logistics_strike": is_strike,
            "is_delivery_crackdown": is_crackdown,
            "is_payday_window": is_payday,
            "is_NYE": is_nye,
            "is_NYD": is_nyd,
            "is_Christmas": is_christmas,
            "is_month_start": is_month_start,
            "is_ramadan": is_ramadan,
            "is_eid_al_fitr": is_fitr,
            "is_eid_al_adha": is_adha,
            "is_Boxing_Day": is_boxing_day,
            "is_covid_lockdown": is_lockdown,
            "Month": m,
            "DayOfMonth": d,
            "DayOfWeek": day_of_week
        }
