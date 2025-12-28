#!/usr/bin/env python3.11
"""
Complete workflow for claims 900-920 using local files:
1. Process documents from local directory
2. Run decision engine
3. Evaluate against validations
4. Generate variance report
"""

import asyncio
import sys
import argparse
from pathlib import Path
from decimal import Decimal
from sqlalchemy import create_engine, text
import json
import logging
import hashlib
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))


async def complete_workflow(
    local_folder: str,
    db_url: str,
    start_tracking: int = 900,
    end_tracking: int = 920
):
    """Complete workflow: Local Files → Process → Decide → Evaluate"""
    
    from document_service.processor import DocumentProcessor
    from decision_service.engine.decision_engine import DecisionEngine
    from shared.models import DocumentType
    from shared.config import Config
    
    Config.DATABASE_URL = db_url
    
    logger.info("=" * 80)
    logger.info("COMPLETE WORKFLOW: Claims 900-920 (Local Files)")
    logger.info("=" * 80)
    
    engine = create_engine(db_url)
    doc_processor = DocumentProcessor()
    decision_engine = DecisionEngine()
    
    local_path = Path(local_folder)
    if not local_path.exists():
        logger.error(f"Local folder not found: {local_folder}")
        return
    
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1: Processing Documents from Local Directory")
    logger.info("=" * 80)
    
    documents_processed = 0
    
    for tracking in tracking_numbers:
        try:
            logger.info(f"\nProcessing claim {tracking}...")
            
            with engine.begin() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                claim_result = conn.execute(
                    text("SELECT id FROM claims.claims WHERE claim_tracking_number = :tracking"),
                    {'tracking': tracking}
                )
                claim_row = claim_result.fetchone()
                
                if not claim_row:
                    logger.warning(f"  ⚠ Claim {tracking} not found in database")
                    continue
                
                claim_id = claim_row[0]
                logger.info(f"  → Claim ID: {claim_id}")
                
                tracking_folder = local_path / tracking
                
                if not tracking_folder.exists():
                    logger.warning(f"  ⚠ Folder '{tracking}' not found in local directory")
                    continue
                
                logger.info(f"  → Found local folder: {tracking_folder}")
                
                files = list(tracking_folder.glob("*"))
                files = [f for f in files if f.is_file() and f.suffix.lower() in ['.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.docx']]
                
                logger.info(f"  → Found {len(files)} files in folder")
                
                if not files:
                    logger.warning(f"  ⚠ No files in folder")
                    continue
                
                for file_path in files:
                    try:
                        logger.info(f"    Processing: {file_path.name}")
                        
                        logger.info(f"    → Running document processor...")
                        result = await doc_processor.process_document(
                            file_path=file_path,
                            claim_id=claim_id,
                            processing_priority=0,
                            force_high_quality=False
                        )
                        
                        if result.errors:
                            logger.error(f"    ✗ Processing errors: {[e.error_type for e in result.errors]}")
                            # Continue anyway to save what we can
                        
                        logger.info(f"    ✓ Processed: {result.classification.document_type} (confidence: {result.classification.confidence:.1f}%)")
                        
                        with engine.begin() as doc_conn:
                            doc_conn.execute(text("SET search_path TO claims, public"))
                            
                            file_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
                            file_size = file_path.stat().st_size
                            
                            doc_conn.execute(
                                text("""
                                    INSERT INTO claims.claim_documents (
                                        claim_id, file_path, original_filename, file_hash,
                                        file_size_bytes, mime_type, document_type,
                                        classification_confidence, extracted_text, ocr_confidence,
                                        page_count, processing_status, processed_at
                                    ) VALUES (
                                        :claim_id, :file_path, :filename, :file_hash,
                                        :size, :mime_type, CAST(:doc_type AS document_type_enum),
                                        :class_conf, :text, :ocr_conf,
                                        :pages, 'completed', NOW()
                                    )
                                    ON CONFLICT (claim_id, file_hash) DO UPDATE SET
                                        extracted_text = EXCLUDED.extracted_text,
                                        classification_confidence = EXCLUDED.classification_confidence,
                                        ocr_confidence = EXCLUDED.ocr_confidence,
                                        processing_status = 'completed',
                                        processed_at = NOW()
                                """),
                                {
                                    'claim_id': claim_id,
                                    'file_path': str(file_path),
                                    'filename': file_path.name,
                                    'file_hash': file_hash,
                                    'size': file_size,
                                    'mime_type': 'application/pdf' if file_path.suffix.lower() == '.pdf' else 'image/jpeg',
                                    'doc_type': result.classification.document_type,
                                    'class_conf': result.classification.confidence,
                                    'text': result.best_extraction.text or '',
                                    'ocr_conf': result.best_extraction.confidence,
                                    'pages': len(result.best_extraction.page_wise_text) if result.best_extraction.page_wise_text else (result.file_metadata.page_count if result.file_metadata else 1)
                                }
                            )
                        
                        documents_processed += 1
                        logger.info(f"    ✓ Document saved to database")
                    
                    except Exception as e:
                        logger.error(f"    ✗ Error processing file {file_path.name}: {e}")
                        import traceback
                        traceback.print_exc()
        
        except Exception as e:
            logger.error(f"  ✗ Error processing claim {tracking}: {e}")
            import traceback
            traceback.print_exc()
    
    logger.info(f"\n✓ Processed {documents_processed} documents from local directory")
    
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Running Decision Engine")
    logger.info("=" * 80)
    
    decisions_created = 0
    
    for tracking in tracking_numbers:
        try:
            logger.info(f"\nRunning decision engine for claim {tracking}...")
            
            with engine.begin() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                claim_result = conn.execute(
                    text("""
                        SELECT id, claim_amount, max_benefit, security_deposit_amount,
                               claim_date, move_out_date, lease_start_date, lease_end_date
                        FROM claims.claims 
                        WHERE claim_tracking_number = :tracking
                    """),
                    {'tracking': tracking}
                )
                claim_row = claim_result.fetchone()
                
                if not claim_row:
                    continue
                
                claim_id, claim_amount, max_benefit, security_deposit, claim_date, move_out_date, lease_start, lease_end = claim_row
                
                existing = conn.execute(
                    text("SELECT id FROM claims.decisions WHERE claim_id = :claim_id AND is_active = true"),
                    {'claim_id': claim_id}
                ).fetchone()
                
                if existing:
                    logger.info(f"  → Decision already exists, skipping")
                    continue
                
                doc_result = conn.execute(
                    text("""
                        SELECT id, document_type, extracted_text, classification_confidence,
                               ocr_confidence, file_path, original_filename
                        FROM claims.claim_documents
                        WHERE claim_id = :claim_id
                    """),
                    {'claim_id': claim_id}
                )
                doc_rows = doc_result.fetchall()
                
                documents = []
                for doc_row in doc_rows:
                    documents.append({
                        'id': doc_row[0],
                        'document_type': doc_row[1],
                        'extracted_text': doc_row[2] or '',
                        'classification_confidence': float(doc_row[3]) if doc_row[3] else None,
                        'ocr_confidence': float(doc_row[4]) if doc_row[4] else None,
                        'file_path': doc_row[5],
                        'original_filename': doc_row[6]
                    })
                
                logger.info(f"  → Found {len(documents)} documents")
                
                if not documents:
                    logger.warning(f"  ⚠ No documents - creating deny decision")
                    conn.execute(
                        text("""
                            INSERT INTO claims.decisions (
                                claim_id, decision_type, proposed_status, proposed_benefit_amount,
                                eligible_total, invoice_total, cap_amount,
                                approved_line_items, ineligible_line_items, flags, missing_data, reasoning,
                                confidence_score, engine_version, processing_time_ms, decided_by, decided_at, is_active
                            ) VALUES (
                                :claim_id, 'initial', 'deny', 0.00,
                                0.00, :claim_amount, :max_benefit,
                                '[]'::jsonb, '[]'::jsonb,
                                '{"critical":["no_documents"],"warnings":[],"info":[]}'::jsonb,
                                '{"fields":["documents"],"needs_user_input":true}'::jsonb,
                                '{"reason":"No documents available"}'::jsonb,
                                50.0, 'rules_v1.0.0', 0, 'system', NOW(), true
                            )
                        """),
                        {
                            'claim_id': claim_id,
                            'claim_amount': float(claim_amount) if claim_amount else 0.0,
                            'max_benefit': float(max_benefit) if max_benefit else None
                        }
                    )
                    decisions_created += 1
                    continue
                
                claim_data = {
                    'id': claim_id,
                    'claim_tracking_number': tracking,
                    'claim_amount': float(claim_amount) if claim_amount else 0.0,
                    'max_benefit': float(max_benefit) if max_benefit else None,
                    'security_deposit_amount': float(security_deposit) if security_deposit else None,
                    'claim_date': str(claim_date) if claim_date else None,
                    'move_out_date': str(move_out_date) if move_out_date else None,
                    'lease_start_date': str(lease_start) if lease_start else None,
                    'lease_end_date': str(lease_end) if lease_end else None,
                    'status': 'completed'
                }
                
                logger.info(f"  → Running decision engine...")
                
                # Calculate average document confidence
                avg_confidence = 0.0
                if documents:
                    confidences = [doc.get('classification_confidence', 0) or 0 for doc in documents]
                    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
                    logger.info(f"  → Average document confidence: {avg_confidence:.1f}%")
                
                has_addendum = any(doc.get('document_type') == DocumentType.ADDENDUM.value for doc in documents)
                # Check for invoices - also check if invoice parser found any documents
                has_invoice = any(doc.get('document_type') == DocumentType.INVOICE.value for doc in documents)
                # Also check filenames for addendum-like documents
                if not has_addendum:
                    addendum_keywords = ['addendum', 'waiver', 'sdrp']
                    for doc in documents:
                        filename = doc.get('original_filename', '').lower()
                        if any(keyword in filename for keyword in addendum_keywords):
                            has_addendum = True
                            logger.info(f"  → Found addendum-like document: {doc.get('original_filename')}")
                            break
                
                invoice_data = await decision_engine.invoice_parser.parse_documents(documents)
                
                # Update has_invoice based on what invoice parser found
                if invoice_data.get("document_count", 0) > 0 or invoice_data.get("total_amount", Decimal("0")) > 0:
                    has_invoice = True
                    logger.info(f"  → Invoice parser found invoice data (total: ${invoice_data.get('total_amount', 0)})")
                
                eligibility_result = await decision_engine.eligibility_engine.calculate(
                    claim=claim_data,
                    invoice_data=invoice_data
                )
                
                rule_result = await decision_engine.rule_evaluator.evaluate(
                    claim=claim_data,
                    eligibility_result=eligibility_result,
                    override_max_benefit=Decimal(str(max_benefit)) if max_benefit else None,
                    has_addendum=has_addendum,
                    has_invoice=has_invoice,
                    invoice_total=invoice_data.get("total_amount", Decimal("0")),
                    document_confidence=avg_confidence
                )
                
                logger.info(f"  → Decision: {rule_result['status']} ${rule_result['benefit_amount']}")
                
                # Helper function to convert Decimal to float for JSON serialization
                def decimal_to_float(obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, dict):
                        return {k: decimal_to_float(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [decimal_to_float(item) for item in obj]
                    return obj
                
                conn.execute(
                    text("""
                        INSERT INTO claims.decisions (
                            claim_id, decision_type, proposed_status, proposed_benefit_amount,
                            eligible_total, invoice_total, cap_amount,
                            approved_line_items, ineligible_line_items, flags, missing_data, reasoning,
                            confidence_score, engine_version, processing_time_ms, decided_by, decided_at, is_active
                        ) VALUES (
                            :claim_id, 'initial', CAST(:status AS decision_status_enum), :benefit,
                            :eligible, :invoice, :cap,
                            CAST(:approved AS jsonb), CAST(:ineligible AS jsonb),
                            CAST(:flags AS jsonb), CAST(:missing AS jsonb),
                            CAST(:reasoning AS jsonb),
                            :confidence, :version, :time_ms, 'system', NOW(), true
                        )
                    """),
                    {
                        'claim_id': claim_id,
                        'status': rule_result['status'],
                        'benefit': float(rule_result['benefit_amount']),
                        'eligible': float(eligibility_result.get('eligible_total', 0)),
                        'invoice': float(invoice_data.get('total_amount', 0)),
                        'cap': float(rule_result.get('cap_amount')) if rule_result.get('cap_amount') else None,
                        'approved': json.dumps(decimal_to_float(eligibility_result.get('approved_items', []))),
                        'ineligible': json.dumps(decimal_to_float(eligibility_result.get('ineligible_items', []))),
                        'flags': json.dumps(decimal_to_float(rule_result.get('flags', {}))),
                        'missing': json.dumps(decimal_to_float(rule_result.get('missing_data', {}))),
                        'reasoning': json.dumps(decimal_to_float(rule_result.get('reasoning', {}))),
                        'confidence': rule_result.get('confidence', 85.0),
                        'version': decision_engine.rule_evaluator.version,
                        'time_ms': 0
                    }
                )
                
                decisions_created += 1
                logger.info(f"  ✓ Decision saved")
        
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            import traceback
            traceback.print_exc()
    
    logger.info(f"\n✓ Created {decisions_created} decisions")
    
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Running Evaluation")
    logger.info("=" * 80)
    
    from evaluation import DecisionEvaluator
    
    evaluator = DecisionEvaluator(db_url)
    
    tracking_list = "', '".join(tracking_numbers)
    
    query = f"""
    SELECT 
        d.claim_id,
        c.claim_tracking_number,
        d.proposed_status,
        d.proposed_benefit_amount,
        d.eligible_total,
        d.invoice_total,
        d.flags,
        d.missing_data,
        d.confidence_score,
        d.engine_version,
        d.decided_at,
        d.processing_time_ms,
        v.actual_status,
        v.actual_paid_amount,
        v.actual_decision_date,
        v.adjudication_notes
    FROM claims.decisions d
    INNER JOIN claims.claims c ON d.claim_id = c.id
    INNER JOIN claims.decision_validation v ON d.claim_id = v.claim_id
    WHERE d.is_active = true
    AND c.claim_tracking_number IN ('{tracking_list}')
    ORDER BY CAST(c.claim_tracking_number AS INTEGER)
    """
    
    with engine.connect() as conn:
        import pandas as pd
        df = pd.read_sql(text(query), conn)
    
    if len(df) == 0:
        logger.error("No decisions found for evaluation")
        return
    
    logger.info(f"Evaluating {len(df)} decisions...")
    
    metrics = evaluator.calculate_metrics(df)
    mismatches = evaluator.identify_mismatches(df)
    
    output_dir = Path("./claims_900_920_results")
    output_dir.mkdir(exist_ok=True)
    
    evaluator.generate_visualizations(df, metrics, str(output_dir))
    evaluator.export_results(metrics, mismatches, str(output_dir))
    
    from evaluate_claims_range import generate_variance_report
    generate_variance_report(
        metrics,
        mismatches,
        str(output_dir / f"variance_report_claims_{start_tracking}_to_{end_tracking}.txt")
    )
    
    logger.info("\n" + "=" * 80)
    logger.info("WORKFLOW COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Documents processed: {documents_processed}")
    logger.info(f"Decisions created: {decisions_created}")
    logger.info(f"Evaluation accuracy: {metrics.accuracy:.2%}")
    logger.info(f"Mean Absolute Error: ${metrics.mean_absolute_error:.2f}")
    logger.info(f"Results saved to: {output_dir}/")
    logger.info("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Complete workflow for claims 900-920 using local files")
    parser.add_argument('--local-folder', required=True, help='Path to local folder with numbered subfolders')
    parser.add_argument('--db', required=True, help='PostgreSQL connection string')
    parser.add_argument('--start', type=int, default=900, help='Start tracking number')
    parser.add_argument('--end', type=int, default=920, help='End tracking number')
    
    args = parser.parse_args()
    
    asyncio.run(complete_workflow(
        local_folder=args.local_folder,
        db_url=args.db,
        start_tracking=args.start,
        end_tracking=args.end
    ))

