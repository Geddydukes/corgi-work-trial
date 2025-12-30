from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional
from uuid import uuid4
import logging
import asyncio
import json
import tempfile
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from decision_service.schemas.request import DecisionRequest, UpdateDecisionRequest, ProcessFromDriveRequest
from decision_service.schemas.response import DecisionResponse
from shared.models import DocumentType
from shared.database import get_engine
from shared.config import Config
from shared.google_drive import GoogleDriveService
from decision_service.routes.claim_helpers import (
    process_line_item_overrides,
    calculate_cap_amount,
    determine_new_status,
    build_decision_record_dict,
    safe_json_load
)
from decision_service.routes.error_handling import handle_route_errors
from decision_service.engine.decision_engine import DecisionEngine
from decision_service.repositories.claim_repository import ClaimRepository
from decision_service.repositories.override_repository import OverrideRepository
from decision_service.repositories.document_repository import DocumentRepository
from document_service.processor import DocumentProcessor
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/claims/{tracking_number}/decision", response_model=DecisionResponse)
@handle_route_errors
async def create_decision(
    tracking_number: str,
    request: Optional[DecisionRequest] = None,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    """
    Generate decision for a claim.
    
    Synchronously generates a decision for a claim. Response time target: < 5 seconds.
    """
    if not tracking_number:
        raise HTTPException(status_code=400, detail="Tracking number is required")
    
    request_id = x_request_id or str(uuid4())
    
    engine = DecisionEngine()
    repository = ClaimRepository()
    
    claim = await repository.get_claim_by_tracking_number(tracking_number)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim with tracking number {tracking_number} not found")
    
    decision = await engine.evaluate_claim(
        claim_id=claim["id"],
        override_max_benefit=request.override_max_benefit if request else None
    )
    
    decision_record = await repository.create_decision(decision, user_id="system")
    
    return DecisionResponse.from_decision_record(decision_record)


@router.get("/claims/{tracking_number}/decision", response_model=DecisionResponse)
@handle_route_errors
async def get_decision(
    tracking_number: str,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
):
    """
    Get the latest decision for a claim.
    
    Returns the most recent decision for a claim without re-running the decision engine.
    Use POST to create a new decision.
    """
    request_id = x_request_id or str(uuid4())
    logger.info(f"Getting decision for tracking number: {tracking_number}")
    
    repository = ClaimRepository()
    try:
        decision_record = await repository.get_latest_decision_by_tracking_number(tracking_number)
    except TimeoutError as e:
        logger.error(f"Database query timed out for tracking number: {tracking_number} - {e}")
        raise HTTPException(
            status_code=504,
            detail=f"Database query timed out after 10 seconds. The server took too long to respond. Please try again or check if the database is accessible."
        )
    except Exception as e:
        logger.error(f"Unexpected error getting decision: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while fetching decision: {str(e)}"
        )
    
    if not decision_record:
        logger.info(f"No decision found for tracking number: {tracking_number}")
        raise HTTPException(
            status_code=404, 
            detail=f"No decision found for claim with tracking number {tracking_number}. Use POST to create a new decision."
        )
    
    logger.info(f"Found decision {decision_record.get('id')} for tracking number: {tracking_number}")
    return DecisionResponse.from_decision_record(decision_record)


@router.get("/claims/{tracking_number}/documents")
@handle_route_errors
async def get_claim_documents(
    tracking_number: str,
    document_type: Optional[DocumentType] = Query(None, description="Filter by document type")
):
    """
    Get documents for a claim.
    
    Returns metadata for all documents associated with a claim.
    Optionally filter by document type.
    """
    repository = DocumentRepository()
    documents = await repository.get_documents_by_tracking_number(
        tracking_number,
        document_type=document_type.value if document_type else None
    )
    
    if not documents:
        raise HTTPException(status_code=404, detail=f"Claim with tracking number {tracking_number} not found")
    
    return documents


@router.patch("/claims/{tracking_number}/decision/{decision_id}", response_model=DecisionResponse)
@handle_route_errors
async def update_decision(
    tracking_number: str,
    decision_id: int,
    request: UpdateDecisionRequest,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
):
    """
    Update a decision with user overrides.
    
    Updates line item approvals based on user input and stores overrides for rule refinement.
    """
    request_id = x_request_id or str(uuid4())
    claim_repo = ClaimRepository()
    override_repo = OverrideRepository()
    
    claim = await claim_repo.get_claim_by_tracking_number(tracking_number)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim with tracking number {tracking_number} not found")
    
    if not Config.DATABASE_URL:
        raise HTTPException(status_code=500, detail="Database not configured")
    
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=500, detail="Database engine not available")
    with engine.connect() as conn:
            conn.execute(text("SET search_path TO claims, public"))
            
            decision_result = conn.execute(
                text("""
                    SELECT id, claim_id, approved_line_items, ineligible_line_items,
                           decision_type, proposed_status, proposed_benefit_amount,
                           eligible_total, invoice_total, cap_amount, flags, missing_data,
                           reasoning, confidence_score, engine_version, processing_time_ms,
                           decided_at
                    FROM decisions
                    WHERE id = :decision_id AND claim_id = :claim_id
                """),
                {'decision_id': decision_id, 'claim_id': claim['id']}
            ).fetchone()
            
            if not decision_result:
                raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
            
            decision_cols = ['id', 'claim_id', 'approved_line_items', 'ineligible_line_items',
                            'decision_type', 'proposed_status', 'proposed_benefit_amount',
                            'eligible_total', 'invoice_total', 'cap_amount', 'flags', 'missing_data',
                            'reasoning', 'confidence_score', 'engine_version', 'processing_time_ms',
                            'decided_at']
            decision_dict = {col: decision_result[i] for i, col in enumerate(decision_cols)}
            
            all_approved = safe_json_load(decision_dict['approved_line_items'], default=[])
            all_ineligible = safe_json_load(decision_dict['ineligible_line_items'], default=[])
            
            all_items = []
            current_index = 0
            
            for item in all_approved:
                all_items.append({**item, '_original_included': True, '_index': current_index})
                current_index += 1
            
            for item in all_ineligible:
                all_items.append({**item, '_original_included': False, '_index': current_index})
                current_index += 1
            
            override_map = {}
            for override in request.approved_line_items:
                override_map[override.line_item_index] = {
                    'should_be_included': True,
                    'reasoning': override.user_reasoning
                }
            for override in request.ineligible_line_items:
                override_map[override.line_item_index] = {
                    'should_be_included': False,
                    'reasoning': override.user_reasoning
                }
            
            original_included_map = {
                index: item.get('_original_included', False)
                for index, item in enumerate(all_items)
            }
            
            new_approved, new_ineligible, overrides_to_save = process_line_item_overrides(
                all_items, override_map, original_included_map
            )
            
            new_eligible_total = sum(item['amount'] for item in new_approved)
            new_proposed_benefit = new_eligible_total
            
            new_cap_amount = calculate_cap_amount(
                request.cap_enabled,
                request.override_cap_amount,
                decision_dict['cap_amount']
            )
            
            if new_cap_amount is not None and new_proposed_benefit > new_cap_amount:
                new_proposed_benefit = new_cap_amount
            
            new_status = determine_new_status(
                decision_dict['proposed_status'],
                request.override_status,
                new_proposed_benefit,
                len(new_approved)
            )
            
            conn.execute(
                text("""
                    UPDATE decisions
                    SET approved_line_items = CAST(:approved AS jsonb),
                        ineligible_line_items = CAST(:ineligible AS jsonb),
                        eligible_total = :eligible_total,
                        proposed_benefit_amount = :benefit_amount,
                        proposed_status = CAST(:proposed_status AS decision_status_enum),
                        cap_amount = :cap_amount,
                        decision_type = CAST('reconsideration' AS decision_type_enum),
                        decided_by = 'user'
                    WHERE id = :decision_id
                """),
                {
                    'decision_id': decision_id,
                    'approved': json.dumps(new_approved),
                    'ineligible': json.dumps(new_ineligible),
                    'eligible_total': new_eligible_total,
                    'benefit_amount': new_proposed_benefit,
                    'proposed_status': new_status,
                    'cap_amount': new_cap_amount
                }
            )
            
            await override_repo.save_line_item_overrides(
                decision_id=decision_id,
                claim_id=claim['id'],
                overrides=overrides_to_save,
                user_id='user',
                user_role='reviewer'
            )
            
            conn.commit()
            
            updated_result = conn.execute(
                text("""
                    SELECT 
                        d.id, d.claim_id, d.approved_line_items, d.ineligible_line_items,
                        d.decision_type, d.proposed_status, d.proposed_benefit_amount,
                        d.eligible_total, d.invoice_total, d.cap_amount, d.flags, d.missing_data,
                        d.reasoning, d.confidence_score, d.engine_version, d.processing_time_ms,
                        d.decided_at, c.claim_tracking_number
                    FROM decisions d
                    JOIN claims c ON c.id = d.claim_id
                    WHERE d.id = :decision_id
                """),
                {'decision_id': decision_id}
            ).fetchone()
            
            tracking_number = None
            if updated_result:
                updated_cols = ['id', 'claim_id', 'approved_line_items', 'ineligible_line_items',
                               'decision_type', 'proposed_status', 'proposed_benefit_amount',
                               'eligible_total', 'invoice_total', 'cap_amount', 'flags', 'missing_data',
                               'reasoning', 'confidence_score', 'engine_version', 'processing_time_ms',
                               'decided_at', 'claim_tracking_number']
                updated_dict_temp = {col: updated_result[i] for i, col in enumerate(updated_cols)}
                tracking_number = updated_dict_temp['claim_tracking_number']
            
            updated_cols = ['id', 'claim_id', 'approved_line_items', 'ineligible_line_items',
                           'decision_type', 'proposed_status', 'proposed_benefit_amount',
                           'eligible_total', 'invoice_total', 'cap_amount', 'flags', 'missing_data',
                           'reasoning', 'confidence_score', 'engine_version', 'processing_time_ms',
                           'decided_at', 'claim_tracking_number']
            updated_dict = {col: updated_result[i] for i, col in enumerate(updated_cols)} if updated_result else {}
            
            decision_record = build_decision_record_dict(
                updated_dict, tracking_number, claim, new_approved, new_ineligible
            )
            
            return DecisionResponse.from_decision_record(decision_record)


@router.post("/claims/process-from-drive", response_model=DecisionResponse)
@handle_route_errors
async def process_claim_from_drive(
    request: ProcessFromDriveRequest,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
):
    """
    Process a claim from Google Drive documents.
    
    This endpoint:
    1. Creates the claim if it doesn't exist
    2. Fetches documents from the specified Google Drive folder
    3. Processes documents (OCR, classification)
    4. Runs the decision engine
    5. Returns the decision
    
    Use this for claims that aren't already in the database.
    """
    start_time = time.time()
    request_id = x_request_id or str(uuid4())
    logger.info(f"[{request_id}] Starting process-from-drive for tracking_number={request.tracking_number}")
    
    step_start = time.time()
    claim_repo = ClaimRepository()
    claim = await claim_repo.get_claim_by_tracking_number(request.tracking_number)
    logger.info(f"[{request_id}] Claim lookup took {time.time() - step_start:.2f}s")
    
    if not claim:
        logger.info(f"[{request_id}] Claim {request.tracking_number} not found in database, creating new claim...")
        step_start = time.time()
        # Create a new claim with minimal information - we'll get more details from Google Drive
        # Use default values that can be updated later
        claim = await claim_repo.create_or_get_claim(
            tracking_number=request.tracking_number,
            claim_amount=0.0,  # Will be updated from documents
            max_benefit=None,  # Will be calculated
            claim_date="2024-01-01",  # Default, will be updated from documents
            policyholder_id=None,
            property_id=None,
            lease_start_date=None,
            lease_end_date=None,
            move_out_date=None,
            security_deposit_amount=None
        )
        logger.info(f"[{request_id}] Created new claim {request.tracking_number} (ID: {claim['id']}) in {time.time() - step_start:.2f}s")
    else:
        logger.info(f"[{request_id}] Using existing claim {request.tracking_number} (ID: {claim['id']})")
    
    step_start = time.time()
    credentials_path = Config.GOOGLE_DRIVE_CREDENTIALS or "google-drive-credentials.json"
    credentials_path_obj = Path(credentials_path)
    if not credentials_path_obj.is_absolute():
        project_root = Path(__file__).parent.parent.parent
        credentials_path_obj = project_root / credentials_path
    
    if not credentials_path_obj.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Google Drive credentials not found at {credentials_path_obj}. Please set GOOGLE_DRIVE_CREDENTIALS env var or place credentials at google-drive-credentials.json"
        )
    
    credentials_path = str(credentials_path_obj)
    logger.info(f"[{request_id}] Credentials path setup took {time.time() - step_start:.2f}s")
    
    step_start = time.time()
    drive_service = GoogleDriveService(
        credentials_path=credentials_path,
        use_service_account=Config.GOOGLE_DRIVE_USE_SERVICE_ACCOUNT
    )
    logger.info(f"[{request_id}] GoogleDriveService initialization took {time.time() - step_start:.2f}s")
    
    step_start = time.time()
    folder_id = drive_service.extract_folder_id_from_url(request.drive_folder_id)
    logger.info(f"[{request_id}] Extracted folder_id={folder_id} in {time.time() - step_start:.2f}s")
    
    step_start = time.time()
    logger.info(f"[{request_id}] Listing files in Google Drive folder {folder_id}...")
    drive_files = drive_service.list_folder_files(
        folder_id=folder_id,
        file_types=['application/pdf', 'image/png', 'image/jpeg', 'image/jpg', 'image/tiff'],
        recursive=False
    )
    logger.info(f"[{request_id}] list_folder_files took {time.time() - step_start:.2f}s, found {len(drive_files) if drive_files else 0} files")
    
    if not drive_files:
        step_start = time.time()
        logger.info(f"[{request_id}] No files found in root folder, looking for subfolder '{request.tracking_number}'...")
        subfolder = drive_service.get_file_by_name(folder_id, request.tracking_number)
        logger.info(f"[{request_id}] get_file_by_name took {time.time() - step_start:.2f}s")
        
        if subfolder and 'folder' in subfolder.mime_type:
            logger.info(f"[{request_id}] Found subfolder '{request.tracking_number}' with ID {subfolder.id}")
            folder_id = subfolder.id
            step_start = time.time()
            drive_files = drive_service.list_folder_files(
                folder_id=folder_id,
                file_types=['application/pdf', 'image/png', 'image/jpeg', 'image/jpg', 'image/tiff'],
                recursive=False
            )
            logger.info(f"[{request_id}] list_folder_files (subfolder) took {time.time() - step_start:.2f}s, found {len(drive_files) if drive_files else 0} files")
        else:
            all_items = drive_service.list_folder_files(folder_id, recursive=False)
            folders = [item for item in all_items if 'folder' in item.mime_type]
            if folders:
                folder_names = [f.name for f in folders[:10]]
                raise HTTPException(
                    status_code=404,
                    detail=f"No documents found in folder {folder_id} and no subfolder named '{request.tracking_number}' found. Available subfolders: {', '.join(folder_names)}"
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"No documents found in Google Drive folder {folder_id}"
                )
    
    if not drive_files:
        raise HTTPException(
            status_code=404,
            detail=f"No documents found in Google Drive folder {folder_id}"
        )
    
    logger.info(f"[{request_id}] Found {len(drive_files)} files in Google Drive folder")
    
    # Priority keywords for relevant documents
    PRIORITY_KEYWORDS = ("addendum", "move-out", "move out", "moveout", "invoice", "itemization", "final statement")
    # Secondary keywords (less priority but still useful)
    SECONDARY_KEYWORDS = ("statement", "charges", "deposit")
    # Keywords to explicitly skip (reduce load - these are large documents with minimal value)
    # - ledger: Long transaction history, not needed for line item extraction
    # - application: Rental application, not relevant to deposit claims
    # - lease: Large (20+ pages), lease_text is optional for improper notice check
    # - id/license/identification: ID documents, not relevant
    SKIP_KEYWORDS = ("ledger", "application", "lease", "id", "license", "identification")
    
    # First pass: priority documents only
    priority_files = [
        f for f in drive_files
        if f.mime_type == "application/pdf" 
        and any(k in f.name.lower() for k in PRIORITY_KEYWORDS)
        and not any(k in f.name.lower() for k in SKIP_KEYWORDS)
    ]
    
    if priority_files:
        logger.info(f"[{request_id}] Filtered to {len(priority_files)} priority documents (addendum/invoice/move-out/itemization)")
        drive_files = priority_files
    else:
        # Second pass: include secondary documents
        secondary_files = [
            f for f in drive_files
            if f.mime_type == "application/pdf"
            and any(k in f.name.lower() for k in SECONDARY_KEYWORDS)
            and not any(k in f.name.lower() for k in SKIP_KEYWORDS)
        ]
        
        if secondary_files:
            logger.info(f"[{request_id}] Filtered to {len(secondary_files)} secondary documents (statement/charges/deposit)")
            drive_files = secondary_files
        else:
            # Final fallback: all PDFs except skip keywords, capped at 5 files
            fallback_files = [
                f for f in drive_files
                if f.mime_type == "application/pdf"
                and not any(k in f.name.lower() for k in SKIP_KEYWORDS)
            ][:5]  # Cap at 5 to reduce load
            
            if fallback_files:
                logger.warning(f"[{request_id}] No keyword matches, using {len(fallback_files)} PDFs (capped at 5)")
                drive_files = fallback_files
            else:
                logger.warning(f"[{request_id}] No relevant files found after filtering")
    
    step_start = time.time()
    doc_processor = DocumentProcessor()
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=500, detail="Database engine not available")
    logger.info(f"[{request_id}] DocumentProcessor and engine setup took {time.time() - step_start:.2f}s")
    
    async def process_single_document(drive_file, cached_meta=None):
        """Process a single document from Google Drive."""
        doc_start = time.time()
        doc_id = f"{request_id}-{drive_file.id}"
        try:
            logger.info(f"[{doc_id}] Starting download: {drive_file.name}")
            download_start = time.time()
            
            loop = asyncio.get_event_loop()
            # Use cached metadata if available to skip metadata API call
            file_stream, filename, mime_type = await loop.run_in_executor(
                None,
                lambda: drive_service.download_file_to_stream(drive_file.id, cached_metadata=cached_meta)
            )
            logger.info(f"[{doc_id}] Download took {time.time() - download_start:.2f}s (metadata cached: {cached_meta is not None})")
            
            hash_start = time.time()
            file_content = file_stream.read()
            file_hash = hashlib.sha256(file_content).hexdigest()
            logger.info(f"[{doc_id}] File hash calculation took {time.time() - hash_start:.2f}s")
            
            write_start = time.time()
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
                tmp_file.write(file_content)
                tmp_path = Path(tmp_file.name)
            logger.info(f"[{doc_id}] Temp file write took {time.time() - write_start:.2f}s")
            
            process_start = time.time()
            logger.info(f"[{doc_id}] Processing document: {filename}")
            
            result = await doc_processor.process_document(
                file_path=tmp_path,
                claim_id=claim['id'],
                processing_priority=0,
                force_high_quality=False
            )
            logger.info(f"[{doc_id}] Document processing took {time.time() - process_start:.2f}s")
            
            cleanup_start = time.time()
            tmp_path.unlink()
            logger.info(f"[{doc_id}] Cleanup took {time.time() - cleanup_start:.2f}s")
            logger.info(f"[{doc_id}] Total document processing time: {time.time() - doc_start:.2f}s")
            
            if result.errors:
                error_messages = [e.message for e in result.errors]
                logger.error(f"Error processing {filename}: {', '.join(error_messages)}")
                return None
            
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                conn.execute(
                    text("""
                        INSERT INTO claim_documents (
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
                            document_type = EXCLUDED.document_type,
                            classification_confidence = EXCLUDED.classification_confidence,
                            ocr_confidence = EXCLUDED.ocr_confidence,
                            page_count = EXCLUDED.page_count,
                            processing_status = 'completed',
                            processed_at = NOW()
                    """),
                    {
                        'claim_id': claim['id'],
                        'file_path': f"drive://{drive_file.id}",
                        'filename': filename,
                        'file_hash': file_hash,
                        'size': drive_file.size,
                        'mime_type': mime_type,
                        'doc_type': result.classification.document_type.value,
                        'class_conf': result.classification.confidence,
                        'text': result.best_extraction.text,
                        'ocr_conf': result.quality_metrics.avg_ocr_confidence,
                        'pages': result.processing_metrics.pages_processed,
                    }
                )
                conn.commit()
            
            logger.info(f"✓ Processed: {result.classification.document_type.value} (confidence: {result.classification.confidence:.1f}%)")
            return True
            
        except Exception as e:
            logger.error(f"Error processing document {drive_file.name}: {e}", exc_info=True)
            return None
    
    step_start = time.time()
    
    # OPTIMIZATION: Batch fetch metadata first to reduce API calls
    file_ids = [f.id for f in drive_files]
    logger.info(f"[{request_id}] Batch fetching metadata for {len(file_ids)} files...")
    
    loop = asyncio.get_event_loop()
    metadata_cache = await loop.run_in_executor(
        None,
        drive_service.batch_get_metadata,
        file_ids
    )
    logger.info(f"[{request_id}] Batch metadata fetch completed in {time.time() - step_start:.2f}s")
    
    # Process documents sequentially with small delay to avoid SSL pool exhaustion
    # This is more reliable than parallel processing under load
    logger.info(f"[{request_id}] Processing {len(drive_files)} documents (sequential with 0.3s delay)...")
    
    results = []
    for i, drive_file in enumerate(drive_files):
        logger.info(f"[{request_id}] Processing document {i+1}/{len(drive_files)}: {drive_file.name}")
        # Pass cached metadata to avoid redundant API calls
        cached_meta = metadata_cache.get(drive_file.id)
        result = await process_single_document(drive_file, cached_meta=cached_meta)
        results.append(result)
        
        # Small delay between downloads to avoid connection pool issues
        if i < len(drive_files) - 1:
            await asyncio.sleep(0.3)
    processed_count = sum(1 for r in results if r is True)
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Exception processing {drive_files[i].name}: {result}", exc_info=result)
    
    if processed_count == 0:
        raise HTTPException(
            status_code=500,
            detail="Failed to process any documents from Google Drive"
        )
    
    logger.info(f"[{request_id}] Processed {processed_count}/{len(drive_files)} documents")
    logger.info(f"[{request_id}] Document processing phase took {time.time() - step_start:.2f}s")
    
    step_start = time.time()
    logger.info(f"[{request_id}] Running decision engine...")
    decision_engine = DecisionEngine()
    decision = await decision_engine.evaluate_claim(
        claim_id=claim['id'],
        override_max_benefit=request.override_max_benefit
    )
    logger.info(f"[{request_id}] Decision engine evaluation took {time.time() - step_start:.2f}s")
    
    step_start = time.time()
    decision_record = await claim_repo.create_decision(decision, user_id="system")
    logger.info(f"[{request_id}] Decision record creation took {time.time() - step_start:.2f}s")
    
    total_time = time.time() - start_time
    logger.info(f"[{request_id}] ✓ Decision created: {decision.proposed_status} ${decision.proposed_benefit_amount}")
    logger.info(f"[{request_id}] ⏱️  Total process-from-drive time: {total_time:.2f}s")
    
    return DecisionResponse.from_decision_record(decision_record)


@router.get("/claims/{tracking_number}/variance")
@handle_route_errors
async def get_variance(
    tracking_number: str,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
):
    """
    Get variance data comparing proposed decision to actual decision.
    
    Returns actual decision data from decision_validation table if available.
    """
    request_id = x_request_id or str(uuid4())
    logger.info(f"Getting variance data for tracking number: {tracking_number}")
    
    repository = ClaimRepository()
    claim = await repository.get_claim_by_tracking_number(tracking_number)
    
    if not claim:
        raise HTTPException(
            status_code=404,
            detail=f"Claim with tracking number {tracking_number} not found"
        )
    
    variance_data = await repository.get_variance_data(claim["id"])
    
    if not variance_data:
        raise HTTPException(
            status_code=404,
            detail=f"No actual decision found for claim with tracking number {tracking_number}"
        )
    
    return variance_data

