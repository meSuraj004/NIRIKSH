"""
Deterministic Date Parsing and Validation Utilities.
Handles various date formats on packaged commodity labels (MFD, PKD, EXP, USE BY, BEST BEFORE).
"""

import re
from datetime import datetime, date
from typing import Optional, Tuple, Dict, Any


MONTH_NAMES = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9, "sept": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12
}


class ParsedDate:
    """Structured representation of a parsed label date."""
    def __init__(
        self,
        raw_text: str,
        year: int,
        month: int,
        day: Optional[int] = None,
        has_day: bool = False,
        period_months: Optional[int] = None,
        period_days: Optional[int] = None,
        is_period_declaration: bool = False
    ):
        self.raw_text = raw_text
        self.year = year
        self.month = month
        self.day = day if day else 1
        self.has_day = has_day
        self.period_months = period_months
        self.period_days = period_days
        self.is_period_declaration = is_period_declaration

    @property
    def as_date(self) -> date:
        return date(self.year, self.month, self.day)

    @property
    def formatted_iso(self) -> str:
        if self.has_day:
            return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
        return f"{self.year:04d}-{self.month:02d}"

    def __repr__(self) -> str:
        return f"<ParsedDate {self.formatted_iso} (has_day={self.has_day})>"


def clean_date_string(text: str) -> str:
    """Cleans common OCR noise in date declarations."""
    if not text:
        return ""
    cleaned = text.strip()
    # Strip common leading labels
    cleaned = re.sub(r"^(mfg|mfd|pkd|packed|exp|expiry|use\s*by|best\s*before|date)[\s.:\-=]+", "", cleaned, flags=re.IGNORECASE)
    # Strip time part if present (e.g. 15/06/26 07:20:52 -> 15/06/26)
    cleaned = re.sub(r"\s+\d{1,2}:\d{2}(:\d{2})?", "", cleaned)
    return cleaned.strip()


def parse_label_date(date_str: Optional[str]) -> Optional[ParsedDate]:
    """
    Deterministically parses a date string found on packaged commodity labels into a ParsedDate object.
    Supports:
      - DD/MM/YYYY, DD/MM/YY, DD-MM-YYYY, DD-MM-YY, DD.MM.YYYY, DD.MM.YY
      - MM/YYYY, MM/YY, MM-YYYY, MM-YY
      - DD MMM YYYY, MMM YYYY, Month YYYY, DD-MMM-YY
      - Period declarations: 'Best before 6 months from manufacture/pkd'
    """
    if not date_str or not isinstance(date_str, str):
        return None

    cleaned = clean_date_string(date_str)
    if not cleaned:
        return None

    # Check for relative period declaration e.g. "6 months", "180 days", "9 months from pkd"
    period_month_match = re.search(r"(\d+)\s*(months?|mths?|mo)\b", cleaned, re.IGNORECASE)
    if period_month_match:
        months_val = int(period_month_match.group(1))
        return ParsedDate(
            raw_text=date_str,
            year=0,
            month=0,
            period_months=months_val,
            is_period_declaration=True
        )

    period_day_match = re.search(r"(\d+)\s*(days?)\b", cleaned, re.IGNORECASE)
    if period_day_match:
        days_val = int(period_day_match.group(1))
        return ParsedDate(
            raw_text=date_str,
            year=0,
            month=0,
            period_days=days_val,
            is_period_declaration=True
        )

    # 1. Pattern: DD/MM/YYYY or DD/MM/YY (or with - or .)
    m = re.search(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b", cleaned)
    if m:
        p1, p2, p3 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Resolve year
        year = p3 if p3 >= 1000 else (2000 + p3 if p3 < 70 else 1900 + p3)
        # Determine day vs month
        if p1 > 12 and 1 <= p2 <= 12:
            day, month = p1, p2
        elif p2 > 12 and 1 <= p1 <= 12:
            month, day = p1, p2
        elif 1 <= p1 <= 31 and 1 <= p2 <= 12:
            # Default Indian / UK convention: DD/MM/YYYY
            day, month = p1, p2
        else:
            return None
        
        try:
            d = date(year, month, day)
            return ParsedDate(raw_text=date_str, year=year, month=month, day=day, has_day=True)
        except ValueError:
            return None

    # 2. Pattern: MM/YYYY or MM/YY (or with - or .)
    m = re.search(r"\b(\d{1,2})[\/\-\.](\d{2,4})\b", cleaned)
    if m:
        p1, p2 = int(m.group(1)), int(m.group(2))
        year = p2 if p2 >= 1000 else (2000 + p2 if p2 < 70 else 1900 + p2)
        if 1 <= p1 <= 12:
            month = p1
            return ParsedDate(raw_text=date_str, year=year, month=month, has_day=False)

    # 3. Pattern: Named Month with Year e.g. "JUN 2026", "15 JUN 2026", "June 26", "15-DEC-26"
    words_pattern = r"\b(?:(\d{1,2})[\s\-\/]?)?([A-Za-z]{3,9})[\s\-\/]?(\d{2,4})\b"
    m = re.search(words_pattern, cleaned)
    if m:
        day_str, month_str, year_str = m.group(1), m.group(2).lower(), m.group(3)
        month = MONTH_NAMES.get(month_str[:3]) or MONTH_NAMES.get(month_str)
        if month:
            y_val = int(year_str)
            year = y_val if y_val >= 1000 else (2000 + y_val if y_val < 70 else 1900 + y_val)
            day = int(day_str) if day_str else None
            has_day = bool(day)
            try:
                if day:
                    date(year, month, day)
                else:
                    date(year, month, 1)
                return ParsedDate(raw_text=date_str, year=year, month=month, day=day, has_day=has_day)
            except ValueError:
                return None

    return None


def calculate_shelf_life_days(mfg_date: ParsedDate, exp_date: ParsedDate) -> Optional[int]:
    """Computes difference in days between manufacturing date and expiry date."""
    if not mfg_date or not exp_date:
        return None
    if mfg_date.is_period_declaration:
        return None
    if exp_date.is_period_declaration:
        if exp_date.period_months:
            return exp_date.period_months * 30
        if exp_date.period_days:
            return exp_date.period_days
        return None

    d1 = mfg_date.as_date
    d2 = exp_date.as_date
    delta = (d2 - d1).days
    return delta


def is_date_chronologically_valid(mfg_date: ParsedDate, exp_date: ParsedDate) -> Tuple[bool, str]:
    """
    Checks if Expiry Date is on or after Manufacturing Date.
    Returns (is_valid, reason).
    """
    if exp_date.is_period_declaration:
        # Period declaration (e.g. 'best before 6 months') is inherently forward-looking and valid
        return True, f"Relative expiry duration declared: {exp_date.period_months or exp_date.period_days} units."

    delta_days = calculate_shelf_life_days(mfg_date, exp_date)
    if delta_days is None:
        return False, "Unable to compute calendar delta between MFD and EXP."

    if delta_days < 0:
        return False, f"Expiry date ({exp_date.formatted_iso}) is prior to Manufacturing date ({mfg_date.formatted_iso}) by {abs(delta_days)} days."

    return True, f"Expiry date ({exp_date.formatted_iso}) is {delta_days} days after Manufacturing date ({mfg_date.formatted_iso})."
