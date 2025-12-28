#!/usr/bin/env python3
"""
Import Security Deposit Claims CSV into Database

This script reads the CSV file and splits data into appropriate database tables:
- claims: Core claim information
- decision_validation: Actual decision outcomes for evaluation
- Optional: Creates decisions if needed

CSV Mapping:
- Tracking Number -> claim_tracking_number
- Claim Date -> claim_date
- Approval Date/Posted Date -> actual_decision_date
- Amount of Claim -> claim_amount
- Max Benefit -> max_benefit
- Approved Benefit Amount -> actual_paid_amount
- Status -> actual_status (Posted=approve, Declined=deny)
- Lease dates, addresses, etc. -> claims table fields
"""

import csv
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from decimal import Decimal
import re
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> Optional[str]:
    """Parse various date formats to YYYY-MM-DD."""
    if not date_str or date_str.strip() == '':
        return None
    
    date_str = date_str.strip()
    
    formats = [
        '%m/%d/%y',  # 03/04/22
        '%m/%d/%Y',  # 03/04/2022
        '%Y-%m-%d',  # 2022-03-04
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    logger.warning(f"Could not parse date: {date_str}")
    return None


def parse_currency(amount_str: str) -> float:
    """Parse currency string to float."""
    if not amount_str or amount_str.strip() == '':
        return 0.0
    
    amount_str = amount_str.strip()
    
    amount_str = re.sub(r'[$,]', '', amount_str)
    
    try:
        return float(amount_str)
    except ValueError:
        logger.warning(f"Could not parse amount: {amount_str}")
        return 0.0


def normalize_status(status: str) -> str:
    """Normalize status to 'approve' or 'deny'."""
    if not status:
        return 'deny'
    
    status_lower = status.strip().lower()
    
    if 'posted' in status_lower or 'approve' in status_lower:
        return 'approve'
    elif 'decline' in status_lower or 'deny' in status_lower:
        return 'deny'
    else:
        logger.warning(f"Unknown status: {status}, defaulting to deny")
        return 'deny'


def build_property_id(address: str, city: str, state: str, zip_code: str) -> str:
    """Build a property ID from address components."""
    parts = []
    if address:
        parts.append(address.replace(' ', '_').replace(',', '').replace('#', ''))
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    if zip_code:
        parts.append(zip_code.split('-')[0])
    
    return '-'.join(parts) if parts else f"PROP-{hash(address or 'unknown') % 10000}"


def import_csv_to_database(
    csv_path: str,
    db_url: str,
    dry_run: bool = False,
    create_decisions: bool = False
):
    """
    Import CSV data into database tables.
    
    Args:
        csv_path: Path to CSV file
        db_url: PostgreSQL connection string
        dry_run: If True, validate but don't insert
        create_decisions: If True, create decision records from validation data
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)
    
    engine = create_engine(db_url)
    
    logger.info(f"Reading CSV file: {csv_path}")
    
    claims_inserted = 0
    validations_inserted = 0
    decisions_inserted = 0
    errors = []
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        if not reader.fieldnames:
            logger.error("CSV file is empty or invalid")
            sys.exit(1)
        
        logger.info(f"Found {len(reader.fieldnames)} columns in CSV")
        
        for row_num, row in enumerate(reader, start=2):
            try:
                tracking_number = row.get('Tracking Number', '').strip()
                if not tracking_number:
                    errors.append(f"Row {row_num}: Missing Tracking Number")
                    continue
                
                claim_date = parse_date(row.get('Claim Date', ''))
                if not claim_date:
                    errors.append(f"Row {row_num}: Missing or invalid Claim Date")
                    continue
                
                move_out_date = parse_date(row.get('Move-Out Date', ''))
                lease_start = parse_date(row.get('Lease Start Date', ''))
                lease_end = parse_date(row.get('Lease End Date', ''))
                
                claim_amount = parse_currency(row.get('Amount of Claim', ''))
                max_benefit = parse_currency(row.get('Max Benefit', ''))
                
                status = normalize_status(row.get('Status', ''))
                approved_amount = parse_currency(row.get('Approved Benefit Amount', ''))
                
                posted_date = parse_date(row.get('Posted Date', '') or row.get('Approval Date', ''))
                if not posted_date:
                    posted_date = claim_date
                
                address = row.get('Lease Street Address', '').strip()
                city = row.get('Lease City', '').strip()
                state = row.get('Lease State', '').strip()
                zip_code = row.get('Lease Zip', '').strip()
                
                property_id = build_property_id(address, city, state, zip_code)
                policyholder_id = f"POL-{row.get('Policy', '').strip() or 'UNKNOWN'}"
                
                monthly_rent = parse_currency(row.get('Monthly Rent', ''))
                security_deposit = monthly_rent if monthly_rent > 0 else max_benefit * 0.4
                
                adjudication_notes = row.get('PM Explanation', '').strip() or row.get('Hold Reason', '').strip()
                if not adjudication_notes:
                    adjudication_notes = f"Status: {row.get('Status', '')}"
                
                if dry_run:
                    logger.info(f"[DRY RUN] Would import claim {tracking_number}: ${claim_amount} -> {status} ${approved_amount}")
                    claims_inserted += 1
                    validations_inserted += 1
                    continue
                
                with engine.begin() as conn:
                    try:
                        conn.execute(text("SET search_path TO claims, public"))
                        claim_id_result = conn.execute(
                            text("""
                                INSERT INTO claims.claims (
                                    claim_tracking_number,
                                    claim_amount,
                                    max_benefit,
                                    security_deposit_amount,
                                    policyholder_id,
                                    property_id,
                                    claim_date,
                                    move_out_date,
                                    lease_start_date,
                                    lease_end_date,
                                    status,
                                    priority,
                                    created_at,
                                    created_by
                                )
                                VALUES (
                                    :tracking_number,
                                    :claim_amount,
                                    :max_benefit,
                                    :security_deposit,
                                    :policyholder_id,
                                    :property_id,
                                    CAST(:claim_date AS DATE),
                                    CAST(:move_out_date AS DATE),
                                    CAST(:lease_start AS DATE),
                                    CAST(:lease_end AS DATE),
                                    'completed',
                                    0,
                                    NOW(),
                                    'csv_import'
                                )
                                ON CONFLICT (claim_tracking_number) 
                                DO UPDATE SET
                                    claim_amount = EXCLUDED.claim_amount,
                                    max_benefit = EXCLUDED.max_benefit,
                                    claim_date = EXCLUDED.claim_date,
                                    move_out_date = EXCLUDED.move_out_date,
                                    lease_start_date = EXCLUDED.lease_start_date,
                                    lease_end_date = EXCLUDED.lease_end_date
                                RETURNING id
                            """),
                            {
                                'tracking_number': tracking_number,
                                'claim_amount': claim_amount,
                                'max_benefit': max_benefit,
                                'security_deposit': security_deposit,
                                'policyholder_id': policyholder_id,
                                'property_id': property_id,
                                'claim_date': claim_date,
                                'move_out_date': move_out_date,
                                'lease_start': lease_start,
                                'lease_end': lease_end
                            }
                        )
                        
                        claim_id = claim_id_result.scalar()
                        if claim_id:
                            claims_inserted += 1
                            logger.info(f"Inserted/Updated claim: {tracking_number} (ID: {claim_id})")
                        
                        validation_result = conn.execute(
                            text("""
                                INSERT INTO claims.decision_validation (
                                    claim_id,
                                    actual_status,
                                    actual_paid_amount,
                                    actual_decision_date,
                                    adjudication_notes,
                                    adjudicator_id,
                                    validation_source
                                )
                                VALUES (
                                    :claim_id,
                                    CAST(:actual_status AS decision_status_enum),
                                    :actual_paid_amount,
                                    CAST(:actual_decision_date AS DATE),
                                    :adjudication_notes,
                                    :adjudicator_id,
                                    :validation_source
                                )
                                ON CONFLICT (claim_id, actual_decision_date)
                                DO UPDATE SET
                                    actual_status = EXCLUDED.actual_status,
                                    actual_paid_amount = EXCLUDED.actual_paid_amount,
                                    adjudication_notes = EXCLUDED.adjudication_notes
                            """),
                            {
                                'claim_id': claim_id,
                                'actual_status': status,
                                'actual_paid_amount': approved_amount,
                                'actual_decision_date': posted_date,
                                'adjudication_notes': adjudication_notes,
                                'adjudicator_id': 'csv_import',
                                'validation_source': 'historical_csv'
                            }
                        )
                        
                        if validation_result.rowcount > 0:
                            validations_inserted += 1
                            logger.info(f"  → Validation: {status} ${approved_amount:.2f} on {posted_date}")
                        
                        conn.commit()
                        
                        if create_decisions and claim_id:
                            decision_result = conn.execute(
                                text("""
                                    INSERT INTO claims.decisions (
                                        claim_id,
                                        decision_type,
                                        proposed_status,
                                        proposed_benefit_amount,
                                        eligible_total,
                                        invoice_total,
                                        cap_amount,
                                        approved_line_items,
                                        ineligible_line_items,
                                        flags,
                                        missing_data,
                                        reasoning,
                                        confidence_score,
                                        engine_version,
                                        processing_time_ms,
                                        decided_by,
                                        decided_at,
                                        is_active
                                    )
                                    VALUES (
                                        :claim_id,
                                        'initial',
                                        CAST(:proposed_status AS decision_status_enum),
                                        :proposed_benefit_amount,
                                        :eligible_total,
                                        :invoice_total,
                                        :cap_amount,
                                        '[]'::jsonb,
                                        '[]'::jsonb,
                                        '{"critical":[],"warnings":[],"info":[]}'::jsonb,
                                        '{"fields":[],"needs_user_input":false}'::jsonb,
                                        '{"source":"csv_import"}'::jsonb,
                                        100.0,
                                        'csv_import_v1.0',
                                        0,
                                        'csv_import',
                                        CAST(:decided_at AS TIMESTAMPTZ),
                                        true
                                    )
                                    ON CONFLICT DO NOTHING
                                """),
                                {
                                    'claim_id': claim_id,
                                    'proposed_status': status,
                                    'proposed_benefit_amount': approved_amount,
                                    'eligible_total': approved_amount,
                                    'invoice_total': claim_amount,
                                    'cap_amount': max_benefit,
                                    'decided_at': posted_date
                                }
                            )
                            
                            if decision_result.rowcount > 0:
                                decisions_inserted += 1
                                logger.info(f"  → Decision created")
                                conn.commit()
                    
                    except SQLAlchemyError as e:
                        conn.rollback()
                        error_msg = f"Row {row_num}: Database error - {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
            
            except Exception as e:
                error_msg = f"Row {row_num}: Processing error - {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
    
    logger.info("=" * 60)
    logger.info("Import Summary:")
    logger.info(f"  Claims inserted/updated: {claims_inserted}")
    logger.info(f"  Validations inserted/updated: {validations_inserted}")
    if create_decisions:
        logger.info(f"  Decisions created: {decisions_inserted}")
    
    if errors:
        logger.warning(f"  Errors encountered: {len(errors)}")
        logger.info("\nFirst 10 errors:")
        for error in errors[:10]:
            logger.info(f"  - {error}")
        if len(errors) > 10:
            logger.info(f"  ... and {len(errors) - 10} more errors")
    
    if dry_run:
        logger.info("\n[DRY RUN] No data was actually inserted. Run without --dry-run to import.")
    
    logger.info("=" * 60)
    
    return claims_inserted, validations_inserted, decisions_inserted, errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import Security Deposit Claims CSV into database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script imports claims and validation data from the CSV file.

Required CSV columns:
  - Tracking Number (claim tracking number)
  - Claim Date (claim date)
  - Amount of Claim (claim amount)
  - Max Benefit (max benefit)
  - Status (Posted/Declined -> approve/deny)
  - Approved Benefit Amount (actual paid amount)
  - Posted Date or Approval Date (decision date)
  - Lease dates, addresses (optional but recommended)

Example:
  python import_claims_csv.py claims.csv --db "postgresql://user:pass@localhost/corgi_dev"
        """
    )
    
    parser.add_argument('csv_file', help='Path to CSV file')
    parser.add_argument('--db', required=True, help='PostgreSQL connection string')
    parser.add_argument('--dry-run', action='store_true', help='Validate CSV without inserting data')
    parser.add_argument('--create-decisions', action='store_true', help='Also create decision records from validation data')
    
    args = parser.parse_args()
    
    import_csv_to_database(
        args.csv_file,
        args.db,
        dry_run=args.dry_run,
        create_decisions=args.create_decisions
    )

