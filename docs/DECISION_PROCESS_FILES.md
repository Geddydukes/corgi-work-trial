# Decision Process Files Reference

This document lists all files involved in the decision-making process for analyzing variance reports.

## Entry Point Scripts

### Main Execution Script

- **`scripts/run_decisions_first_5.py`** - Main script that runs the decision engine on claims 900-904
  - Orchestrates the entire decision process
  - Calls DecisionEngine for each claim
  - Prints results and line item details

### Variance Report Generation

- **`scripts/generate_variance_report.py`** - Generates variance reports comparing proposed vs actual decisions
  - Queries database for proposed and actual decisions
  - Calculates variance statistics
  - Outputs formatted reports

## Core Decision Engine Files

### Main Orchestrator

- **`decision_service/engine/decision_engine.py`** - Main decision engine orchestrator
  - Coordinates all decision components
  - Calls EligibilityEngine, InvoiceParser, RuleEvaluator, DocumentAnalyzer
  - Handles document analysis and line item extraction
  - Creates final Decision objects
  - **Key method**: `evaluate_claim(claim_id) -> Decision`

### Document Analysis (Gemini Integration)

- **`decision_service/engine/document_analyzer.py`** - Analyzes documents using Gemini 2.5 Pro/Flash
  - `analyze_all_documents()` - Batch analyzes all documents for denial reasons
  - `extract_line_items_from_invoice()` - Extracts line items from invoices/statements
  - `analyze_line_items_batch()` - Analyzes line items for eligibility flags
  - **Contains the prompts sent to Gemini** - This is where approval/denial logic is defined
  - **Key flags**: `should_be_included`, `is_normal_wear_tear`, `is_covered_by_addendum`, `is_covered_by_other_insurance`

### JSON Validation

- **`decision_service/engine/json_validator.py`** - Validates Gemini's JSON responses
  - `LineItemAnalysis` dataclass - Structure for line item analysis
  - `extract_json_from_response()` - Extracts JSON from Gemini's markdown-wrapped responses
  - `validate_line_item_analysis_response()` - Validates schema, types, ranges
  - `parse_and_validate_line_item_analysis()` - Orchestrates validation with retry logic

### Rule Evaluation

- **`decision_service/engine/rule_evaluator.py`** - Evaluates business rules
  - Applies caps (claim_amount, max_benefit)
  - Calculates final benefit amounts
  - Determines approve/deny status
  - **Key method**: `evaluate(claim, eligibility_result) -> rule_result`

### Eligibility Calculation

- **`decision_service/engine/eligibility.py`** - Calculates eligible amounts
  - Processes approved/ineligible line items
  - Calculates eligible_total
  - **Key method**: `calculate(claim, invoice_data) -> eligibility_result`

### Invoice Parsing (Legacy - Mostly Bypassed)

- **`decision_service/engine/invoice_parser.py`** - Legacy invoice parser
  - Mostly bypassed in favor of Gemini extraction
  - Still used for invoice detection logic

## Data Access Layer

### Repositories

- **`decision_service/repositories/claim_repository.py`** - Database operations for claims and decisions

  - `get_claim(claim_id)` - Fetches claim data
  - `get_claim_by_tracking_number(tracking_number)` - Fetches by tracking number
  - `create_decision(decision)` - Saves decision to database

- **`decision_service/repositories/document_repository.py`** - Database operations for documents
  - `get_documents(claim_id)` - Fetches all documents for a claim
  - Returns document metadata including extracted_text, document_type, etc.

## Data Models

### Shared Models

- **`shared/models.py`** - Core data models
  - `DocumentType` enum - Document classification types
  - `EligibilityStatus` enum - Eligibility statuses
  - `ExtractedText` - OCR extraction results
  - `DocumentProcessingResult` - Document processing results

## Configuration

### Environment Variables

- **`env.example`** - Environment variable template
  - `GEMINI_API_KEY` - API key for Gemini
  - `GEMINI_MODEL` - Model to use (gemini-2.5-flash or gemini-2.5-pro)

## Documentation

### Analysis Documents

- **`docs/ISSUE_ANALYSIS.md`** - Analysis of issues found in variance reports
- **`docs/JSON_STRUCTURE_REQUIREMENTS.md`** - JSON validation requirements
- **`variance_report_900_904.txt`** - First variance report
- **`variance_report_900_904_v2.txt`** - Second variance report
- **`variance_report_900_904_v3.txt`** - Third variance report

## Decision Flow

```
1. scripts/run_decisions_first_5.py
   ↓
2. decision_service/engine/decision_engine.py::evaluate_claim()
   ↓
3. decision_service/repositories/claim_repository.py::get_claim()
   ↓
4. decision_service/repositories/document_repository.py::get_documents()
   ↓
5. decision_service/engine/document_analyzer.py::analyze_all_documents()
   ↓ (Gemini API call)
6. decision_service/engine/document_analyzer.py::extract_line_items_from_invoice()
   ↓ (Gemini API call)
7. decision_service/engine/document_analyzer.py::analyze_line_items_batch()
   ↓ (Gemini API call with prompts)
   ↓ (JSON validation via json_validator.py)
8. decision_service/engine/eligibility.py::calculate()
   ↓
9. decision_service/engine/rule_evaluator.py::evaluate()
   ↓
10. decision_service/repositories/claim_repository.py::create_decision()
```

## Key Files for Variance Analysis

When analyzing variance reports, focus on these files:

1. **`decision_service/engine/document_analyzer.py`** (Lines 250-350)

   - Contains the prompts sent to Gemini
   - Defines approval/denial rules
   - Auto-denial logic (rent, improper notice, other insurance)
   - Normal wear/tear detection

2. **`decision_service/engine/decision_engine.py`** (Lines 88-280)

   - Document analysis override logic
   - Line item extraction and analysis
   - Final decision creation

3. **`decision_service/engine/rule_evaluator.py`**

   - Cap calculation (claim_amount, max_benefit)
   - Final benefit amount calculation

4. **`decision_service/engine/json_validator.py`**
   - Ensures Gemini responses are valid
   - May cause fallback to defaults if validation fails

## Database Tables

- **`claims`** - Claim data (claim_amount, max_benefit, etc.)
- **`claim_documents`** - Document metadata and extracted text
- **`decisions`** - Proposed decisions (proposed_status, proposed_benefit_amount, approved_line_items, ineligible_line_items)
- **`decision_validation`** - Actual decisions (actual_status, actual_paid_amount)
