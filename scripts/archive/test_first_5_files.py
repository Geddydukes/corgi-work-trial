#!/usr/bin/env python3.11
"""
Test script: Process first 5 files with Gemini line item extraction
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from document_service.processor import DocumentProcessor
from shared import config


def extract_line_items_with_gemini(invoice_text: str, filename: str) -> list:
    """Use Gemini 2.5 Pro to extract line items directly from invoice text."""
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=config.Config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-pro")
        
        prompt = f"""Extract line items from this invoice/statement document.

FILENAME: {filename}

INVOICE TEXT:
{invoice_text[:8000]}

TASK:
Extract all line items (charges, fees, credits) from this invoice. For each line item, provide:
- description: Clear description of what the charge is for
- amount: The dollar amount (positive for charges, negative for credits)
- line_number: Approximate line number if visible

IMPORTANT:
- Only extract actual line items, not totals, dates, or other metadata
- Do not extract page numbers, invoice numbers, or other non-charge items
- If amounts seem unrealistic (over $10,000 for a single item), verify carefully
- Group related items together if they appear on the same line

RESPONSE FORMAT (JSON only):
{{
    "line_items": [
        {{
            "description": "Description of the charge",
            "amount": 123.45,
            "line_number": 1
        }},
        ...
    ],
    "total_amount": 1234.56,
    "confidence": 0.0-1.0
}}"""
        
        logger.info("  🤖 Calling Gemini 2.5 Pro for line item extraction...")
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Extract JSON from response
        if '```json' in response_text:
            json_start = response_text.find('```json') + 7
            json_end = response_text.find('```', json_start)
            response_text = response_text[json_start:json_end].strip()
        elif '```' in response_text:
            json_start = response_text.find('```') + 3
            json_end = response_text.find('```', json_start)
            response_text = response_text[json_start:json_end].strip()
        
        result = json.loads(response_text)
        return result.get('line_items', [])
        
    except Exception as e:
        logger.error(f"Gemini extraction error: {e}")
        if 'response_text' in locals():
            logger.error(f"Response was: {response_text[:500]}")
        return []


def analyze_document_content_with_gemini(text: str, filename: str) -> dict:
    """Use Gemini to analyze why a claim might be denied."""
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=config.Config.GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-pro")
        
        prompt = f"""Analyze this security deposit claim document to determine why it might be DENIED.

FILENAME: {filename}

DOCUMENT TEXT:
{text[:10000]}

TASK:
Analyze the document and identify:
1. What charges are listed
2. Whether there are any issues that would cause a DENIAL:
   - Normal wear and tear (not covered)
   - Charges not covered by addendum
   - Missing required information
   - Ineligible charges
   - Other denial reasons

RESPONSE FORMAT (JSON only):
{{
    "charges_found": ["list of charges"],
    "denial_reasons": ["reason1", "reason2"],
    "is_normal_wear_tear": true/false,
    "has_eligible_charges": true/false,
    "analysis": "Detailed explanation"
}}"""
        
        logger.info("  🔍 Analyzing document for denial reasons...")
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Extract JSON from response
        if '```json' in response_text:
            json_start = response_text.find('```json') + 7
            json_end = response_text.find('```', json_start)
            response_text = response_text[json_start:json_end].strip()
        elif '```' in response_text:
            json_start = response_text.find('```') + 3
            json_end = response_text.find('```', json_start)
            response_text = response_text[json_start:json_end].strip()
        
        return json.loads(response_text)
        
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return {}


async def test_files(folder_path: str, limit: int = 5):
    """Process first N files and extract line items."""
    folder = Path(folder_path)
    
    if not folder.exists():
        logger.error(f"Folder not found: {folder}")
        return
    
    files = sorted([f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in ['.pdf', '.jpg', '.jpeg', '.png']])[:limit]
    
    if not files:
        logger.error("No files found")
        return
    
    logger.info("=" * 80)
    logger.info(f"Processing First {len(files)} Files from: {folder.name}")
    logger.info("=" * 80)
    
    processor = DocumentProcessor()
    all_line_items = []
    
    for file_path in files:
        logger.info(f"\n{'='*80}")
        logger.info(f"📄 Processing: {file_path.name}")
        logger.info(f"{'='*80}")
        
        # Process with Gemini OCR
        result = await processor.process_document(
            file_path=file_path,
            claim_id=1,
            force_high_quality=True
        )
        
        if result.errors:
            logger.error(f"✗ Errors: {[e.error_type.value for e in result.errors]}")
            continue
        
        logger.info(f"✓ OCR: {result.best_extraction.confidence:.1f}% confidence")
        logger.info(f"✓ Type: {result.classification.document_type.value}")
        
        extracted_text = result.best_extraction.text
        logger.info(f"✓ Extracted {len(extracted_text)} characters")
        
        # Only extract line items for invoices/move-out statements
        is_invoice_or_statement = (
            result.classification.document_type.value == 'invoice' or
            'move-out-statement' in file_path.name.lower() or
            'move out statement' in file_path.name.lower() or
            'statement' in file_path.name.lower() and 'move' in file_path.name.lower()
        )
        
        line_items = []
        if is_invoice_or_statement:
            logger.info(f"\n🤖 Extracting line items (invoice/statement detected)...")
            line_items = extract_line_items_with_gemini(extracted_text, file_path.name)
        else:
            logger.info(f"\n⏭️  Skipping line item extraction (not an invoice/statement)")
        
        # Analyze for denial reasons
        logger.info(f"\n🔍 Analyzing for denial reasons...")
        analysis = analyze_document_content_with_gemini(extracted_text, file_path.name)
        
        # Display results
        if line_items:
            print(f"\n{'='*80}")
            print(f"LINE ITEMS: {file_path.name}")
            print(f"{'='*80}")
            print(f"\n{'#':<4} {'AMOUNT':>12} {'DESCRIPTION':<50}")
            print(f"{'-'*80}")
            
            total = Decimal("0")
            for i, item in enumerate(line_items, 1):
                amount = Decimal(str(item.get('amount', 0)))
                desc = item.get('description', 'No description')
                total += amount
                print(f"{i:<4} ${amount:>11.2f}  {desc[:48]}")
            
            print(f"{'-'*80}")
            print(f"{'TOTAL:':<16} ${total:>11.2f}")
            all_line_items.extend(line_items)
        
        # Display analysis
        if analysis:
            print(f"\n{'='*80}")
            print(f"DENIAL ANALYSIS: {file_path.name}")
            print(f"{'='*80}")
            if analysis.get('denial_reasons'):
                print(f"\n❌ DENIAL REASONS:")
                for reason in analysis['denial_reasons']:
                    print(f"   • {reason}")
            if analysis.get('is_normal_wear_tear'):
                print(f"\n⚠️  Contains Normal Wear & Tear: YES")
            if analysis.get('has_eligible_charges'):
                print(f"✅ Has Eligible Charges: YES")
            if analysis.get('analysis'):
                print(f"\n📋 Analysis:")
                print(f"   {analysis['analysis']}")
            print(f"{'='*80}\n")
        
        logger.info(f"✓ Processed {file_path.name}")
    
    # Summary
    if all_line_items:
        total_all = sum(Decimal(str(item.get('amount', 0))) for item in all_line_items)
        logger.info(f"\n{'='*80}")
        logger.info(f"SUMMARY")
        logger.info(f"{'='*80}")
        logger.info(f"Total Files Processed: {len(files)}")
        logger.info(f"Total Line Items: {len(all_line_items)}")
        logger.info(f"Total Amount: ${total_all}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Gemini extraction on first N files")
    parser.add_argument('folder', help='Path to folder containing files')
    parser.add_argument('--limit', type=int, default=5, help='Number of files to process')
    
    args = parser.parse_args()
    
    asyncio.run(test_files(args.folder, args.limit))

