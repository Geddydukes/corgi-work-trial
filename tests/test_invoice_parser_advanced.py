import pytest
from decimal import Decimal
from decision_service.engine.invoice_parser_advanced import AdvancedInvoiceParser
from decision_service.engine.invoice_models import LineItemConfidence


class TestInvoiceParserAdvanced:
    @pytest.fixture
    def parser(self):
        return AdvancedInvoiceParser()
    
    def test_perfect_invoice(self, parser):
        text = """
        INVOICE #12345
        Date: 01/15/2024
        
        Description                    Amount
        Cleaning                        $150.00
        Carpet Repair                   $75.50
        Paint Touch-up                  $45.25
        
        Total                          $270.75
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) == 3
        assert result.invoice_total_stated == Decimal("270.75")
        assert result.reconciliation_difference <= Decimal("1.00")
        assert not result.requires_manual_review
        assert all(item.confidence == LineItemConfidence.HIGH for item in result.line_items)
    
    def test_handwritten_additions(self, parser):
        text = """
        INVOICE
        
        Cleaning                        $150.00
        Repairs                         $75.00
        Additional work (handwritten)    $25.00
        
        Total                           $250.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert result.invoice_total_calculated >= Decimal("200.00")
    
    def test_multi_page_with_page_break(self, parser):
        text = """
        Page 1
        Cleaning                        $150.00
        Repairs                         $75.00
        
        Page 2
        Additional work                 $50.00
        
        Total                           $275.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert any("Page" in item.description or "page" in item.description.lower() 
                  for item in result.line_items)
    
    def test_missing_total(self, parser):
        text = """
        INVOICE
        
        Description                    Amount
        Cleaning                        $150.00
        Repairs                         $75.50
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert result.invoice_total_stated is None
        assert result.invoice_total_calculated > Decimal("0")
    
    def test_negative_amounts_credits(self, parser):
        text = """
        INVOICE
        
        Cleaning                        $150.00
        Repairs                         $75.00
        Credit for overcharge          ($25.00)
        Refund                         -$10.00
        
        Total                           $190.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.credits) >= 1
        assert all(item.amount <= 0 for item in result.credits)
        assert len(result.line_items) >= 2
    
    def test_percentage_based_charges(self, parser):
        text = """
        INVOICE
        
        Base amount                    $1000.00
        Service fee (15%)              $150.00
        
        Total                          $1150.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 1
        assert result.invoice_total_calculated > Decimal("1000.00")
    
    def test_formula_charges(self, parser):
        text = """
        INVOICE
        
        Labor: 3 hours × $25/hour       $75.00
        Materials: 5 units × $10        $50.00
        
        Total                          $125.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 1
        assert any("×" in item.description or "x" in item.description.lower() 
                  for item in result.line_items)
    
    def test_foreign_currency(self, parser):
        text = """
        INVOICE
        
        Cleaning                        1.234,56€
        Repairs                         500,00€
        
        Total                          1.734,56€
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 1
        assert any("euro" in note.lower() or "conversion" in note.lower() 
                  for item in result.line_items for note in item.notes)
    
    def test_ambiguous_descriptions(self, parser):
        text = """
        INVOICE
        
        cln                            $150.00
        rpr                             $75.00
        misc                            $25.00
        
        Total                          $250.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert any(item.ambiguity_score > 50 for item in result.line_items)
    
    def test_duplicate_line_items(self, parser):
        text = """
        INVOICE
        
        Cleaning                        $150.00
        Cleaning                        $150.00
        Repairs                         $75.00
        
        Total                          $375.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert "duplicate" in ' '.join(result.flags).lower() or len(result.line_items) == 3
    
    def test_single_item_exceeds_total(self, parser):
        text = """
        INVOICE
        
        Cleaning                        $500.00
        
        Total                          $250.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 1
        assert result.requires_manual_review or "suspicious" in ' '.join(result.flags).lower()
    
    def test_sum_not_equal_stated_total(self, parser):
        text = """
        INVOICE
        
        Cleaning                        $150.00
        Repairs                         $75.00
        
        Total                          $300.00
        """
        result = parser.parse_invoice(text)
        
        assert not result.reconciliation_difference == Decimal("0")
        assert result.requires_manual_review or "reconciliation" in ' '.join(result.flags).lower()
    
    def test_no_line_items_found(self, parser):
        text = """
        INVOICE
        
        Thank you for your business.
        Please contact us with any questions.
        """
        result = parser.parse_invoice(text)
        
        assert result.requires_manual_review
        assert "no line items" in ' '.join(result.manual_review_reasons).lower() or len(result.line_items) == 0
    
    def test_tax_separate_from_charges(self, parser):
        text = """
        INVOICE
        
        Cleaning                        $150.00
        Repairs                           $75.00
        
        Subtotal                        $225.00
        Sales Tax (8%)                  $18.00
        
        Total                           $243.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.taxes) >= 1
        assert all(item.is_tax for item in result.taxes)
        assert len(result.line_items) >= 2
    
    def test_subtotals_throughout(self, parser):
        text = """
        INVOICE
        
        Room 1 Cleaning                 $50.00
        Room 2 Cleaning                 $50.00
        Subtotal                        $100.00
        
        Room 1 Repairs                  $30.00
        Room 2 Repairs                  $30.00
        Subtotal                        $60.00
        
        Total                           $160.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 4
        assert result.invoice_total_calculated > Decimal("0")
    
    def test_columnar_format(self, parser):
        text = """
        Item Description          Quantity    Unit Price    Amount
        Cleaning Service          1           $150.00       $150.00
        Repair Work               2           $37.50        $75.00
        
        Total                                          $225.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert result.invoice_total_stated == Decimal("225.00")
    
    def test_itemized_list_with_bullets(self, parser):
        text = """
        INVOICE
        
        • Cleaning                  $150.00
        • Repairs                   $75.00
        • Paint                     $45.00
        
        Total                       $270.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 3
    
    def test_multiline_item_descriptions(self, parser):
        text = """
        INVOICE
        
        Deep cleaning of entire
        apartment including all
        rooms and common areas      $200.00
        
        Total                       $200.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 1
        assert any(len(item.description) > 20 for item in result.line_items)
    
    def test_no_dollar_sign_amounts(self, parser):
        text = """
        INVOICE
        
        Cleaning                    150.00
        Repairs                     75.50
        
        Total                       225.50
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert result.invoice_total_calculated >= Decimal("200.00")
    
    def test_parentheses_for_negatives(self, parser):
        text = """
        INVOICE
        
        Cleaning                     $150.00
        Credit                      ($25.00)
        
        Total                        $125.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.credits) >= 1
        assert any(item.amount < 0 for item in result.credits)
    
    def test_minus_sign_negatives(self, parser):
        text = """
        INVOICE
        
        Cleaning                     $150.00
        Refund                      -$25.00
        
        Total                        $125.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.credits) >= 1
    
    def test_tbd_or_pending_amounts(self, parser):
        text = """
        INVOICE
        
        Cleaning                     $150.00
        Additional work              TBD
        Future repairs               Pending
        
        Total                        $150.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 1
        assert any("tbd" in note.lower() or "pending" in note.lower() 
                  for item in result.line_items for note in item.notes)
    
    def test_range_amounts(self, parser):
        text = """
        INVOICE
        
        Estimated repairs            $50-$75
        Cleaning                     $150.00
        
        Total                        $200.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 1
        assert any("range" in note.lower() or "midpoint" in note.lower() 
                  for item in result.line_items for note in item.notes)
    
    def test_mixed_fonts_and_sizes(self, parser):
        text = """
        INVOICE #123
        
        CLEANING                      $150.00
        repairs                       $75.00
        PAINT                         $45.00
        
        TOTAL                         $270.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 3
    
    def test_previous_balance_vs_new_charges(self, parser):
        text = """
        INVOICE
        
        Previous Balance              $100.00
        New Charges                   $200.00
        
        Total Due                     $300.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 1
        assert result.invoice_total_calculated > Decimal("0")
    
    def test_payment_already_applied(self, parser):
        text = """
        INVOICE
        
        Charges                       $300.00
        Payment Applied              ($100.00)
        
        Balance Due                   $200.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.credits) >= 1
        assert len(result.line_items) >= 1
    
    def test_formula_based_charges_detailed(self, parser):
        text = """
        INVOICE
        
        Labor: 3 units × $25/unit      $75.00
        Materials: 2 × $50              $100.00
        
        Total                          $175.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert result.invoice_total_calculated >= Decimal("150.00")
    
    def test_foreign_language_descriptions(self, parser):
        text = """
        INVOICE
        
        Limpieza                      $150.00
        Reparaciones                  $75.00
        
        Total                         $225.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert result.requires_manual_review or any(
            "translation" in flag.lower() or "foreign" in flag.lower() 
            for flag in result.flags
        )
    
    def test_merged_cells_table(self, parser):
        text = """
        INVOICE
        
        Description                    Amount
        Cleaning Services              $150.00
        (includes all rooms)
        Repairs                        $75.00
        
        Total                          $225.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 1
    
    def test_typos_and_abbreviations(self, parser):
        text = """
        INVOICE
        
        cln                            $150.00
        rpr                             $75.00
        pnt                             $45.00
        
        Total                          $270.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 3
        assert any(item.ambiguity_score > 40 for item in result.line_items)
    
    def test_multiple_items_per_line(self, parser):
        text = """
        INVOICE
        
        Cleaning & Repairs             $225.00
        Paint & Touch-up               $70.00
        
        Total                          $295.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
    
    def test_codes_without_descriptions(self, parser):
        text = """
        INVOICE
        
        Code 42A                       $75.00
        Code 15B                       $50.00
        
        Total                          $125.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert any("code" in item.description.lower() for item in result.line_items)
    
    def test_empty_invoice(self, parser):
        text = ""
        result = parser.parse_invoice(text)
        
        assert result.requires_manual_review
        assert len(result.line_items) == 0 or result.requires_manual_review
    
    def test_performance_large_invoice(self, parser):
        text = "INVOICE\n"
        for i in range(200):
            text += f"Item {i+1}                        ${(i+1)*10:.2f}\n"
        text += "\nTotal                          $201000.00"
        
        result = parser.parse_invoice(text)
        
        assert result.quality_metrics.processing_time_ms < 5000
        assert len(result.line_items) > 0
    
    def test_industry_specific_property_management(self, parser):
        text = """
        MOVE-OUT CHARGES
        
        Cleaning                        $150.00
        Carpet cleaning                 $75.00
        Paint                           $200.00
        Repairs                         $100.00
        
        Total                           $525.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 4
        assert any("move-out" in item.description.lower() or 
                  "cleaning" in item.description.lower() 
                  for item in result.line_items)
    
    def test_industry_specific_utility_bills(self, parser):
        text = """
        UTILITY BILL
        
        Water                          $45.00
        Electric                       $120.00
        Gas                            $60.00
        
        Total                          $225.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 3
        assert any("water" in item.description.lower() or 
                  "electric" in item.description.lower() or
                  "gas" in item.description.lower()
                  for item in result.line_items)
    
    def test_industry_specific_cleaning_breakdown(self, parser):
        text = """
        CLEANING INVOICE
        
        Kitchen                        $50.00
        Living Room                    $40.00
        Bedroom 1                      $35.00
        Bedroom 2                      $35.00
        Bathroom                       $30.00
        
        Total                          $190.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 5
    
    def test_industry_specific_maintenance_split(self, parser):
        text = """
        MAINTENANCE INVOICE
        
        Labor                          $150.00
        Parts                          $75.00
        
        Total                          $225.00
        """
        result = parser.parse_invoice(text)
        
        assert len(result.line_items) >= 2
        assert any("labor" in item.description.lower() or 
                  "parts" in item.description.lower()
                  for item in result.line_items)
    
    def test_confidence_scoring(self, parser):
        text = """
        INVOICE
        
        Detailed cleaning service      $150.00
        Repairs                        $75.00
        X                              $25.00
        
        Total                          $250.00
        """
        result = parser.parse_invoice(text)
        
        assert all(item.confidence in [LineItemConfidence.HIGH, LineItemConfidence.MEDIUM, LineItemConfidence.LOW]
                  for item in result.line_items)
        assert result.quality_metrics.overall_confidence >= 0
        assert result.quality_metrics.overall_confidence <= 100
















