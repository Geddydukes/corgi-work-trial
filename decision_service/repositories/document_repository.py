import logging
from typing import List, Dict, Optional

from decision_service.repositories.base_repository import BaseRepository
from shared.config import Config
from sqlalchemy import text

logger = logging.getLogger(__name__)


class DocumentRepository(BaseRepository):
    async def get_documents(self, claim_id: int) -> List[dict]:
        if not self.is_database_configured():
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
        
        try:
            with self.get_connection() as conn:
                result = conn.execute(
                    text("""
                        SELECT 
                            id, claim_id, document_type, extracted_text,
                            ocr_confidence, classification_confidence,
                            file_path, original_filename, file_hash,
                            file_size_bytes, mime_type, page_count,
                            processing_status, created_at
                        FROM claim_documents
                        WHERE claim_id = :claim_id
                        ORDER BY created_at
                    """),
                    {"claim_id": claim_id}
                ).fetchall()
                
                documents = []
                for row in result:
                    documents.append({
                        "id": row[0],
                        "claim_id": row[1],
                        "document_type": row[2],
                        "extracted_text": row[3] or "",
                        "ocr_confidence": float(row[4]) if row[4] else None,
                        "classification_confidence": float(row[5]) if row[5] else None,
                        "file_path": row[6],
                        "original_filename": row[7],
                        "file_hash": row[8],
                        "file_size_bytes": row[9],
                        "mime_type": row[10],
                        "page_count": row[11],
                        "processing_status": row[12],
                        "created_at": row[13].isoformat() if row[13] else None,
                    })
                
                return documents
        except Exception as e:
            logger.error(f"Error fetching documents for claim {claim_id}: {e}")
            return []
    
    async def get_documents_by_tracking_number(
        self,
        tracking_number: str,
        document_type: Optional[str] = None
    ) -> List[dict]:
        if not self.is_database_configured():
            logger.warning("Database not configured, returning mock data")
            mock_docs = [
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
            if document_type:
                mock_docs = [doc for doc in mock_docs if doc["document_type"] == document_type]
            return mock_docs
        
        try:
            with self.get_connection() as conn:
                
                query = """
                    SELECT 
                        cd.id, cd.claim_id, cd.document_type, cd.extracted_text,
                        cd.ocr_confidence, cd.classification_confidence,
                        cd.file_path, cd.original_filename, cd.file_hash,
                        cd.file_size_bytes, cd.mime_type, cd.page_count,
                        cd.processing_status, cd.created_at
                    FROM claim_documents cd
                    INNER JOIN claims c ON cd.claim_id = c.id
                    WHERE c.claim_tracking_number = :tracking_number
                """
                
                params = {"tracking_number": tracking_number}
                
                if document_type:
                    query += " AND cd.document_type = :document_type"
                    params["document_type"] = document_type
                
                query += " ORDER BY cd.created_at"
                
                result = conn.execute(text(query), params).fetchall()
                
                documents = []
                for row in result:
                    documents.append({
                        "document_id": row[0],
                        "claim_id": row[1],
                        "document_type": row[2],
                        "extracted_text": row[3] or "",
                        "ocr_confidence": float(row[4]) if row[4] else None,
                        "classification_confidence": float(row[5]) if row[5] else None,
                        "file_path": row[6],
                        "original_filename": row[7],
                        "file_hash": row[8],
                        "file_size_bytes": row[9],
                        "mime_type": row[10],
                        "page_count": row[11],
                        "processing_status": row[12],
                        "created_at": row[13].isoformat() if row[13] else None,
                    })
                
                return documents
        except Exception as e:
            logger.error(f"Error fetching documents for tracking number {tracking_number}: {e}")
            return []

