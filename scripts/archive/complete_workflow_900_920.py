#!/usr/bin/env python3.11
"""
Complete workflow for claims 900-920:
1. Get documents from Google Drive
2. Process documents (OCR, classification)
3. Run decision engine
4. Evaluate against validations
5. Generate variance report
"""

import asyncio
import sys
import argparse
from pathlib import Path
from decimal import Decimal
from sqlalchemy import create_engine, text
import json
import logging
import tempfile
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))


async def complete_workflow(
    drive_folder_id: str,
    drive_credentials: str,
    db_url: str,
    start_tracking: int = 900,
    end_tracking: int = 920
):
    """Complete workflow: Drive → Process → Decide → Evaluate"""
    
    from shared.google_drive import GoogleDriveService
    from document_service.processor import DocumentProcessor
    from decision_service.engine.decision_engine import DecisionEngine
    from decision_service.engine.invoice_parser import InvoiceParser
    from decision_service.engine.eligibility import EligibilityEngine
    from decision_service.engine.rule_evaluator import RuleEvaluator
    from shared.models import DocumentType
    from shared.config import Config
    
    Config.DATABASE_URL = db_url
    
    logger.info("=" * 80)
    logger.info("COMPLETE WORKFLOW: Claims 900-920")
    logger.info("=" * 80)
    
    engine = create_engine(db_url)
    drive_service = GoogleDriveService(
        credentials_path=drive_credentials,
        use_service_account=True
    )
    doc_processor = DocumentProcessor()
    decision_engine = DecisionEngine()
    
    tracking_numbers = [str(i) for i in range(start_tracking, end_tracking + 1)]
    
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1: Fetching Documents from Google Drive")
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
                
                subfolder = drive_service.get_file_by_name(drive_folder_id, tracking)
                
                if not subfolder:
                    logger.warning(f"  ⚠ Folder '{tracking}' not found in Drive")
                    continue
                
                logger.info(f"  → Found Drive folder: {subfolder.name} (ID: {subfolder.id})")
                
                files = drive_service.list_folder_files(
                    folder_id=subfolder.id,
                    file_types=['application/pdf', 'image/png', 'image/jpeg', 'image/jpg', 'image/tiff'],
                    recursive=False
                )
                
                logger.info(f"  → Found {len(files)} files in Drive folder")
                
                if not files:
                    logger.warning(f"  ⚠ No files in folder")
                    continue
                
                for drive_file in files:
                    try:
                        logger.info(f"    Processing: {drive_file.name}")
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(drive_file.name).suffix) as tmp_file:
                            file_stream, _, _ = drive_service.download_file_to_stream(drive_file.id)
                            tmp_file.write(file_stream.read())
                            tmp_path = Path(tmp_file.name)
                        
                        logger.info(f"    → Running document processor...")
                        result = await doc_processor.process_document(
                            file_path=tmp_path,
                            claim_id=claim_id,
                            processing_priority=0,
                            force_high_quality=False
                        )
                        
                        tmp_path.unlink()
                        
                        if result.processing_error:
                            logger.error(f"    ✗ Processing error: {result.processing_error}")
                            continue
                        
                        logger.info(f"    ✓ Processed: {result.classification.document_type} (confidence: {result.classification.confidence:.1f}%)")
                        
                        with engine.begin() as doc_conn:
                            doc_conn.execute(text("SET search_path TO claims, public"))
                            
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
                                    'file_path': f"drive://{drive_file.id}",
                                    'filename': drive_file.name,
                                    'file_hash': f"drive_{drive_file.id}",
                                    'size': drive_file.size,
                                    'mime_type': drive_file.mime_type,
                                    'doc_type': result.classification.document_type,
                                    'class_conf': result.classification.confidence,
                                    'text': result.best_extraction.text or '',
                                    'ocr_conf': result.best_extraction.confidence,
                                    'pages': result.best_extraction.page_count or 1
                                }
                            )
                        
                        documents_processed += 1
                        logger.info(f"    ✓ Document saved to database")
                    
                    except Exception as e:
                        logger.error(f"    ✗ Error processing file {drive_file.name}: {e}")
                        import traceback
                        traceback.print_exc()
        
        except Exception as e:
            logger.error(f"  ✗ Error processing claim {tracking}: {e}")
            import traceback
            traceback.print_exc()
    
    logger.info(f"\n✓ Processed {documents_processed} documents from Drive")
    
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
                
                has_addendum = any(doc.get('document_type') == DocumentType.ADDENDUM.value for doc in documents)
                has_invoice = any(doc.get('document_type') == DocumentType.INVOICE.value for doc in documents)
                
                invoice_data = await decision_engine.invoice_parser.parse_documents(documents)
                
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
                    invoice_total=invoice_data.get("total_amount", Decimal("0"))
                )
                
                logger.info(f"  → Decision: {rule_result['status']} ${rule_result['benefit_amount']}")
                
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
                        'approved': json.dumps(eligibility_result.get('approved_items', [])),
                        'ineligible': json.dumps(eligibility_result.get('ineligible_items', [])),
                        'flags': json.dumps(rule_result.get('flags', {})),
                        'missing': json.dumps(rule_result.get('missing_data', {})),
                        'reasoning': json.dumps(rule_result.get('reasoning', {})),
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
    parser = argparse.ArgumentParser(description="Complete workflow for claims 900-920")
    parser.add_argument('--drive-folder', required=True, help='Google Drive folder ID')
    parser.add_argument('--drive-credentials', required=True, help='Path to service account JSON')
    parser.add_argument('--db', required=True, help='PostgreSQL connection string')
    parser.add_argument('--start', type=int, default=900, help='Start tracking number')
    parser.add_argument('--end', type=int, default=920, help='End tracking number')
    
    args = parser.parse_args()
    
    asyncio.run(complete_workflow(
        drive_folder_id=args.drive_folder,
        drive_credentials=args.drive_credentials,
        db_url=args.db,
        start_tracking=args.start,
        end_tracking=args.end
    ))

