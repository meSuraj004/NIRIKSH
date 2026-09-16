"""
Deterministic Price and Currency Parsing Utilities for LMPC 2011 Compliance.
Handles detection of MRP prefixes, currency symbols, tax inclusion clauses, numeric values, rounding, and Unit Sale Price (USP).
"""

import re
from typing import Optional, Dict, Any, Tuple


class ParsedPrice:
    """Structured representation of a parsed price declaration."""
    def __init__(
        self,
        raw_text: str,
        numeric_value: Optional[float] = None,
        currency: Optional[str] = None,
        has_mrp_prefix: bool = False,
        has_tax_declaration: bool = False,
        has_valid_currency: bool = False,
        is_rounded_properly: bool = False,
        unit_sale_price_raw: Optional[str] = None,
        unit_sale_price_val: Optional[float] = None,
        unit_sale_price_unit: Optional[str] = None
    ):
        self.raw_text = raw_text
        self.numeric_value = numeric_value
        self.currency = currency
        self.has_mrp_prefix = has_mrp_prefix
        self.has_tax_declaration = has_tax_declaration
        self.has_valid_currency = has_valid_currency
        self.is_rounded_properly = is_rounded_properly
        self.unit_sale_price_raw = unit_sale_price_raw
        self.unit_sale_price_val = unit_sale_price_val
        self.unit_sale_price_unit = unit_sale_price_unit

    def __repr__(self) -> str:
        return (
            f"<ParsedPrice ₹{self.numeric_value} (prefix={self.has_mrp_prefix}, "
            f"taxes={self.has_tax_declaration}, curr={self.currency})>"
        )


MRP_PREFIX_REGEX = re.compile(
    r"\b(m\.?r\.?p\.?|maximum\s+retail\s+price|max\.?\s+retail\s+price|max\s+mrp)\b",
    re.IGNORECASE
)

TAX_INCLUSION_REGEX = re.compile(
    r"(incl(?:usive)?\.?\s+(?:of\s+)?all\s+taxes|inclusive\s+of\s+taxes|incl\.?\s+taxes|\(incl\.?\s+of\s+all\s+taxes\)|\(inclusive\s+of\s+all\s+taxes\))",
    re.IGNORECASE
)

CURRENCY_REGEX = re.compile(
    r"(₹|rs\.?|inr|rupees)",
    re.IGNORECASE
)

PRICE_NUMERIC_REGEX = re.compile(
    r"(?:₹|rs\.?|inr)?\s*([0-9]+(?:\.[0-9]{1,2})?)(?:\s*/-|\s*per|\s*\(|$|\s)",
    re.IGNORECASE
)

USP_REGEX = re.compile(
    r"(?:unit\s+sale\s+price|usp)\s*(?:per\s*([a-zA-Z]+))?\s*[:\-]?\s*(?:₹|rs\.?|inr)?\s*([0-9]+(?:\.[0-9]{1,4})?)(?:\s*(?:per|/)\s*([a-zA-Z]+))?",
    re.IGNORECASE
)


def is_properly_rounded(amount: float) -> bool:
    """
    Checks if price in rupees and paise is rounded off to the nearest rupee or 50 paise (Rule 6(1)(e)).
    e.g. 30.00, 30.50, 30 -> True
    30.33, 30.17 -> False (or warning)
    """
    paise = round((amount - int(amount)) * 100)
    return paise in (0, 50, 100)


def parse_mrp_declaration(mrp_str: Optional[str], fallback_lines: Optional[list] = None) -> Optional[ParsedPrice]:
    """
    Deterministically parses an MRP declaration string and checks all LMPC 2011 compliance criteria.
    """
    if not mrp_str and not fallback_lines:
        return None

    # "No MRP printed" style lines must not satisfy the prefix scan, and a
    # number from an unrelated line (e.g. net weight) must never be adopted
    # as the price just because the word MRP appears somewhere.
    no_mrp_regex = re.compile('(?i)\\bno\\s+mrp\\b')
    usable_lines = [ln for ln in (fallback_lines or []) if not no_mrp_regex.search(ln)]
    fallback_context = " ".join(usable_lines)
    prefix_in_fallback = any(MRP_PREFIX_REGEX.search(ln) for ln in usable_lines)

    if mrp_str:
        full_context = f"{mrp_str} {fallback_context}".strip()
    elif prefix_in_fallback:
        full_context = fallback_context
    else:
        return None

    # Prefix check
    has_prefix = bool(MRP_PREFIX_REGEX.search(full_context))

    # Tax declaration check
    has_tax = bool(TAX_INCLUSION_REGEX.search(full_context))

    # Currency symbol check
    has_currency = bool(CURRENCY_REGEX.search(full_context))
    currency_match = CURRENCY_REGEX.search(full_context)
    curr_str = currency_match.group(0) if currency_match else None

    # Numeric extraction
    # Try searching after MRP prefix first
    num_val = None
    mrp_after = None
    m = MRP_PREFIX_REGEX.search(full_context)
    if m:
        sub = full_context[m.start():]
        num_m = re.search(r"(?:₹|rs\.?|inr)?\s*([0-9]+(?:\.[0-9]{1,2})?)", sub, re.IGNORECASE)
        if num_m:
            try:
                num_val = float(num_m.group(1))
            except ValueError:
                pass

    if num_val is None:
        num_m = PRICE_NUMERIC_REGEX.search(full_context)
        if num_m:
            try:
                num_val = float(num_m.group(1))
            except ValueError:
                pass

    rounded = is_properly_rounded(num_val) if num_val is not None else False

    # Unit Sale Price (USP) extraction
    usp_raw = None
    usp_val = None
    usp_unit = None
    usp_match = USP_REGEX.search(full_context)
    if usp_match:
        usp_raw = usp_match.group(0)
        u1, v, u2 = usp_match.group(1), usp_match.group(2), usp_match.group(3)
        usp_unit = u1 or u2 or "unit"
        try:
            usp_val = float(v)
        except (ValueError, TypeError):
            pass

    return ParsedPrice(
        raw_text=mrp_str or full_context,
        numeric_value=num_val,
        currency=curr_str,
        has_mrp_prefix=has_prefix,
        has_tax_declaration=has_tax,
        has_valid_currency=has_currency,
        is_rounded_properly=rounded,
        unit_sale_price_raw=usp_raw,
        unit_sale_price_val=usp_val,
        unit_sale_price_unit=usp_unit
    )
