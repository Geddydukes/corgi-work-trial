#!/usr/bin/env python3.11
"""
Test script: Process just one file with Gemini line item extraction
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
        logger.error(f"Response was: {response_text[:500] if 'response_text' in locals() else 'N/A'}")
        return []


async def test_single_file(file_path: str):
    """Process a single file and extract line items."""
    file_path = Path(file_path)
    
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return
    
    logger.info("=" * 80)
    logger.info(f"Testing Single File: {file_path.name}")
    logger.info("=" * 80)
    
    processor = DocumentProcessor()
    
    # Process with Gemini OCR
    logger.info(f"\n📄 Processing: {file_path.name}")
    result = await processor.process_document(
        file_path=file_path,
        claim_id=1,  # Dummy claim ID
        force_high_quality=True
    )
    
    if result.errors:
        logger.error(f"✗ Errors: {[e.error_type.value for e in result.errors]}")
        return
    
    logger.info(f"✓ OCR: {result.best_extraction.confidence:.1f}% confidence")
    logger.info(f"✓ Type: {result.classification.document_type.value}")
    
    extracted_text = result.best_extraction.text
    logger.info(f"✓ Extracted {len(extracted_text)} characters")
    
    # Extract line items with Gemini
    logger.info(f"\n🤖 Extracting line items with Gemini 2.5 Pro...")
    line_items = extract_line_items_with_gemini(extracted_text, file_path.name)
    
    if not line_items:
        logger.warning("No line items extracted")
        return
    
    # Display results
    print(f"\n{'='*80}")
    print(f"EXTRACTED LINE ITEMS: {file_path.name}")
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
    print(f"{'='*80}\n")
    
    logger.info(f"✓ Extracted {len(line_items)} line items")
    logger.info(f"✓ Total: ${total}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Gemini line item extraction on a single file")
    parser.add_argument('file', help='Path to PDF file to process')
    
    args = parser.parse_args()
    
    asyncio.run(test_single_file(args.file))

