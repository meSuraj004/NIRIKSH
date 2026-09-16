"""
=============================================================================
Product Label Aggregator & Multi-Angle Information Synthesizer
=============================================================================
Module: pipeline.aggregator
Purpose:
  Combines OCR transcripts from multiple packaging images (front, back, sides,
  nutrition panel, batch stamps) using Groq's high-capacity language models.

Synthesizes data into structured legal metrology & regulatory sections:
  1. Product Overview & Identity
  2. Manufacturer & Marketer Details
  3. Dates, Batch & Stamped Information
  4. Pricing, Net Quantity & Weights
  5. Ingredients, Allergens & Additives
  6. Nutritional Facts Table
  7. Regulatory, FSSAI & Quality Certifications
  8. Consumer Care & Contact Information
  9. Compliance Completeness & Missing Fields Flag
=============================================================================
"""

import os
import json
import time
from typing import List, Dict, Any, Optional
from groq import Groq

from app.ai.ocr.key_manager import key_manager, GroqKeyManager
from app.config import settings


PRIMARY_AGGREGATOR_MODEL = settings.aggregator_model
FALLBACK_AGGREGATOR_MODEL = settings.aggregator_fallback_model


AGGREGATOR_SYSTEM_PROMPT = """You are an expert Regulatory Packaging Compliance & Legal Metrology Analyst.
Your task is to take multiple OCR transcripts of a single product (captured from various angles: front, back, side panels, nutrition box, bottom batch stamp) and combine them into a single, unified, highly accurate structured JSON dataset.

Instructions:
1. Reconcile and Deduplicate: Merge matching information across views. If one view has a partial text and another has the complete text, reconstruct the full text accurately.
2. Character Faithfulness: Pay extreme attention to dot-matrix stamped numbers (MFD, EXP, BATCH, MRP), FSSAI license numbers (14 digits), net weights, and ingredient names.
3. Clean JSON Output: Return a strictly valid JSON object matching the exact schema below. Do not wrap with conversational text.
4. If a field is not present or not readable in any of the OCR views, set its value to null or [] (empty list). Do not hallucinate data.
5. Never infer, guess, or complete values (e.g. country of origin, category, prices). Copy values verbatim from the transcripts. If only a fragment is readable, return the fragment verbatim or null.

JSON SCHEMA TO RETURN:
{
  "product_identity": {
    "brand_name": "string or null",
    "product_name": "string or null",
    "variant_flavor": "string or null",
    "category": "string (e.g. Packaged Food, Beverage, Personal Care, Household, Pharmaceutical) or null if not determinable from the text",
    "vegetarian_status": "string (Vegetarian, Non-Vegetarian, or null)"
  },
  "manufacturer_and_marketer": {
    "manufactured_by": "string or null",
    "manufacturing_address": "string or null",
    "marketed_by": "string or null",
    "packed_by": "string or null",
    "imported_by": "string or null",
    "country_of_origin": "string or null"
  },
  "dates_and_batch": {
    "mfg_date": "string or null",
    "exp_date": "string or null",
    "best_before": "string or null",
    "batch_number": "string or null",
    "lot_number": "string or null"
  },
  "pricing_and_quantity": {
    "mrp": "string or null (e.g. ₹50.00 incl. of all taxes)",
    "mrp_numerical_inr": "number or null",
    "net_quantity": "string or null (e.g. 500 ml, 250 g, 10 N)",
    "unit_sale_price": "string or null",
    "gross_weight": "string or null"
  },
  "ingredients_and_allergens": {
    "ingredients_list": ["string"],
    "allergens_declared": ["string"],
    "food_additives_and_ins": ["string"]
  },
  "nutritional_information": {
    "serving_size": "string or null",
    "servings_per_pack": "string or null",
    "nutrients": [
      {
        "name": "string (e.g. Energy, Protein, Carbohydrate, Added Sugars, Total Fat, Sodium)",
        "per_100g_or_ml": "string or null",
        "per_serving": "string or null",
        "rda_percentage": "string or null"
      }
    ]
  },
  "regulatory_and_certifications": {
    "fssai_license_number": "string (14 digits) or null",
    "fssai_logo_present": "boolean",
    "other_certifications": ["string (e.g. BIS, ISI, Agmark, Cruelty-Free, Green Dot)"],
    "statutory_warnings": ["string (e.g. Contains added flavour, Not recommended for children)"],
    "storage_instructions": "string or null",
    "usage_instructions": "string or null"
  },
  "consumer_care": {
    "email": "string or null",
    "phone": "string or null",
    "address": "string or null",
    "website": "string or null"
  },
  "compliance_summary": {
    "detected_mandatory_fields": ["string"],
    "missing_or_unclear_fields": ["string"],
    "data_completeness_percentage": "number (0-100)"
  }
}
"""


class ProductLabelAggregator:
    """
    Groq-powered Multi-Image Packaging Data Aggregator & Synthesizer.
    """

    def __init__(
        self,
        key_mgr: Optional[GroqKeyManager] = None,
        primary_model: str = PRIMARY_AGGREGATOR_MODEL,
        fallback_model: str = FALLBACK_AGGREGATOR_MODEL
    ):
        self.key_manager = key_mgr or key_manager
        self.primary_model = primary_model
        self.fallback_model = fallback_model

    def aggregate_ocr_transcripts(self, ocr_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Takes a list of OCR results from each image angle and combines them into structured sections.

        Args:
            ocr_results: List of dictionaries containing OCR transcripts and metadata from each angle.

        Returns:
            Dict[str, Any]: Structured JSON dataset, Markdown summary, latency, and token usage.
        """
        t0 = time.time()

        if not ocr_results:
            raise ValueError("No OCR results provided to aggregator.")

        # Prepare formatted prompt with each image's text
        prompt_parts = [
            f"Here are the OCR transcriptions extracted from {len(ocr_results)} different image angles of the same product packaging:\n"
        ]

        for i, res in enumerate(ocr_results):
            source = res.get("source_type", f"Image {i+1}")
            full_text = res.get("full_text", "")
            if not full_text and "text_lines" in res:
                full_text = "\n".join(res["text_lines"])

            prompt_parts.append(f"--- [VIEW {i+1} : {source}] ---")
            prompt_parts.append(full_text if full_text.strip() else "(No text detected in this view)")
            prompt_parts.append("")

        prompt_parts.append("Now synthesize and combine all the above views into the requested JSON schema.")
        user_content = "\n".join(prompt_parts)

        # Execution function with fallback model logic
        def _execute_aggregation(client: Groq):
            for model_candidate in [self.primary_model, self.fallback_model]:
                try:
                    response = client.chat.completions.create(
                        model=model_candidate,
                        temperature=0.1,
                        max_tokens=2500,
                        messages=[
                            {"role": "system", "content": AGGREGATOR_SYSTEM_PROMPT},
                            {"role": "user", "content": user_content}
                        ]
                    )
                    return response, model_candidate
                except Exception as ex:
                    print(f"[Aggregator] Model '{model_candidate}' error: {ex}. Trying fallback...")
                    continue
            raise RuntimeError("All aggregator models failed.")

        response, model_used = self.key_manager.execute_with_retry(_execute_aggregation)
        elapsed = time.time() - t0

        raw_output = response.choices[0].message.content.strip()

        # Parse JSON
        parsed_json = self._extract_json(raw_output)

        # Generate formatted Markdown summary
        formatted_md = self.generate_markdown_report(parsed_json)

        token_usage = {}
        if hasattr(response, "usage") and response.usage:
            token_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }

        return {
            "model_used": model_used,
            "latency_sec": round(elapsed, 2),
            "total_views_combined": len(ocr_results),
            "token_usage": token_usage,
            "structured_data": parsed_json,
            "markdown_report": formatted_md,
            "raw_response": raw_output
        }

    def _extract_json(self, raw_text: str) -> Dict[str, Any]:
        """Extracts and parses JSON object from model output."""
        cleaned = raw_text.strip()
        if "```json" in cleaned:
            parts = cleaned.split("```json")
            if len(parts) > 1:
                cleaned = parts[1].split("```")[0].strip()
        elif "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) > 1:
                cleaned = parts[1].split("```")[0].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback regex search for outer braces
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(cleaned[start:end+1])
                except Exception:
                    pass
            print("[WARN] Failed to parse strict JSON from aggregator output. Returning raw text wrapper.")
            return {"raw_text": raw_text}

    @staticmethod
    def generate_markdown_report(data: Dict[str, Any]) -> str:
        """Generates a presentation-ready markdown report with distinct sections."""
        if not data or "product_identity" not in data:
            return f"```\n{json.dumps(data, indent=2)}\n```"

        pi = data.get("product_identity", {})
        mfg = data.get("manufacturer_and_marketer", {})
        dates = data.get("dates_and_batch", {})
        price = data.get("pricing_and_quantity", {})
        ingr = data.get("ingredients_and_allergens", {})
        nutr = data.get("nutritional_information", {})
        reg = data.get("regulatory_and_certifications", {})
        care = data.get("consumer_care", {})
        comp = data.get("compliance_summary", {})

        md = []
        md.append(f"# 📦 Product Compliance & Label Analysis: {pi.get('product_name') or 'Packaging'}\n")

        # 1. Product Overview
        md.append("## 1. 🏷️ Product Overview & Identity")
        md.append(f"- **Brand Name**: {pi.get('brand_name') or 'N/A'}")
        md.append(f"- **Product Name**: {pi.get('product_name') or 'N/A'}")
        md.append(f"- **Variant / Flavor**: {pi.get('variant_flavor') or 'Not detected'}")
        md.append(f"- **Category**: {pi.get('category') or 'Not detected'}")
        md.append(f"- **Vegetarian Status**: {pi.get('vegetarian_status') or 'Unspecified'}\n")

        # 2. Pricing & Quantity
        md.append("## 2. 💰 Pricing, Net Quantity & Weights")
        md.append(f"- **Maximum Retail Price (MRP)**: {price.get('mrp') or 'N/A'}")
        md.append(f"- **Net Quantity / Volume**: {price.get('net_quantity') or 'N/A'}")
        if price.get("unit_sale_price"):
            md.append(f"- **Unit Sale Price (USP)**: {price.get('unit_sale_price')}")
        if price.get("gross_weight"):
            md.append(f"- **Gross Weight**: {price.get('gross_weight')}")
        md.append("")

        # 3. Dates & Batch
        md.append("## 3. 📅 Dates & Batch Declarations")
        md.append(f"- **Date of Manufacture (MFD)**: {dates.get('mfg_date') or 'N/A'}")
        md.append(f"- **Expiry Date (EXP) / Use By**: {dates.get('exp_date') or 'N/A'}")
        md.append(f"- **Best Before**: {dates.get('best_before') or 'N/A'}")
        md.append(f"- **Batch / Lot No.**: {dates.get('batch_number') or dates.get('lot_number') or 'N/A'}\n")

        # 4. Manufacturer & Marketer
        md.append("## 4. 🏭 Manufacturer & Marketer Details")
        md.append(f"- **Manufactured By**: {mfg.get('manufactured_by') or 'N/A'}")
        md.append(f"- **Manufacturing Address**: {mfg.get('manufacturing_address') or 'N/A'}")
        if mfg.get("marketed_by"):
            md.append(f"- **Marketed By**: {mfg.get('marketed_by')}")
        if mfg.get("packed_by"):
            md.append(f"- **Packed By**: {mfg.get('packed_by')}")
        md.append(f"- **Country of Origin**: {mfg.get('country_of_origin') or 'India'}\n")

        # 5. Ingredients & Allergens
        md.append("## 5. 🥗 Ingredients & Allergens")
        ingredients = ingr.get("ingredients_list", [])
        if ingredients:
            md.append(f"- **Ingredients List**: {', '.join(ingredients)}")
        else:
            md.append("- **Ingredients List**: Not declared / not visible")

        allergens = ingr.get("allergens_declared", [])
        if allergens:
            md.append(f"- ⚠️ **Allergen Advice**: {', '.join(allergens)}")

        additives = ingr.get("food_additives_and_ins", [])
        if additives:
            md.append(f"- **Food Additives & INS**: {', '.join(additives)}")
        md.append("")

        # 6. Nutrition Facts Table
        md.append("## 6. 📊 Nutritional Information")
        if nutr.get("serving_size"):
            servings = nutr.get("servings_per_pack")
            md.append(f"*Serving Size: {nutr.get('serving_size')}"
                      + (f" | Servings Per Pack: {servings}" if servings else "")
                      + "*")

        nutrients = nutr.get("nutrients", [])
        if nutrients:
            md.append("\n| Nutrient | Per 100g/ml | Per Serving | % RDA |")
            md.append("| :--- | :---: | :---: | :---: |")
            for item in nutrients:
                n_name = item.get("name", "")
                per_100 = item.get("per_100g_or_ml") or "-"
                per_srv = item.get("per_serving") or "-"
                rda = item.get("rda_percentage") or "-"
                md.append(f"| {n_name} | {per_100} | {per_srv} | {rda} |")
        else:
            md.append("- No nutrition table detected.\n")
        md.append("")

        # 7. Regulatory & Quality Certifications
        md.append("## 7. ⚖️ Regulatory, FSSAI & Certifications")
        md.append(f"- **FSSAI License No.**: {reg.get('fssai_license_number') or 'Not Found / Not Visible'}")
        md.append(f"- **FSSAI Logo**: {'Present' if reg.get('fssai_logo_present') else 'Not Detected'}")
        certs = reg.get("other_certifications", [])
        if certs:
            md.append(f"- **Certifications**: {', '.join(certs)}")
        warnings = reg.get("statutory_warnings", [])
        if warnings:
            md.append(f"- **Mandatory Warnings**: {', '.join(warnings)}")
        if reg.get("storage_instructions"):
            md.append(f"- **Storage Instructions**: {reg.get('storage_instructions')}")
        md.append("")

        # 8. Consumer Care
        md.append("## 8. 📞 Consumer Care & Contact")
        md.append(f"- **Email**: {care.get('email') or 'N/A'}")
        md.append(f"- **Helpline / Phone**: {care.get('phone') or 'N/A'}")
        md.append(f"- **Website**: {care.get('website') or 'N/A'}\n")

        # 9. Compliance Summary
        md.append("## 9. 📋 Compliance Completeness Summary")
        comp_score = comp.get("data_completeness_percentage")
        if comp_score is not None:
            md.append(f"- **Overall Data Completeness**: **{comp_score}%**")
        else:
            md.append("- **Overall Data Completeness**: Not available")
        found_f = comp.get("detected_mandatory_fields", [])
        if found_f:
            md.append(f"- **Detected Mandatory Fields ({len(found_f)})**: {', '.join(found_f)}")
        miss_f = comp.get("missing_or_unclear_fields", [])
        if miss_f:
            md.append(f"- ⚠️ **Missing / Unclear Fields ({len(miss_f)})**: {', '.join(miss_f)}")

        return "\n".join(md)
