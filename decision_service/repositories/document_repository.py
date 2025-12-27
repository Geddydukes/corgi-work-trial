import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class DocumentRepository:
    async def get_documents(self, claim_id: int) -> List[dict]:
        from shared.config import Config
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock data")
            return [
                {
                    "id": 1,
                    "claim_id": claim_id,
                    "document_type": "invoice",
                    "extracted_text": "INVOICE\nItem 1: $500.00\nItem 2: $300.00\nTotal: $800.00",
                    "file_path": f"claims/{claim_id}/invoice.pdf",
                }
            ]
        
        return []
    
    async def get_documents_by_tracking_number(self, tracking_number: str) -> List[dict]:
        from shared.config import Config
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock data")
            return [
                {
                    "document_id": 1,
                    "claim_id": 12345,
                    "file_path": f"claims/12345/invoice.pdf",
                    "original_filename": "invoice.pdf",
                    "file_hash": "abc123",
                    "file_size_bytes": 245760,
                    "mime_type": "application/pdf",
                    "document_type": "invoice",
                    "classification_confidence": 95.5,
                    "page_count": 3,
                    "processing_status": "completed",
                    "created_at": "2024-01-15T09:00:00Z",
                }
            ]
        
        return []

