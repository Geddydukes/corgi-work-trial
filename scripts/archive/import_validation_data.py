#!/usr/bin/env python3
"""
CSV Import Script for Decision Validation Data

This script imports historical validation data from CSV into the decision_validation table.
The CSV should contain actual decision outcomes to compare against proposed decisions.

CSV Format:
- claim_tracking_number: Claim tracking number (must match existing claims)
- actual_status: 'approve' or 'deny'
- actual_paid_amount: Amount actually paid (0.00 for denied claims)
- actual_decision_date: Date of actual decision (YYYY-MM-DD)
- adjudication_notes: Optional notes about the decision
- adjudicator_id: Optional adjudicator user ID
- validation_source: Source of validation data (e.g., 'historical', 'manual', 'system')
"""

import csv
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def validate_csv_row(row: dict, row_num: int) -> tuple[bool, Optional[str]]:
    """Validate a CSV row has required fields and valid values."""
    required_fields = ['claim_tracking_number', 'actual_status', 'actual_paid_amount', 'actual_decision_date']
    
    for field in required_fields:
        if field not in row or not row[field].strip():
            return False, f"Row {row_num}: Missing required field '{field}'"
    
    status = row['actual_status'].strip().lower()
    if status not in ['approve', 'deny']:
        return False, f"Row {row_num}: Invalid actual_status '{status}'. Must be 'approve' or 'deny'"
    
    try:
        amount = float(row['actual_paid_amount'])
        if amount < 0:
            return False, f"Row {row_num}: actual_paid_amount cannot be negative"
        if status == 'deny' and amount > 0:
            logger.warning(f"Row {row_num}: Denied claim has non-zero amount. Setting to 0.00")
            row['actual_paid_amount'] = '0.00'
    except ValueError:
        return False, f"Row {row_num}: Invalid actual_paid_amount '{row['actual_paid_amount']}'"
    
    try:
        datetime.strptime(row['actual_decision_date'].strip(), '%Y-%m-%d')
    except ValueError:
        return False, f"Row {row_num}: Invalid actual_decision_date format. Expected YYYY-MM-DD"
    
    return True, None


def import_csv_to_database(csv_path: str, db_url: str, dry_run: bool = False):
    """
    Import CSV data into decision_validation table.
    
    Args:
        csv_path: Path to CSV file
        db_url: PostgreSQL connection string
        dry_run: If True, validate but don't insert
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        logger.error(f"CSV file not found: {csv_path}")
        sys.exit(1)
    
    engine = create_engine(db_url)
    
    logger.info(f"Reading CSV file: {csv_path}")
    
    rows_processed = 0
    rows_inserted = 0
    rows_skipped = 0
    errors = []
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        if not reader.fieldnames:
            logger.error("CSV file is empty or invalid")
            sys.exit(1)
        
        logger.info(f"CSV columns: {', '.join(reader.fieldnames)}")
        
        for row_num, row in enumerate(reader, start=2):
            rows_processed += 1
            
            is_valid, error_msg = validate_csv_row(row, row_num)
            if not is_valid:
                errors.append(error_msg)
                rows_skipped += 1
                continue
            
            claim_tracking = row['claim_tracking_number'].strip()
            actual_status = row['actual_status'].strip().lower()
            actual_amount = float(row['actual_paid_amount'])
            decision_date = row['actual_decision_date'].strip()
            notes = row.get('adjudication_notes', '').strip() or None
            adjudicator = row.get('adjudicator_id', '').strip() or None
            source = row.get('validation_source', 'csv_import').strip() or 'csv_import'
            
            if dry_run:
                logger.info(f"[DRY RUN] Would insert: {claim_tracking} -> {actual_status} ${actual_amount:.2f}")
                rows_inserted += 1
                continue
            
            try:
                with engine.connect() as conn:
                    result = conn.execute(
                        text("""
                            INSERT INTO decision_validation (
                                claim_id,
                                actual_status,
                                actual_paid_amount,
                                actual_decision_date,
                                adjudication_notes,
                                adjudicator_id,
                                validation_source
                            )
                            SELECT 
                                c.id,
                                :actual_status::decision_status_enum,
                                :actual_paid_amount,
                                :actual_decision_date::date,
                                :adjudication_notes,
                                :adjudicator_id,
                                :validation_source
                            FROM claims c
                            WHERE c.claim_tracking_number = :claim_tracking
                            ON CONFLICT (claim_id, actual_decision_date) 
                            DO UPDATE SET
                                actual_status = EXCLUDED.actual_status,
                                actual_paid_amount = EXCLUDED.actual_paid_amount,
                                adjudication_notes = EXCLUDED.adjudication_notes,
                                adjudicator_id = EXCLUDED.adjudicator_id,
                                validation_source = EXCLUDED.validation_source
                        """),
                        {
                            'claim_tracking': claim_tracking,
                            'actual_status': actual_status,
                            'actual_paid_amount': actual_amount,
                            'actual_decision_date': decision_date,
                            'adjudication_notes': notes,
                            'adjudicator_id': adjudicator,
                            'validation_source': source
                        }
                    )
                    conn.commit()
                    
                    if result.rowcount > 0:
                        rows_inserted += 1
                        logger.info(f"Inserted/Updated: {claim_tracking} -> {actual_status} ${actual_amount:.2f}")
                    else:
                        rows_skipped += 1
                        logger.warning(f"Claim not found: {claim_tracking}")
                        errors.append(f"Row {row_num}: Claim tracking number not found: {claim_tracking}")
            
            except SQLAlchemyError as e:
                error_msg = f"Row {row_num}: Database error - {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                rows_skipped += 1
    
    logger.info("=" * 60)
    logger.info("Import Summary:")
    logger.info(f"  Rows processed: {rows_processed}")
    logger.info(f"  Rows inserted/updated: {rows_inserted}")
    logger.info(f"  Rows skipped: {rows_skipped}")
    
    if errors:
        logger.warning(f"  Errors encountered: {len(errors)}")
        logger.info("\nErrors:")
        for error in errors[:10]:
            logger.info(f"  - {error}")
        if len(errors) > 10:
            logger.info(f"  ... and {len(errors) - 10} more errors")
    
    if dry_run:
        logger.info("\n[DRY RUN] No data was actually inserted. Run without --dry-run to import.")
    
    logger.info("=" * 60)
    
    return rows_inserted, rows_skipped, errors


def create_sample_csv(output_path: str):
    """Create a sample CSV file with the expected format."""
    sample_data = [
        {
            'claim_tracking_number': 'CLM-2024-001',
            'actual_status': 'approve',
            'actual_paid_amount': '5000.00',
            'actual_decision_date': '2024-01-20',
            'adjudication_notes': 'Approved - all items eligible',
            'adjudicator_id': 'adjudicator_001',
            'validation_source': 'historical'
        },
        {
            'claim_tracking_number': 'CLM-2024-002',
            'actual_status': 'approve',
            'actual_paid_amount': '10000.00',
            'actual_decision_date': '2024-02-15',
            'adjudication_notes': 'Approved - capped at max benefit',
            'adjudicator_id': 'adjudicator_001',
            'validation_source': 'historical'
        },
        {
            'claim_tracking_number': 'CLM-2024-003',
            'actual_status': 'deny',
            'actual_paid_amount': '0.00',
            'actual_decision_date': '2024-02-12',
            'adjudication_notes': 'Denied - missing required documents',
            'adjudicator_id': 'adjudicator_002',
            'validation_source': 'historical'
        }
    ]
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'claim_tracking_number',
            'actual_status',
            'actual_paid_amount',
            'actual_decision_date',
            'adjudication_notes',
            'adjudicator_id',
            'validation_source'
        ])
        writer.writeheader()
        writer.writerows(sample_data)
    
    logger.info(f"Sample CSV created: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import decision validation data from CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
CSV Format:
  - claim_tracking_number: Must match existing claim (required)
  - actual_status: 'approve' or 'deny' (required)
  - actual_paid_amount: Amount paid, 0.00 for denied (required)
  - actual_decision_date: YYYY-MM-DD format (required)
  - adjudication_notes: Optional notes
  - adjudicator_id: Optional user ID
  - validation_source: Source identifier (default: 'csv_import')

Example:
  python import_validation_data.py validation_data.csv --db "postgresql://user:pass@localhost/corgi_dev"
        """
    )
    
    parser.add_argument('csv_file', help='Path to CSV file with validation data')
    parser.add_argument('--db', required=True, help='PostgreSQL connection string')
    parser.add_argument('--dry-run', action='store_true', help='Validate CSV without inserting data')
    parser.add_argument('--create-sample', action='store_true', help='Create a sample CSV file and exit')
    
    args = parser.parse_args()
    
    if args.create_sample:
        sample_path = 'validation_data_sample.csv'
        create_sample_csv(sample_path)
        sys.exit(0)
    
    import_csv_to_database(args.csv_file, args.db, dry_run=args.dry_run)

