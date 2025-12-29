from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional
from uuid import uuid4
import logging
import asyncio
import json
import tempfile
import hashlib
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
    build_decision_record_dict
)
from decision_service.engine.decision_engine import DecisionEngine
from decision_service.repositories.claim_repository import ClaimRepository
from decision_service.repositories.override_repository import OverrideRepository
from decision_service.repositories.document_repository import DocumentRepository
from document_service.processor import DocumentProcessor
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/claims/{tracking_number}/decision", response_model=DecisionResponse)
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
    
    try:
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
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/claims/{tracking_number}/decision", response_model=DecisionResponse)
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
    
    try:
        repository = ClaimRepository()
        decision_record = await repository.get_latest_decision_by_tracking_number(tracking_number)
        
        if not decision_record:
            raise HTTPException(
                status_code=404, 
                detail=f"No decision found for claim with tracking number {tracking_number}. Use POST to create a new decision."
            )
        
        return DecisionResponse.from_decision_record(decision_record)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Internal server error during decision retrieval: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/claims/{tracking_number}/documents")
async def get_claim_documents(
    tracking_number: str,
    document_type: Optional[DocumentType] = Query(None, description="Filter by document type")
):
    """
    Get documents for a claim.
    
    Returns metadata for all documents associated with a claim.
    Optionally filter by document type.
    """
    from decision_service.repositories.document_repository import DocumentRepository
    
    repository = DocumentRepository()
    documents = await repository.get_documents_by_tracking_number(
        tracking_number,
        document_type=document_type.value if document_type else None
    )
    
    if not documents:
        raise HTTPException(status_code=404, detail=f"Claim with tracking number {tracking_number} not found")
    
    return documents


@router.patch("/claims/{tracking_number}/decision/{decision_id}", response_model=DecisionResponse)
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
    
    try:
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
            
            all_approved = json.loads(decision_dict['approved_line_items']) if isinstance(decision_dict['approved_line_items'], str) else (decision_dict['approved_line_items'] if decision_dict['approved_line_items'] else [])
            all_ineligible = json.loads(decision_dict['ineligible_line_items']) if isinstance(decision_dict['ineligible_line_items'], str) else (decision_dict['ineligible_line_items'] if decision_dict['ineligible_line_items'] else [])
            
            all_items = []
            item_index_map = {}
            current_index = 0
            
            for item in all_approved:
                all_items.append({**item, '_original_included': True, '_index': current_index})
                item_index_map[current_index] = item
                current_index += 1
            
            for item in all_ineligible:
                all_items.append({**item, '_original_included': False, '_index': current_index})
                item_index_map[current_index] = item
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
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Internal server error during decision update: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/claims/process-from-drive", response_model=DecisionResponse)
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
    request_id = x_request_id or str(uuid4())
    
    try:
        claim_repo = ClaimRepository()
        claim = await claim_repo.get_claim_by_tracking_number(request.tracking_number)
        
        if not claim:
            raise HTTPException(
                status_code=404,
                detail=f"Claim with tracking number {request.tracking_number} not found in database. Please create the claim first."
            )
        
        logger.info(f"Using existing claim {request.tracking_number} (ID: {claim['id']})")
        
        credentials_path = Config.GOOGLE_DRIVE_CREDENTIALS or "google-drive-credentials.json"
        if not Path(credentials_path).exists():
            raise HTTPException(
                status_code=500,
                detail=f"Google Drive credentials not found at {credentials_path}. Please set GOOGLE_DRIVE_CREDENTIALS env var or place credentials at google-drive-credentials.json"
            )
        
        drive_service = GoogleDriveService(
            credentials_path=credentials_path,
            use_service_account=Config.GOOGLE_DRIVE_USE_SERVICE_ACCOUNT
        )
        
        folder_id = drive_service.extract_folder_id_from_url(request.drive_folder_id)
        
        logger.info(f"Checking Google Drive folder {folder_id}")
        drive_files = drive_service.list_folder_files(
            folder_id=folder_id,
            file_types=['application/pdf', 'image/png', 'image/jpeg', 'image/jpg', 'image/tiff'],
            recursive=False
        )
        
        if not drive_files:
            logger.info(f"No files found in root folder, looking for subfolder '{request.tracking_number}'...")
            subfolder = drive_service.get_file_by_name(folder_id, request.tracking_number)
            
            if subfolder and 'folder' in subfolder.mime_type:
                logger.info(f"Found subfolder '{request.tracking_number}' with ID {subfolder.id}")
                folder_id = subfolder.id
                drive_files = drive_service.list_folder_files(
                    folder_id=folder_id,
                    file_types=['application/pdf', 'image/png', 'image/jpeg', 'image/jpg', 'image/tiff'],
                    recursive=False
                )
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
        
        logger.info(f"Found {len(drive_files)} files in Google Drive folder")
        
        doc_processor = DocumentProcessor()
        engine = get_engine()
        if not engine:
            raise HTTPException(status_code=500, detail="Database engine not available")
        
        async def process_single_document(drive_file):
            """Process a single document from Google Drive."""
            try:
                logger.info(f"Downloading: {drive_file.name}")
                
                loop = asyncio.get_event_loop()
                file_stream, filename, mime_type = await loop.run_in_executor(
                    None,
                    drive_service.download_file_to_stream,
                    drive_file.id
                )
                
                file_content = file_stream.read()
                file_hash = hashlib.sha256(file_content).hexdigest()
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
                    tmp_file.write(file_content)
                    tmp_path = Path(tmp_file.name)
                
                logger.info(f"Processing: {filename}")
                
                result = await doc_processor.process_document(
                    file_path=tmp_path,
                    claim_id=claim['id'],
                    processing_priority=0,
                    force_high_quality=False
                )
                
                tmp_path.unlink()
                
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
        
        logger.info(f"Processing {len(drive_files)} documents in parallel (max 3 concurrent)...")
        semaphore = asyncio.Semaphore(3)
        
        async def process_with_semaphore(drive_file):
            async with semaphore:
                return await process_single_document(drive_file)
        
        results = await asyncio.gather(*[process_with_semaphore(f) for f in drive_files], return_exceptions=True)
        processed_count = sum(1 for r in results if r is True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Exception processing {drive_files[i].name}: {result}", exc_info=result)
        
        if processed_count == 0:
            raise HTTPException(
                status_code=500,
                detail="Failed to process any documents from Google Drive"
            )
        
        logger.info(f"Processed {processed_count}/{len(drive_files)} documents")
        
        logger.info("Running decision engine...")
        decision_engine = DecisionEngine()
        decision = await decision_engine.evaluate_claim(
            claim_id=claim['id'],
            override_max_benefit=request.override_max_benefit
        )
        
        decision_record = await claim_repo.create_decision(decision, user_id="system")
        
        logger.info(f"✓ Decision created: {decision.proposed_status} ${decision.proposed_benefit_amount}")
        
        return DecisionResponse.from_decision_record(decision_record)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing claim from Google Drive: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

