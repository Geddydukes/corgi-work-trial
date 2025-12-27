from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import tempfile
import os

from document_service.processor import DocumentProcessor

router = APIRouter()


@router.post("/documents/process")
async def process_document(
    file: UploadFile = File(...),
    claim_id: int = None,
    processing_priority: int = 0,
    force_high_quality: bool = False,
):
    """
    Process a document through OCR and classification.
    """
    if not claim_id:
        raise HTTPException(status_code=400, detail="claim_id is required")
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)
        
        processor = DocumentProcessor()
        result = await processor.process_document(
            file_path=tmp_path,
            claim_id=claim_id,
            processing_priority=processing_priority,
            force_high_quality=force_high_quality,
        )
        
        os.unlink(tmp_path)
        
        return result.to_dict()
        
    except Exception as e:
        if tmp_path.exists():
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

