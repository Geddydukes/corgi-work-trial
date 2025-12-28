from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional
from uuid import uuid4
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

from decision_service.schemas.request import DecisionRequest, UpdateDecisionRequest, ProcessFromDriveRequest
from decision_service.schemas.response import DecisionResponse
from shared.models import DocumentType

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
        from decision_service.engine.decision_engine import DecisionEngine
        from decision_service.repositories.claim_repository import ClaimRepository
        
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
        from decision_service.repositories.claim_repository import ClaimRepository
        
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
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.override_repository import OverrideRepository
        from sqlalchemy import create_engine, text
        from shared.config import Config
        import json
        
        claim_repo = ClaimRepository()
        override_repo = OverrideRepository()
        
        claim = await claim_repo.get_claim_by_tracking_number(tracking_number)
        if not claim:
            raise HTTPException(status_code=404, detail=f"Claim with tracking number {tracking_number} not found")
        
        # Get the decision
        if not Config.DATABASE_URL:
            raise HTTPException(status_code=500, detail="Database not configured")
        
        engine = create_engine(Config.DATABASE_URL)
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
            
            # Get all line items (approved + ineligible)
            all_approved = json.loads(decision_result[2]) if isinstance(decision_result[2], str) else (decision_result[2] if decision_result[2] else [])
            all_ineligible = json.loads(decision_result[3]) if isinstance(decision_result[3], str) else (decision_result[3] if decision_result[3] else [])
            
            # Create index maps for quick lookup
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
            
            # Create override map for quick lookup
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
            
            # Process all items based on overrides
            overrides_to_save = []
            new_approved = []
            new_ineligible = []
            
            for index, item in enumerate(all_items):
                original_included = item.get('_original_included', False)
                override = override_map.get(index)
                
                # Determine if item should be included (override or original)
                should_be_included = override['should_be_included'] if override is not None else original_included
                
                # Extract line item data - handle both simple format and complex format
                if isinstance(item, dict):
                    if 'line_item' in item:
                        line_item_data = item['line_item']
                        analysis = item.get('analysis', {})
                    else:
                        line_item_data = item
                        analysis = {}
                else:
                    line_item_data = {'description': str(item), 'amount': 0}
                    analysis = {}
                
                # Get reason from override, analysis, or item
                reason = None
                if override and override.get('reasoning'):
                    reason = override['reasoning']
                elif analysis:
                    reason = analysis.get('reasoning') or analysis.get('reason')
                elif isinstance(item, dict):
                    reason = item.get('reason')
                
                # Build simple line item for response
                simple_item = {
                    'description': line_item_data.get('description', ''),
                    'amount': float(line_item_data.get('amount', 0)),
                    'reason': reason
                }
                
                if should_be_included:
                    new_approved.append(simple_item)
                else:
                    new_ineligible.append(simple_item)
                
                # Save override if changed
                if override and override['should_be_included'] != original_included:
                    overrides_to_save.append({
                        'line_item_index': index,
                        'line_item_description': line_item_data.get('description', ''),
                        'line_item_amount': float(line_item_data.get('amount', 0)),
                        'system_should_be_included': original_included,
                        'system_categories': json.dumps({
                            'is_rent': item.get('is_rent', False) if isinstance(item, dict) else False,
                            'is_cleaning': item.get('is_cleaning', False) if isinstance(item, dict) else False,
                            'is_repair': item.get('is_repair', False) if isinstance(item, dict) else False,
                            'is_damage': item.get('is_damage', False) if isinstance(item, dict) else False,
                        }),
                        'system_reasoning': analysis.get('reasoning') or analysis.get('reason') if analysis else None,
                        'system_confidence': float(analysis.get('confidence', 0.5)) if analysis and analysis.get('confidence') else None,
                        'user_should_be_included': override['should_be_included'],
                        'user_reasoning': override.get('reasoning')
                    })
            
            # Calculate new totals
            new_eligible_total = sum(item['amount'] for item in new_approved)
            new_proposed_benefit = new_eligible_total
            
            # Determine new cap amount
            new_cap_amount = None
            if request.cap_enabled:
                # Use override cap if provided, otherwise use original cap
                if request.override_cap_amount is not None:
                    new_cap_amount = float(request.override_cap_amount)
                else:
                    new_cap_amount = float(decision_result[9]) if decision_result[9] else None
                
                if new_cap_amount is not None and new_proposed_benefit > new_cap_amount:
                    new_proposed_benefit = new_cap_amount
            # If cap is disabled, new_proposed_benefit stays as new_eligible_total and cap_amount is None
            
            # Determine new status (allow override from deny to approve)
            original_status = decision_result[5]  # proposed_status
            new_status = original_status
            if request.override_status:
                # Validate status override
                if request.override_status.lower() in ['approve', 'deny', 'pending']:
                    new_status = request.override_status.lower()
                else:
                    logger.warning(f"Invalid status override: {request.override_status}, keeping original status")
            
            # If status is being changed to approve and there's a benefit amount, ensure status is approve
            if new_proposed_benefit > 0 and new_status == 'deny':
                # If user is overriding to approve, use that
                if request.override_status and request.override_status.lower() == 'approve':
                    new_status = 'approve'
                # Otherwise, if there are approved items, auto-change to approve
                elif len(new_approved) > 0:
                    new_status = 'approve'
            
            # Update decision
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
            
            # Save overrides
            await override_repo.save_line_item_overrides(
                decision_id=decision_id,
                claim_id=claim['id'],
                overrides=overrides_to_save,
                user_id='user',
                user_role='reviewer'
            )
            
            conn.commit()
            
            # Get updated decision
            updated_result = conn.execute(
                text("""
                    SELECT id, claim_id, approved_line_items, ineligible_line_items,
                           decision_type, proposed_status, proposed_benefit_amount,
                           eligible_total, invoice_total, cap_amount, flags, missing_data,
                           reasoning, confidence_score, engine_version, processing_time_ms,
                           decided_at
                    FROM decisions
                    WHERE id = :decision_id
                """),
                {'decision_id': decision_id}
            ).fetchone()
            
            tracking_result = conn.execute(
                text("SELECT claim_tracking_number FROM claims WHERE id = :claim_id"),
                {"claim_id": claim['id']}
            ).fetchone()
            tracking_number = tracking_result[0] if tracking_result else None
            
            decision_record = {
                "id": updated_result[0],
                "claim_id": updated_result[1],
                "tracking_number": tracking_number,
                "decision_type": updated_result[4],
                "proposed_status": updated_result[5],
                "proposed_benefit_amount": float(updated_result[6]),
                "eligible_total": float(updated_result[7]),
                "invoice_total": float(updated_result[8]),
                "cap_amount": float(updated_result[9]) if updated_result[9] else None,
                "claim_amount": float(claim.get('claim_amount', 0)),
                "max_benefit": float(claim.get('max_benefit', 0)) if claim.get('max_benefit') else None,
                "document_count": 0,
                "line_item_count": len(new_approved) + len(new_ineligible),
                "approved_line_items": new_approved,
                "ineligible_line_items": new_ineligible,
                "flags": json.loads(updated_result[10]) if isinstance(updated_result[10], str) else (updated_result[10] if updated_result[10] else {}),
                "missing_data": json.loads(updated_result[11]) if isinstance(updated_result[11], str) else (updated_result[11] if updated_result[11] else {}),
                "reasoning": json.loads(updated_result[12]) if isinstance(updated_result[12], str) else (updated_result[12] if updated_result[12] else {}),
                "confidence_score": float(updated_result[13]) if updated_result[13] else 0.0,
                "engine_version": updated_result[14],
                "processing_time_ms": updated_result[15],
                "decided_at": updated_result[16],
            }
            
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
        from shared.config import Config
        from shared.google_drive import GoogleDriveService
        from document_service.processor import DocumentProcessor
        from decision_service.engine.decision_engine import DecisionEngine
        from decision_service.repositories.claim_repository import ClaimRepository
        from decision_service.repositories.document_repository import DocumentRepository
        from pathlib import Path
        import tempfile
        import hashlib
        from sqlalchemy import create_engine, text
        
        # Get claim from database (must exist)
        claim_repo = ClaimRepository()
        claim = await claim_repo.get_claim_by_tracking_number(request.tracking_number)
        
        if not claim:
            raise HTTPException(
                status_code=404,
                detail=f"Claim with tracking number {request.tracking_number} not found in database. Please create the claim first."
            )
        
        logger.info(f"Using existing claim {request.tracking_number} (ID: {claim['id']})")
        
        # Initialize Google Drive service
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
        
        # Extract folder ID from URL if needed
        folder_id = drive_service.extract_folder_id_from_url(request.drive_folder_id)
        
        # Check if we need to find a subfolder by tracking number
        # First, try to list files directly in the provided folder
        logger.info(f"Checking Google Drive folder {folder_id}")
        drive_files = drive_service.list_folder_files(
            folder_id=folder_id,
            file_types=['application/pdf', 'image/png', 'image/jpeg', 'image/jpg', 'image/tiff'],
            recursive=False
        )
        
        # If no files found, look for a subfolder with the tracking number name
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
        
        # Process documents in parallel for better performance
        doc_processor = DocumentProcessor()
        engine = create_engine(Config.DATABASE_URL)
        
        async def process_single_document(drive_file):
            """Process a single document from Google Drive."""
            try:
                logger.info(f"Downloading: {drive_file.name}")
                
                # Download file (this is I/O bound, run in thread pool)
                loop = asyncio.get_event_loop()
                file_stream, filename, mime_type = await loop.run_in_executor(
                    None,  # Use default executor
                    drive_service.download_file_to_stream,
                    drive_file.id
                )
                
                # Read file content once
                file_content = file_stream.read()
                
                # Calculate file hash
                file_hash = hashlib.sha256(file_content).hexdigest()
                
                # Write to temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
                    tmp_file.write(file_content)
                    tmp_path = Path(tmp_file.name)
                
                logger.info(f"Processing: {filename}")
                
                # Process document (OCR, classification) - this can use Gemini
                # The process_document is already async, so we can await it directly
                result = await doc_processor.process_document(
                    file_path=tmp_path,
                    claim_id=claim['id'],
                    processing_priority=0,
                    force_high_quality=False
                )
                
                # Clean up temp file
                tmp_path.unlink()
                
                if result.errors:
                    error_messages = [e.message for e in result.errors]
                    logger.error(f"Error processing {filename}: {', '.join(error_messages)}")
                    return None
                
                # Save document to database
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
        
        # Process all documents in parallel (limit concurrency to avoid overwhelming API)
        logger.info(f"Processing {len(drive_files)} documents in parallel (max 3 concurrent)...")
        semaphore = asyncio.Semaphore(3)  # Process 3 documents concurrently to balance speed vs API limits
        
        async def process_with_semaphore(drive_file):
            async with semaphore:
                return await process_single_document(drive_file)
        
        # Process all documents concurrently (up to 3 at a time)
        results = await asyncio.gather(*[process_with_semaphore(f) for f in drive_files], return_exceptions=True)
        processed_count = sum(1 for r in results if r is True)
        
        # Log any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Exception processing {drive_files[i].name}: {result}", exc_info=result)
        
        if processed_count == 0:
            raise HTTPException(
                status_code=500,
                detail="Failed to process any documents from Google Drive"
            )
        
        logger.info(f"Processed {processed_count}/{len(drive_files)} documents")
        
        # Run decision engine
        logger.info("Running decision engine...")
        decision_engine = DecisionEngine()
        decision = await decision_engine.evaluate_claim(
            claim_id=claim['id'],
            override_max_benefit=request.override_max_benefit
        )
        
        # Save decision
        decision_record = await claim_repo.create_decision(decision, user_id="system")
        
        logger.info(f"✓ Decision created: {decision.proposed_status} ${decision.proposed_benefit_amount}")
        
        return DecisionResponse.from_decision_record(decision_record)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing claim from Google Drive: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

