"""
General Commodity Classifier for LMPC 2011 Compliance.
Determines whether a packaged commodity is a consumable / perishable article
(requiring Expiry / Best Before under Rule 6(1)(da)) or a durable non-consumable.
"""

from typing import Dict, Any, List, Optional
import re


CONSUMABLE_CATEGORIES = {
    "food", "beverage", "beverages", "dairy", "snacks", "bakery", "confectionery",
    "grocery", "edible oil", "spices", "condiments", "tea", "coffee", "juice",
    "supplements", "pharmaceutical", "medicine", "drugs", "cosmetic", "cosmetics",
    "personal care", "skincare", "haircare", "ayurvedic", "health", "packaged water"
}

NON_CONSUMABLE_CATEGORIES = {
    "book", "stationery", "electronics", "hardware", "apparel", "clothing",
    "footwear", "toys", "utensils", "appliances", "furniture", "tools",
    "automotive parts", "textile", "sports goods"
}

CONSUMABLE_KEYWORDS = [
    r"\b(food|beverage|drink|milk|lassi|biscuit|snack|oil|juice|tea|coffee|curd|paneer|chocolate|candy)\b",
    r"\b(ingredients?|nutritional|serving\s*size|energy\s*\(?kcal\)?|carbohydrate|sugar|fat|protein)\b",
    r"\b(fssai|lic\.?\s*no|taste|chill|edible|vegetarian|non-vegetarian)\b",
    r"\b(flavor|flavoured|recipe|diet|preservative|culture|syrup|tablet|capsule|ointment|lotion|shampoo|soap)\b"
]

NON_CONSUMABLE_KEYWORDS = [
    r"\b(pages?|isbn|publisher|author|edition|paperback|hardcover)\b",
    r"\b(voltage|watt|battery|usb|warranty|serial\s*no|device|cotton|polyester|size:\s*(s|m|l|xl|xxl))\b"
]


class CommodityProfile:
    """Classified profile of a packaged commodity."""
    def __init__(
        self,
        is_consumable: bool,
        confidence: float,
        detected_category: str,
        fssai_present: bool,
        has_ingredients: bool,
        has_nutritional_facts: bool,
        classification_rationale: str
    ):
        self.is_consumable = is_consumable
        self.confidence = confidence
        self.detected_category = detected_category
        self.fssai_present = fssai_present
        self.has_ingredients = has_ingredients
        self.has_nutritional_facts = has_nutritional_facts
        self.classification_rationale = classification_rationale

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_consumable": self.is_consumable,
            "confidence": self.confidence,
            "detected_category": self.detected_category,
            "fssai_present": self.fssai_present,
            "has_ingredients": self.has_ingredients,
            "has_nutritional_facts": self.has_nutritional_facts,
            "classification_rationale": self.classification_rationale
        }


def classify_commodity(
    category: Optional[str] = None,
    product_name: Optional[str] = None,
    ingredients: Optional[List[str]] = None,
    nutrients: Optional[List[Dict[str, Any]]] = None,
    fssai_number: Optional[str] = None,
    raw_ocr_lines: Optional[List[str]] = None,
    full_text: Optional[str] = None
) -> CommodityProfile:
    """
    Deterministically determines if the packaged product is a consumable/perishable item.
    Generalised across all commodity kinds (Food, Beverages, Drugs, Cosmetics, Stationary, Books, Electronics, etc.).
    """
    reasons = []
    consumable_signals = 0
    non_consumable_signals = 0

    cat_lower = (category or "").lower().strip()
    if cat_lower:
        if any(c in cat_lower for c in CONSUMABLE_CATEGORIES):
            consumable_signals += 3
            reasons.append(f"Category explicitly marked as consumable: '{category}'")
        elif any(c in cat_lower for c in NON_CONSUMABLE_CATEGORIES):
            non_consumable_signals += 3
            reasons.append(f"Category explicitly marked as non-consumable: '{category}'")

    # FSSAI License presence
    has_fssai = bool(fssai_number and str(fssai_number).strip().lower() not in ("null", "none", ""))
    if has_fssai:
        consumable_signals += 3
        reasons.append(f"FSSAI license detected: {fssai_number}")

    # Ingredients presence
    has_ing = bool(ingredients and len(ingredients) > 0)
    if has_ing:
        consumable_signals += 2
        reasons.append(f"Ingredients list detected ({len(ingredients)} items)")

    # Nutritional information presence
    has_nutr = bool(nutrients and len(nutrients) > 0)
    if has_nutr:
        consumable_signals += 2
        reasons.append(f"Nutritional facts table detected ({len(nutrients)} nutrients)")

    # Text pattern analysis
    search_corpus = f"{category or ''} {product_name or ''} {full_text or ''} {' '.join(raw_ocr_lines or [])}".lower()

    for pat in CONSUMABLE_KEYWORDS:
        if re.search(pat, search_corpus, re.IGNORECASE):
            consumable_signals += 1

    for pat in NON_CONSUMABLE_KEYWORDS:
        if re.search(pat, search_corpus, re.IGNORECASE):
            non_consumable_signals += 1

    is_consumable = consumable_signals >= non_consumable_signals and (consumable_signals > 0 or non_consumable_signals == 0)
    
    if not reasons:
        if is_consumable:
            reasons.append("Identified food/consumable characteristics in text content.")
        else:
            reasons.append("Identified non-perishable/durable characteristics in text content.")

    return CommodityProfile(
        is_consumable=is_consumable,
        confidence=0.95 if (consumable_signals >= 3 or non_consumable_signals >= 3) else 0.80,
        detected_category=category or ("Consumable Commodity" if is_consumable else "Durable / Non-Consumable Commodity"),
        fssai_present=has_fssai,
        has_ingredients=has_ing,
        has_nutritional_facts=has_nutr,
        classification_rationale="; ".join(reasons)
    )
