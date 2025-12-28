#!/usr/bin/env python3
"""
Process all documents from a Google Drive folder.

This script:
1. Connects to Google Drive
2. Lists all files in the specified folder
3. Downloads and processes each file
4. Associates files with claims based on tracking numbers or filenames
5. Stores results in the database
"""

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import re
import tempfile
from sqlalchemy import create_engine, text

from shared.google_drive import GoogleDriveService
from document_service.processor import DocumentProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_tracking_number(filename: str, folder_name: Optional[str] = None) -> Optional[str]:
    """
    Extract claim tracking number from filename or folder name.
    
    Args:
        filename: Name of the file
        folder_name: Optional folder name (for numbered subfolders)
    """
    if folder_name:
        match = re.match(r'^(\d+)$', folder_name.strip())
        if match:
            return match.group(1)
    
    patterns = [
        r'CLM[_-]?(\d+)',  # CLM-2024-001, CLM_2024_001, CLM2024001
        r'(\d{4,})',  # Any 4+ digit number
        r'Claim[_-]?(\d+)',  # Claim-123, Claim_123
        r'^(\d+)$',  # Just a number
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            return match.group(1) if len(match.groups()) > 0 else match.group(0)
    
    return None


async def get_claim_id_from_tracking(db_url: str, tracking_number: str) -> Optional[int]:
    """Get claim ID from tracking number."""
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SET search_path TO claims, public"))
            result = conn.execute(
                text("SELECT id FROM claims.claims WHERE claim_tracking_number = :tracking"),
                {'tracking': tracking_number}
            )
            row = result.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"Error looking up claim {tracking_number}: {e}")
        return None


async def process_drive_folder(
    folder_url_or_id: str,
    credentials_path: str,
    db_url: str,
    use_service_account: bool = True,
    file_types: Optional[list] = None,
    recursive: bool = True,
    dry_run: bool = False,
    numbered_subfolders: bool = False
):
    """
    Process all files from a Google Drive folder.
    
    Args:
        folder_url_or_id: Google Drive folder URL or ID
        credentials_path: Path to service account JSON or OAuth credentials
        db_url: PostgreSQL connection string
        use_service_account: Use service account authentication
        file_types: Optional list of MIME types to process (default: PDF, images)
        recursive: Process files in subfolders
        dry_run: If True, only list files without processing
    """
    if file_types is None:
        file_types = [
            'application/pdf',
            'image/png',
            'image/jpeg',
            'image/jpg',
            'image/tiff',
            'image/tif'
        ]
    
    logger.info("=" * 60)
    logger.info("Google Drive Folder Processor")
    logger.info("=" * 60)
    
    drive_service = GoogleDriveService(
        credentials_path=credentials_path,
        use_service_account=use_service_account
    )
    
    folder_id = drive_service.extract_folder_id_from_url(folder_url_or_id)
    logger.info(f"Folder ID: {folder_id}")
    
    if numbered_subfolders:
        logger.info("Processing numbered subfolders structure...")
        files_to_process = []
        
        service = drive_service._get_service()
        try:
            subfolders_result = service.files().list(
                q=f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)"
            ).execute()
            subfolders = subfolders_result.get('files', [])
        except Exception as e:
            logger.error(f"Error listing subfolders: {e}")
            subfolders = []
        
        logger.info(f"Found {len(subfolders)} subfolders")
        
        for subfolder in subfolders:
            subfolder_id = subfolder['id']
            subfolder_name = subfolder['name']
            tracking_number = extract_tracking_number(subfolder_name, folder_name=subfolder_name)
            
            logger.info(f"\nProcessing subfolder: {subfolder_name} (ID: {subfolder_id})")
            
            if not tracking_number:
                logger.warning(f"  ⚠ Could not extract tracking number from folder name: {subfolder_name}")
                continue
            
            logger.info(f"  → Tracking number: {tracking_number}")
            
            subfolder_files = drive_service.list_folder_files(
                folder_id=subfolder_id,
                file_types=file_types,
                recursive=False
            )
            
            logger.info(f"  → Found {len(subfolder_files)} files in subfolder")
            
            for file in subfolder_files:
                files_to_process.append((file, tracking_number, subfolder_name))
        
        files = [f[0] for f in files_to_process]
        logger.info(f"\nTotal files to process: {len(files)}")
        
        if dry_run:
            logger.info("\nFiles that would be processed:")
            for file, tracking, folder in files_to_process[:20]:
                logger.info(f"  - [{folder}] {file.name} → Tracking: {tracking}")
            if len(files_to_process) > 20:
                logger.info(f"  ... and {len(files_to_process) - 20} more files")
            return
    else:
        logger.info("Listing files in folder...")
        files = drive_service.list_folder_files(
            folder_id=folder_id,
            file_types=file_types,
            recursive=recursive
        )
        
        logger.info(f"Found {len(files)} files to process")
        files_to_process = [(file, None, None) for file in files]
        
        if dry_run:
            logger.info("\nFiles that would be processed:")
            for file in files[:20]:
                logger.info(f"  - {file.name} ({file.mime_type}, {file.size} bytes)")
            if len(files) > 20:
                logger.info(f"  ... and {len(files) - 20} more files")
            return
    
    processor = DocumentProcessor()
    processed = 0
    skipped = 0
    errors = 0
    
    for i, (drive_file, folder_tracking, folder_name) in enumerate(files_to_process, 1):
        logger.info(f"\n[{i}/{len(files_to_process)}] Processing: {drive_file.name}")
        if folder_name:
            logger.info(f"  → From folder: {folder_name}")
        
        try:
            tracking_number = folder_tracking or extract_tracking_number(drive_file.name)
            
            if not tracking_number:
                logger.warning(f"  ⚠ Could not extract tracking number")
                claim_id = None
            else:
                logger.info(f"  → Tracking number: {tracking_number}")
                claim_id = await get_claim_id_from_tracking(db_url, tracking_number)
                
                if not claim_id:
                    logger.warning(f"  ⚠ Claim not found for tracking number: {tracking_number}")
                    claim_id = None
            
            if not claim_id:
                logger.warning(f"  ⚠ Skipping - no claim ID found")
                skipped += 1
                continue
            
            logger.info(f"  → Claim ID: {claim_id}")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(drive_file.name).suffix) as tmp_file:
                file_stream, _, _ = drive_service.download_file_to_stream(drive_file.id)
                tmp_file.write(file_stream.read())
                tmp_path = Path(tmp_file.name)
            
            logger.info(f"  → Processing document...")
            result = await processor.process_document(
                file_path=tmp_path,
                claim_id=claim_id,
                processing_priority=0,
                force_high_quality=False
            )
            
            tmp_path.unlink()
            
            if result.processing_error:
                logger.error(f"  ✗ Processing error: {result.processing_error}")
                errors += 1
            else:
                logger.info(f"  ✓ Processed successfully")
                logger.info(f"    - Type: {result.classification.document_type}")
                logger.info(f"    - Confidence: {result.classification.confidence:.1f}%")
                logger.info(f"    - OCR Confidence: {result.best_extraction.confidence:.1f}%")
                processed += 1
        
        except Exception as e:
            logger.error(f"  ✗ Error processing {drive_file.name}: {e}")
            errors += 1
    
    logger.info("\n" + "=" * 60)
    logger.info("Processing Summary:")
    logger.info(f"  Processed: {processed}")
    logger.info(f"  Skipped: {skipped}")
    logger.info(f"  Errors: {errors}")
    logger.info(f"  Total: {len(files_to_process)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process documents from Google Drive folder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all PDFs from a folder (service account)
  python process_drive_folder.py \\
    --folder "https://drive.google.com/drive/folders/FOLDER_ID" \\
    --credentials service_account.json \\
    --db "postgresql://user:pass@localhost/corgi_dev"
  
  # Process with OAuth (interactive)
  python process_drive_folder.py \\
    --folder FOLDER_ID \\
    --credentials credentials.json \\
    --oauth \\
    --db "postgresql://user:pass@localhost/corgi_dev"
  
  # Dry run (list files only)
  python process_drive_folder.py \\
    --folder FOLDER_ID \\
    --credentials service_account.json \\
    --db "postgresql://user:pass@localhost/corgi_dev" \\
    --dry-run
        """
    )
    
    parser.add_argument(
        '--folder',
        required=True,
        help='Google Drive folder URL or ID'
    )
    parser.add_argument(
        '--credentials',
        required=True,
        help='Path to service account JSON or OAuth credentials file'
    )
    parser.add_argument(
        '--db',
        required=True,
        help='PostgreSQL connection string'
    )
    parser.add_argument(
        '--oauth',
        action='store_true',
        help='Use OAuth instead of service account'
    )
    parser.add_argument(
        '--recursive',
        action='store_true',
        help='Process files in subfolders'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='List files without processing'
    )
    parser.add_argument(
        '--file-types',
        nargs='+',
        help='MIME types to process (default: PDF and images)'
    )
    parser.add_argument(
        '--numbered-subfolders',
        action='store_true',
        help='Process numbered subfolders (folder names match tracking numbers)'
    )
    
    args = parser.parse_args()
    
    asyncio.run(process_drive_folder(
        folder_url_or_id=args.folder,
        credentials_path=args.credentials,
        db_url=args.db,
        use_service_account=not args.oauth,
        file_types=args.file_types,
        recursive=args.recursive,
        dry_run=args.dry_run,
        numbered_subfolders=args.numbered_subfolders
    ))

