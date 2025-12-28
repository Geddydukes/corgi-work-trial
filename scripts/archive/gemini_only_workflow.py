#!/usr/bin/env python3.11
"""
Enhanced Gemini workflow: 
- Gemini OCR for all files
- Gemini 2.5 Pro for line item eligibility analysis
- Checks each line item against addendum
- Outputs line items with "should be included" flags
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from sqlalchemy import create_engine, text
import json
import logging
from dotenv import load_dotenv
from typing import Dict, List, Optional

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from document_service.processor import DocumentProcessor
from decision_service.engine.invoice_parser import InvoiceParser
from shared.models import DocumentType
from shared import config


def extract_line_items_with_gemini(
    invoice_text: str,
    filename: str
) -> List[Dict]:
    """
    Use Gemini 2.5 Pro to extract line items directly from invoice text.
    Bypasses the broken invoice parser.
    """
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
        logger.error(f"Gemini line item extraction error: {e}")
        return []


def analyze_line_item_with_gemini(
    line_item: Dict,
    addendum_text: Optional[str],
    claim_context: Dict
) -> Dict:
    """
    Use Gemini 2.5 Pro to analyze if a line item should be included.
    
    Returns:
        Dict with 'should_be_included' (bool), 'confidence' (float), 'reasoning' (str)
    """
    try:
        import google.generativeai as genai
        
        genai.configure(api_key=config.Config.GEMINI_API_KEY)
        # Use Gemini 2.5 Pro for intelligent line item analysis
        model = genai.GenerativeModel("gemini-2.5-pro")
        
        description = line_item.get('description', 'No description')
        amount = line_item.get('amount', 0)
        
        prompt = f"""You are analyzing a security deposit claim line item to determine if it should be approved.

LINE ITEM:
Description: {description}
Amount: ${amount:.2f}

CLAIM CONTEXT:
Max Benefit: ${claim_context.get('max_benefit', 'N/A')}
Security Deposit: ${claim_context.get('security_deposit', 'N/A')}

ADDENDUM TEXT (Security Deposit Waiver/Addendum):
{addendum_text if addendum_text else 'No addendum found'}

TASK:
1. Review the line item description and amount
2. Check if the addendum covers this type of charge
3. Determine if this line item should be INCLUDED in the approved benefit amount

RESPONSE FORMAT (JSON only):
{{
    "should_be_included": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation",
    "addendum_reference": "Quote from addendum if relevant, or 'N/A'"
}}"""
        
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
        return {
            'should_be_included': result.get('should_be_included', False),
            'confidence': float(result.get('confidence', 0.5)),
            'reasoning': result.get('reasoning', 'No reasoning provided'),
            'addendum_reference': result.get('addendum_reference', 'N/A')
        }
        
    except Exception as e:
        logger.error(f"Gemini analysis error: {e}")
        return {
            'should_be_included': False,
            'confidence': 0.0,
            'reasoning': f'Analysis error: {str(e)}',
            'addendum_reference': 'N/A'
        }


async def gemini_only_workflow(
    local_folder: str,
    db_url: str,
    start_tracking: int = 900,
    end_tracking: int = 904
):
    """Process all files with Gemini OCR and output line items to terminal."""
    
    engine = create_engine(db_url)
    processor = DocumentProcessor()
    invoice_parser = InvoiceParser()
    
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    
    logger.info("=" * 80)
    logger.info("GEMINI-ONLY WORKFLOW: All files use Tier 3 Gemini OCR")
    logger.info("=" * 80)
    logger.info(f"Processing claims: {start_tracking} to {end_tracking}")
    logger.info("")
    
    for tracking_num in tracking_numbers:
        with engine.connect() as conn:
            conn.execute(text("SET search_path TO claims, public"))
            result = conn.execute(
                text("SELECT id FROM claims WHERE claim_tracking_number = :tracking"),
                {"tracking": tracking_num}
            ).fetchone()
            
            if not result:
                logger.warning(f"Claim {tracking_num} not found, skipping")
                continue
            
            claim_id = result[0]
            logger.info(f"\n{'='*80}")
            logger.info(f"Processing Claim {tracking_num} (ID: {claim_id})")
            logger.info(f"{'='*80}")
        
        # Find local folder
        local_path = Path(local_folder) / tracking_num
        if not local_path.exists():
            logger.warning(f"  → Folder not found: {local_path}")
            continue
        
        files = list(local_path.glob("*"))
        pdf_files = [f for f in files if f.suffix.lower() in ['.pdf', '.jpg', '.jpeg', '.png']]
        
        logger.info(f"  → Found {len(pdf_files)} files")
        
        # Get claim context
        with engine.connect() as conn:
            conn.execute(text("SET search_path TO claims, public"))
            claim_data = conn.execute(
                text("""
                    SELECT 
                        claim_amount,
                        max_benefit,
                        security_deposit_amount
                    FROM claims
                    WHERE id = :claim_id
                """),
                {"claim_id": claim_id}
            ).fetchone()
            
            claim_context = {
                'max_benefit': float(claim_data[1]) if claim_data[1] else None,
                'security_deposit': float(claim_data[2]) if claim_data[2] else None,
                'claim_amount': float(claim_data[0]) if claim_data[0] else None
            }
        
        # Find addendum file and extract text
        addendum_text = None
        addendum_file = None
        for file_path in sorted(pdf_files):
            filename_lower = file_path.name.lower()
            if 'addendum' in filename_lower:
                addendum_file = file_path
                logger.info(f"  📋 Found addendum: {file_path.name}")
                # Process addendum to get text
                try:
                    result = await processor.process_document(
                        file_path=file_path,
                        claim_id=claim_id,
                        force_high_quality=True
                    )
                    if result.best_extraction.text:
                        addendum_text = result.best_extraction.text
                        logger.info(f"    ✓ Extracted {len(addendum_text)} chars from addendum")
                except Exception as e:
                    logger.error(f"    ✗ Error processing addendum: {e}")
                break
        
        if not addendum_text:
            logger.warning("  ⚠️  No addendum found or could not extract text")
        
        all_line_items = []
        invoice_files = []
        
        for file_path in sorted(pdf_files):
            logger.info(f"\n  📄 Processing: {file_path.name}")
            
            try:
                # Force Gemini OCR (Tier 3) for all files
                result = await processor.process_document(
                    file_path=file_path,
                    claim_id=claim_id,
                    force_high_quality=True  # This forces Tier 3
                )
                
                if result.errors:
                    logger.error(f"    ✗ Errors: {[e.error_type.value for e in result.errors]}")
                    continue
                
                logger.info(f"    ✓ OCR: {result.best_extraction.confidence:.1f}% confidence")
                logger.info(f"    ✓ Type: {result.classification.document_type.value}")
                
                # Get documents for invoice parser
                with engine.connect() as conn:
                    conn.execute(text("SET search_path TO claims, public"))
                    docs = conn.execute(
                        text("""
                            SELECT 
                                id,
                                original_filename,
                                document_type,
                                extracted_text,
                                ocr_confidence
                            FROM claim_documents
                            WHERE claim_id = :claim_id
                            AND original_filename = :filename
                            ORDER BY processed_at DESC
                            LIMIT 1
                        """),
                        {"claim_id": claim_id, "filename": file_path.name}
                    ).fetchall()
                
                # Try to parse as invoice
                if docs:
                    doc_dict = {
                        "id": docs[0][0],
                        "original_filename": docs[0][1],
                        "document_type": docs[0][2],
                        "extracted_text": docs[0][3] or "",
                        "ocr_confidence": float(docs[0][4]) if docs[0][4] else 0.0
                    }
                    
                    # Check if it might be an invoice
                    is_potential_invoice = (
                        doc_dict["document_type"] == DocumentType.INVOICE.value or
                        "move" in doc_dict["original_filename"].lower() and "out" in doc_dict["original_filename"].lower() and "statement" in doc_dict["original_filename"].lower() or
                        "sdi" in doc_dict["original_filename"].lower() or
                        "invoice" in doc_dict["original_filename"].lower() or
                        "statement" in doc_dict["original_filename"].lower()
                    )
                    
                    if is_potential_invoice and doc_dict["extracted_text"]:
                        # Only use Gemini Pro for actual invoices/move-out statements
                        is_actual_invoice = (
                            doc_dict["document_type"] == DocumentType.INVOICE.value or
                            "move-out-statement" in doc_dict["original_filename"].lower() or
                            "move out statement" in doc_dict["original_filename"].lower() or
                            ("statement" in doc_dict["original_filename"].lower() and "move" in doc_dict["original_filename"].lower())
                        )
                        
                        if is_actual_invoice:
                            logger.info(f"    → Extracting line items with Gemini 2.5 Pro (invoice/statement)...")
                            
                            # Use Gemini to extract line items directly (bypass broken parser)
                            extracted_items = extract_line_items_with_gemini(
                                doc_dict["extracted_text"],
                                doc_dict["original_filename"]
                            )
                            
                            if extracted_items:
                                # Calculate total from extracted items
                                total = sum(Decimal(str(item.get('amount', 0))) for item in extracted_items)
                                
                                logger.info(f"    ✓ Found {len(extracted_items)} line items")
                                logger.info(f"    ✓ Total: ${total}")
                                
                                invoice_files.append({
                                    'filename': file_path.name,
                                    'line_items': extracted_items,
                                    'total': float(total)
                                })
                                
                                all_line_items.extend(extracted_items)
                        else:
                            logger.info(f"    ⏭️  Skipping line item extraction (not an invoice/statement)")
            
            except Exception as e:
                logger.error(f"    ✗ Error processing file {file_path.name}: {e}")
                continue
        
        # Analyze line items with Gemini 2.5 Pro
        if all_line_items:
            logger.info(f"\n  🤖 Analyzing {len(all_line_items)} line items with Gemini 2.5 Pro...")
            logger.info(f"  📋 Using addendum: {addendum_file.name if addendum_file else 'None'}")
            
            analyzed_items = []
            for i, item in enumerate(all_line_items, 1):
                logger.info(f"    Analyzing item {i}/{len(all_line_items)}: {item.get('description', 'N/A')[:50]}...")
                analysis = analyze_line_item_with_gemini(item, addendum_text, claim_context)
                analyzed_items.append({
                    'line_item': item,
                    'analysis': analysis
                })
            
            # Output results to terminal
            print(f"\n{'='*80}")
            print(f"CLAIM {tracking_num} - LINE ITEM ANALYSIS")
            print(f"{'='*80}")
            if addendum_file:
                print(f"Addendum: {addendum_file.name}")
            print(f"Total Line Items: {len(analyzed_items)}")
            print(f"\n{'='*80}")
            print(f"{'#':<4} {'INCLUDE':<8} {'AMOUNT':>12} {'CONF':>6} {'DESCRIPTION':<40}")
            print(f"{'-'*80}")
            
            total_included = Decimal("0")
            total_excluded = Decimal("0")
            
            for i, analyzed in enumerate(analyzed_items, 1):
                item = analyzed['line_item']
                analysis = analyzed['analysis']
                
                amount = Decimal(str(item.get('amount', 0)))
                desc = item.get('description', 'No description')[:38]
                include = analysis['should_be_included']
                confidence = analysis['confidence']
                
                if include:
                    total_included += amount
                    include_flag = "✅ YES"
                else:
                    total_excluded += amount
                    include_flag = "❌ NO"
                
                print(f"{i:<4} {include_flag:<8} ${amount:>11.2f} {confidence*100:>5.1f}% {desc}")
                
                # Show reasoning for items that need attention
                if not include or confidence < 0.7:
                    print(f"     └─ {analysis['reasoning'][:70]}")
                    if analysis['addendum_reference'] != 'N/A':
                        print(f"     └─ Addendum: {analysis['addendum_reference'][:70]}")
            
            print(f"{'-'*80}")
            print(f"{'TOTAL INCLUDED:':<20} ${total_included:>11.2f}")
            print(f"{'TOTAL EXCLUDED:':<20} ${total_excluded:>11.2f}")
            print(f"{'INVOICE TOTAL:':<20} ${total_included + total_excluded:>11.2f}")
            print(f"{'='*80}\n")
            
            # Summary
            logger.info(f"\n  📊 Claim {tracking_num} Summary:")
            logger.info(f"     Total Items: {len(analyzed_items)}")
            logger.info(f"     ✅ Should Include: {sum(1 for a in analyzed_items if a['analysis']['should_be_included'])}")
            logger.info(f"     ❌ Should Exclude: {sum(1 for a in analyzed_items if not a['analysis']['should_be_included'])}")
            logger.info(f"     Total Included: ${total_included}")
            logger.info(f"     Total Excluded: ${total_excluded}")
        
    
    logger.info("\n" + "=" * 80)
    logger.info("WORKFLOW COMPLETE")
    logger.info("=" * 80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Gemini-only workflow with line item output")
    parser.add_argument('--local-folder', required=True, help='Local folder path')
    parser.add_argument('--db', required=True, help='Database URL')
    parser.add_argument('--start', type=int, default=900, help='Start tracking number')
    parser.add_argument('--end', type=int, default=904, help='End tracking number')
    
    args = parser.parse_args()
    
    asyncio.run(gemini_only_workflow(
        local_folder=args.local_folder,
        db_url=args.db,
        start_tracking=args.start,
        end_tracking=args.end
    ))

