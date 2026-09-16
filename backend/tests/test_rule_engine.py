"""
=============================================================================
Comprehensive Unit and Edge-Case Test Suite for LMPC 2011 Rule Engine
=============================================================================
Module: tests.test_rule_engine
Purpose:
  Validates deterministic legal metrology rule verification including:
    - Standard packaging OCR sessions.
    - Non-consumable product exemptions (books, electronics).
    - Missing statutory declarations (missing MRP prefix, missing tax notices).
    - Currency indicator checks.
    - Chronological date consistency (mfg vs exp date).
    - Relative shelf life statements (best before X months).
    - Named month date formatting.
=============================================================================
"""

import unittest
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.compliance.engine import RuleEngine
from app.compliance.models import ComplianceStatus, ProductDataInput


class TestLMPCRuleEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = RuleEngine()

    def test_parle_agro_session_mock_data(self):
        """Tests the actual mock session from Part 1 pipeline."""
        mock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "mock_ocr_session.json")
        self.assertTrue(os.path.exists(mock_file), f"Mock file not found: {mock_file}")

        with open(mock_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        report = self.engine.evaluate(data)

        self.assertEqual(report.summary.overall_verdict, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["mrp"].status, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["manufacture_date"].status, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["expiry_date"].status, ComplianceStatus.PASSED)

        # Check extracted values
        self.assertEqual(report.parameter_results["mrp"].extracted_normalized_value["price_inr"], 30.0)
        self.assertEqual(report.parameter_results["manufacture_date"].extracted_normalized_value, "2026-06-15")
        self.assertEqual(report.parameter_results["expiry_date"].extracted_normalized_value, "2026-12-11")

    def test_non_consumable_commodity_book(self):
        """Tests non-consumable goods (e.g. book) where Expiry is NOT applicable."""
        book_input = {
            "session_id": "session_test_book",
            "product_identity": {
                "product_name": "Python Programming Handbook",
                "category": "Book"
            },
            "pricing_and_quantity": {
                "mrp": "MRP ₹ 499.00 (INCL. OF ALL TAXES)",
                "net_quantity": "1 Unit"
            },
            "dates_and_batch": {
                "mfg_date": "01/2026",
                "exp_date": None
            },
            "regulatory_and_certifications": {
                "fssai_license_number": None
            }
        }

        report = self.engine.evaluate(book_input)

        self.assertEqual(report.summary.overall_verdict, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["mrp"].status, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["manufacture_date"].status, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["expiry_date"].status, ComplianceStatus.NOT_APPLICABLE)

    def test_mrp_missing_tax_declaration(self):
        """Tests failure when '(incl. of all taxes)' is missing (Rule 6(1)(e))."""
        non_compliant_mrp = {
            "session_id": "session_test_missing_tax",
            "product_identity": {"category": "Snacks"},
            "pricing_and_quantity": {
                "mrp": "MRP ₹ 50.00"  # Missing (incl. of all taxes)
            },
            "dates_and_batch": {
                "mfg_date": "10/05/2026",
                "exp_date": "10/11/2026"
            }
        }

        report = self.engine.evaluate(non_compliant_mrp)

        self.assertEqual(report.parameter_results["mrp"].status, ComplianceStatus.FAILED)
        self.assertEqual(report.summary.overall_verdict, ComplianceStatus.FAILED)
        
        tax_check = next(sc for sc in report.parameter_results["mrp"].sub_checks if sc.sub_check_id == "MRP-TAX-INCLUSION")
        self.assertEqual(tax_check.status, ComplianceStatus.FAILED)

    def test_mrp_missing_prefix(self):
        """Tests failure when price is given without 'MRP' or 'Maximum Retail Price' prefix."""
        bad_prefix_mrp = {
            "session_id": "session_test_bad_prefix",
            "product_identity": {"category": "Food"},
            "pricing_and_quantity": {
                "mrp": "Price: ₹ 100.00 (incl. of all taxes)"
            },
            "dates_and_batch": {
                "mfg_date": "05/2026",
                "exp_date": "11/2026"
            }
        }

        report = self.engine.evaluate(bad_prefix_mrp)
        self.assertEqual(report.parameter_results["mrp"].status, ComplianceStatus.FAILED)
        prefix_check = next(sc for sc in report.parameter_results["mrp"].sub_checks if sc.sub_check_id == "MRP-PREFIX")
        self.assertEqual(prefix_check.status, ComplianceStatus.FAILED)

    def test_mrp_missing_currency(self):
        """Tests failure when price lacks Indian currency indicator."""
        bad_currency_mrp = {
            "session_id": "session_test_bad_curr",
            "product_identity": {"category": "Beverage"},
            "pricing_and_quantity": {
                "mrp": "MRP 25.00 (incl. of all taxes)"
            },
            "dates_and_batch": {
                "mfg_date": "01/06/2026",
                "exp_date": "01/12/2026"
            }
        }

        report = self.engine.evaluate(bad_currency_mrp)
        self.assertEqual(report.parameter_results["mrp"].status, ComplianceStatus.FAILED)
        curr_check = next(sc for sc in report.parameter_results["mrp"].sub_checks if sc.sub_check_id == "MRP-CURRENCY-INDICATOR")
        self.assertEqual(curr_check.status, ComplianceStatus.FAILED)

    def test_chronological_date_inversion(self):
        """Tests failure when Expiry Date precedes Manufacturing Date."""
        inverted_dates = {
            "session_id": "session_test_inverted_dates",
            "product_identity": {"category": "Dairy", "product_name": "Milk"},
            "pricing_and_quantity": {
                "mrp": "MRP ₹ 28.00 (INCL. OF ALL TAXES)"
            },
            "dates_and_batch": {
                "mfg_date": "20/10/2026",
                "exp_date": "15/05/2026"  # EXP BEFORE MFG!
            }
        }

        report = self.engine.evaluate(inverted_dates)
        self.assertEqual(report.parameter_results["expiry_date"].status, ComplianceStatus.FAILED)
        self.assertEqual(report.summary.overall_verdict, ComplianceStatus.FAILED)

        chrono_check = next(sc for sc in report.parameter_results["expiry_date"].sub_checks if sc.sub_check_id == "EXP-CHRONOLOGICAL-CONSISTENCY")
        self.assertEqual(chrono_check.status, ComplianceStatus.FAILED)

    def test_relative_period_expiry(self):
        """Tests consumable product with relative shelf life statement ('best before 6 months from mfg')."""
        relative_exp = {
            "session_id": "session_test_relative_exp",
            "product_identity": {"category": "Confectionery", "product_name": "Chocolate Bar"},
            "pricing_and_quantity": {
                "mrp": "MRP Rs. 40.00 incl. of all taxes"
            },
            "dates_and_batch": {
                "mfg_date": "01/04/2026",
                "best_before": "BEST BEFORE 9 MONTHS FROM PACKAGING"
            }
        }

        report = self.engine.evaluate(relative_exp)
        self.assertEqual(report.parameter_results["mrp"].status, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["manufacture_date"].status, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["expiry_date"].status, ComplianceStatus.PASSED)
        self.assertEqual(report.summary.overall_verdict, ComplianceStatus.PASSED)

    def test_named_month_date_formats(self):
        """Tests date formats with month names like 'June 2026', '15-Dec-2026'."""
        named_date_input = {
            "session_id": "session_test_named_dates",
            "product_identity": {"category": "Food"},
            "pricing_and_quantity": {
                "mrp": "MRP ₹ 150.00 (INCLUSIVE OF ALL TAXES)"
            },
            "dates_and_batch": {
                "mfg_date": "Jun 2026",
                "exp_date": "Dec 2026"
            }
        }

        report = self.engine.evaluate(named_date_input)
        self.assertEqual(report.parameter_results["manufacture_date"].status, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["expiry_date"].status, ComplianceStatus.PASSED)
        self.assertEqual(report.parameter_results["manufacture_date"].extracted_normalized_value, "2026-06")
        self.assertEqual(report.parameter_results["expiry_date"].extracted_normalized_value, "2026-12")


if __name__ == "__main__":
    unittest.main()
