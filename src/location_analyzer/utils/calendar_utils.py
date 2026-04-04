import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Dict

class CalendarUtility:
    """
    Unified utility for generating the 15 V4 temporal and situational flags.
    Supports historical dates (COVID) and future projections (Ramadan, Eids).
    """
    
    # Accurate Eid/Ramadan dates for historical backtesting and future forecasting
    HOLIDAY_MAP = {
        2010: {"ramadan": [("2010-08-11", "2010-09-09")], "eid_fitr": ["2010-09-10"], "eid_adha": ["2010-11-16"]},
        2011: {"ramadan": [("2011-08-01", "2011-08-30")], "eid_fitr": ["2011-08-31"], "eid_adha": ["2011-11-06"]},
        2012: {"ramadan": [("2012-07-20", "2012-08-18")], "eid_fitr": ["2012-08-19"], "eid_adha": ["2012-10-26"]},
        2013: {"ramadan": [("2013-07-09", "2013-08-07")], "eid_fitr": ["2013-08-08"], "eid_adha": ["2013-10-15"]},
        2014: {"ramadan": [("2014-06-28", "2014-07-27")], "eid_fitr": ["2014-07-28"], "eid_adha": ["2014-10-04"]},
        2015: {"ramadan": [("2015-06-18", "2015-07-16")], "eid_fitr": ["2015-07-17"], "eid_adha": ["2015-09-23"]},
        2016: {"ramadan": [("2016-06-06", "2016-07-05")], "eid_fitr": ["2016-07-06"], "eid_adha": ["2016-09-12"]},
        2017: {"ramadan": [("2017-05-27", "2017-06-24")], "eid_fitr": ["2017-06-25"], "eid_adha": ["2017-09-01"]},
        2018: {"ramadan": [("2018-05-16", "2018-06-14")], "eid_fitr": ["2018-06-15"], "eid_adha": ["2018-08-21"]},
        2019: {"ramadan": [("2019-05-05", "2019-06-03")], "eid_fitr": ["2019-06-04"], "eid_adha": ["2019-08-11"]},
        2020: {"ramadan": [("2020-04-23", "2020-05-22")], "eid_fitr": ["2020-05-23"], "eid_adha": ["2020-07-31"]},
        2021: {"ramadan": [("2021-04-12", "2021-05-11")], "eid_fitr": ["2021-05-12"], "eid_adha": ["2021-07-20"]},
        2022: {"ramadan": [("2022-04-01", "2022-04-30")], "eid_fitr": ["2022-05-02"], "eid_adha": ["2022-07-09"]},
        2023: {"ramadan": [("2023-03-22", "2023-04-20")], "eid_fitr": ["2023-04-21"], "eid_adha": ["2023-06-28"]},
        2024: {"ramadan": [("2024-03-10", "2024-04-08")], "eid_fitr": ["2024-04-09"], "eid_adha": ["2024-06-16"]},
        2025: {"ramadan": [("2025-02-28", "2025-03-29")], "eid_fitr": ["2025-03-30"], "eid_adha": ["2025-06-06"]},
        2026: {"ramadan": [("2026-02-17", "2026-03-19")], "eid_fitr": ["2026-03-20"], "eid_adha": ["2026-05-26"]},
        2027: {"ramadan": [("2027-02-08", "2027-03-08")], "eid_fitr": ["2027-03-09"], "eid_adha": ["2027-05-16"]},
        2028: {"ramadan": [("2028-01-28", "2028-02-26")], "eid_fitr": ["2028-02-27"], "eid_adha": ["2028-05-05"]},
        2029: {"ramadan": [("2029-01-16", "2029-02-14")], "eid_fitr": ["2029-02-15"], "eid_adha": ["2029-04-24"]},
        2030: {
            "ramadan": [("2030-01-05", "2030-02-03"), ("2030-12-25", "2030-12-31")], 
            "eid_fitr": ["2030-02-04"], 
            "eid_adha": ["2030-04-13"]
        },
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
            # Ramadan check (Looping through multiple possible ranges per year)
            for r_range in h.get("ramadan", []):
                r_start = datetime.strptime(r_range[0], "%Y-%m-%d").date()
                r_end = datetime.strptime(r_range[1], "%Y-%m-%d").date()
                if r_start <= dt.date() <= r_end:
                    is_ramadan = 1
                    break
            
            # Eid Fitr (Looping through list)
            for e_date in h.get("eid_fitr", []):
                if dt.date() == datetime.strptime(e_date, "%Y-%m-%d").date():
                    is_fitr = 1
                    break
            
            # Eid Adha (Looping through list)
            for e_date in h.get("eid_adha", []):
                if dt.date() == datetime.strptime(e_date, "%Y-%m-%d").date():
                    is_adha = 1
                    break
        
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
