import logging
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

# Cache database engine for connection pooling
_engine_cache = None

def _get_engine():
    """Get or create a cached database engine with connection pooling."""
    global _engine_cache
    from shared.config import Config
    
    if _engine_cache is None and Config.DATABASE_URL:
        from sqlalchemy import create_engine
        _engine_cache = create_engine(
            Config.DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600
        )
    return _engine_cache


class ClaimRepository:
    async def get_claim(self, claim_id: int) -> Optional[dict]:
        from shared.config import Config
        from sqlalchemy import text
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock data")
            return {
                "id": claim_id,
                "claim_tracking_number": f"CLM-2024-{claim_id:06d}",
                "claim_amount": 5000.0,
                "max_benefit": 5000.0,
                "lease_start_date": "2023-01-01",
            }
        
        try:
            engine = _get_engine()
            if not engine:
                logger.warning("Database not configured, returning mock data")
                return {
                    "id": claim_id,
                    "claim_tracking_number": f"CLM-2024-{claim_id:06d}",
                    "claim_amount": 5000.0,
                    "max_benefit": 5000.0,
                    "lease_start_date": "2023-01-01",
                }
            
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                result = conn.execute(
                    text("""
                        SELECT 
                            id, claim_tracking_number, claim_amount, max_benefit,
                            security_deposit_amount, policyholder_id, property_id,
                            claim_date, move_out_date, lease_start_date, lease_end_date,
                            status, priority, retry_count, last_processed_at,
                            created_at, updated_at, created_by, updated_by
                        FROM claims
                        WHERE id = :claim_id
                    """),
                    {"claim_id": claim_id}
                ).fetchone()
                
                if not result:
                    return None
                
                return {
                    "id": result[0],
                    "claim_tracking_number": result[1],
                    "claim_amount": float(result[2]) if result[2] else 0.0,
                    "max_benefit": float(result[3]) if result[3] else None,
                    "security_deposit_amount": float(result[4]) if result[4] else None,
                    "policyholder_id": result[5],
                    "property_id": result[6],
                    "claim_date": result[7].isoformat() if result[7] else None,
                    "move_out_date": result[8].isoformat() if result[8] else None,
                    "lease_start_date": result[9].isoformat() if result[9] else None,
                    "lease_end_date": result[10].isoformat() if result[10] else None,
                    "status": result[11],
                    "priority": result[12],
                    "retry_count": result[13],
                    "last_processed_at": result[14].isoformat() if result[14] else None,
                    "created_at": result[15].isoformat() if result[15] else None,
                    "updated_at": result[16].isoformat() if result[16] else None,
                    "created_by": result[17],
                    "updated_by": result[18],
                }
        except Exception as e:
            logger.error(f"Error fetching claim {claim_id}: {e}")
            return None
    
    async def get_claim_by_tracking_number(self, tracking_number: str) -> Optional[dict]:
        from shared.config import Config
        from sqlalchemy import text
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock data")
            return {
                "id": 12345,
                "claim_tracking_number": tracking_number,
                "claim_amount": 5000.0,
                "max_benefit": 5000.0,
                "lease_start_date": "2023-01-01",
            }
        
        try:
            engine = _get_engine()
            if not engine:
                logger.warning("Database not configured, returning mock data")
                return {
                    "id": claim_id,
                    "claim_tracking_number": f"CLM-2024-{claim_id:06d}",
                    "claim_amount": 5000.0,
                    "max_benefit": 5000.0,
                    "lease_start_date": "2023-01-01",
                }
            
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                result = conn.execute(
                    text("""
                        SELECT 
                            id, claim_tracking_number, claim_amount, max_benefit,
                            security_deposit_amount, policyholder_id, property_id,
                            claim_date, move_out_date, lease_start_date, lease_end_date,
                            status, priority, retry_count, last_processed_at,
                            created_at, updated_at, created_by, updated_by
                        FROM claims
                        WHERE claim_tracking_number = :tracking_number
                    """),
                    {"tracking_number": tracking_number}
                ).fetchone()
                
                if not result:
                    return None
                
                return {
                    "id": result[0],
                    "claim_tracking_number": result[1],
                    "claim_amount": float(result[2]) if result[2] else 0.0,
                    "max_benefit": float(result[3]) if result[3] else None,
                    "security_deposit_amount": float(result[4]) if result[4] else None,
                    "policyholder_id": result[5],
                    "property_id": result[6],
                    "claim_date": result[7].isoformat() if result[7] else None,
                    "move_out_date": result[8].isoformat() if result[8] else None,
                    "lease_start_date": result[9].isoformat() if result[9] else None,
                    "lease_end_date": result[10].isoformat() if result[10] else None,
                    "status": result[11],
                    "priority": result[12],
                    "retry_count": result[13],
                    "last_processed_at": result[14].isoformat() if result[14] else None,
                    "created_at": result[15].isoformat() if result[15] else None,
                    "updated_at": result[16].isoformat() if result[16] else None,
                    "created_by": result[17],
                    "updated_by": result[18],
                }
        except Exception as e:
            logger.error(f"Error fetching claim by tracking number {tracking_number}: {e}")
            return None
    
    async def create_decision(self, decision, user_id: str) -> dict:
        from shared.config import Config
        from sqlalchemy import text
        import json
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning mock decision")
            return {
                "id": 1,
                "claim_id": decision.claim_id,
                "tracking_number": f"CLM-2024-{decision.claim_id:06d}",
                "decision_type": "automated",
                "proposed_status": decision.proposed_status,
                "proposed_benefit_amount": float(decision.proposed_benefit_amount),
                "eligible_total": float(decision.eligible_total),
                "invoice_total": float(decision.invoice_total),
                "cap_amount": float(decision.cap_amount) if decision.cap_amount else None,
                "claim_amount": float(decision.claim_amount),
                "max_benefit": float(decision.max_benefit) if decision.max_benefit else None,
                "document_count": decision.document_count,
                "line_item_count": decision.line_item_count,
                "approved_line_items": decision.approved_line_items,
                "ineligible_line_items": decision.ineligible_line_items,
                "flags": decision.flags,
                "missing_data": decision.missing_data,
                "reasoning": decision.reasoning,
                "confidence_score": decision.confidence_score,
                "engine_version": decision.engine_version,
                "decided_at": datetime.utcnow(),
            }
        
        try:
            engine = _get_engine()
            if not engine:
                logger.warning("Database not configured, returning mock data")
                return {
                    "id": claim_id,
                    "claim_tracking_number": f"CLM-2024-{claim_id:06d}",
                    "claim_amount": 5000.0,
                    "max_benefit": 5000.0,
                    "lease_start_date": "2023-01-01",
                }
            
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                # Deactivate old decisions for this claim
                conn.execute(
                    text("UPDATE decisions SET is_active = false WHERE claim_id = :claim_id AND is_active = true"),
                    {"claim_id": decision.claim_id}
                )
                
                # Insert new decision
                result = conn.execute(
                    text("""
                        INSERT INTO decisions (
                            claim_id, decision_type, proposed_status, proposed_benefit_amount,
                            eligible_total, invoice_total, cap_amount,
                            approved_line_items, ineligible_line_items, flags, missing_data, reasoning,
                            confidence_score, engine_version, processing_time_ms, decided_by, is_active
                        ) VALUES (
                            :claim_id, 'initial', CAST(:status AS decision_status_enum), :benefit,
                            :eligible, :invoice, :cap,
                            CAST(:approved AS jsonb), CAST(:ineligible AS jsonb),
                            CAST(:flags AS jsonb), CAST(:missing AS jsonb),
                            CAST(:reasoning AS jsonb),
                            :confidence, :version, 0, :user_id, true
                        ) RETURNING id
                    """),
                    {
                        'claim_id': decision.claim_id,
                        'status': decision.proposed_status,
                        'benefit': float(decision.proposed_benefit_amount),
                        'eligible': float(decision.eligible_total),
                        'invoice': max(0.0, float(decision.invoice_total)),  # Ensure non-negative for database constraint
                        'cap': float(decision.cap_amount) if decision.cap_amount else None,
                        'approved': json.dumps(decision.approved_line_items, default=str),
                        'ineligible': json.dumps(decision.ineligible_line_items, default=str),
                        'flags': json.dumps(decision.flags, default=str),
                        'missing': json.dumps(decision.missing_data, default=str),
                        'reasoning': json.dumps(decision.reasoning, default=str),
                        'confidence': decision.confidence_score,
                        'version': decision.engine_version,
                        'user_id': user_id
                    }
                )
                
                decision_id = result.scalar()
                conn.commit()
                
                # Get tracking number
                tracking_result = conn.execute(
                    text("SELECT claim_tracking_number FROM claims WHERE id = :claim_id"),
                    {"claim_id": decision.claim_id}
                ).fetchone()
                tracking_number = tracking_result[0] if tracking_result else None
                
                return {
                    "id": decision_id,
                    "claim_id": decision.claim_id,
                    "tracking_number": tracking_number,
                    "decision_type": "initial",
                    "proposed_status": decision.proposed_status,
                    "proposed_benefit_amount": float(decision.proposed_benefit_amount),
                    "eligible_total": float(decision.eligible_total),
                    "invoice_total": float(decision.invoice_total),
                    "cap_amount": float(decision.cap_amount) if decision.cap_amount else None,
                    "claim_amount": float(decision.claim_amount),
                    "max_benefit": float(decision.max_benefit) if decision.max_benefit else None,
                    "document_count": decision.document_count,
                    "line_item_count": decision.line_item_count,
                    "approved_line_items": decision.approved_line_items,
                    "ineligible_line_items": decision.ineligible_line_items,
                    "flags": decision.flags,
                    "missing_data": decision.missing_data,
                    "reasoning": decision.reasoning,
                    "confidence_score": decision.confidence_score,
                    "engine_version": decision.engine_version,
                    "decided_at": datetime.utcnow(),
                }
        except Exception as e:
            logger.error(f"Error creating decision: {e}", exc_info=True)
            return None
    
    async def get_latest_decision_by_tracking_number(self, tracking_number: str) -> Optional[dict]:
        """Get the latest decision for a claim by tracking number."""
        from shared.config import Config
        from sqlalchemy import text
        import json
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, returning None")
            return None
        
        try:
            # Use cached engine with connection pooling
            engine = _get_engine()
            if not engine:
                logger.warning("Database not configured, returning None")
                return None
            
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                result = conn.execute(
                    text("""
                        SELECT 
                            d.id, d.claim_id, d.approved_line_items, d.ineligible_line_items,
                            d.decision_type, d.proposed_status, d.proposed_benefit_amount,
                            d.eligible_total, d.invoice_total, d.cap_amount, d.flags, d.missing_data,
                            d.reasoning, d.confidence_score, d.engine_version, d.processing_time_ms,
                            d.decided_at, c.claim_tracking_number, c.claim_amount, c.max_benefit
                        FROM decisions d
                        JOIN claims c ON c.id = d.claim_id
                        WHERE c.claim_tracking_number = :tracking_number
                        ORDER BY d.decided_at DESC
                        LIMIT 1
                    """),
                    {"tracking_number": tracking_number}
                ).fetchone()
                
                if not result:
                    return None
                
                # Get document count from claim_documents table (faster, skip if fails)
                document_count = 0
                try:
                    doc_count_result = conn.execute(
                        text("""
                            SELECT COUNT(*) 
                            FROM claim_documents 
                            WHERE claim_id = :claim_id
                        """),
                        {"claim_id": result[1]}
                    ).fetchone()
                    document_count = doc_count_result[0] if doc_count_result else 0
                except Exception:
                    # Table might not exist or query failed, use 0
                    pass
                
                # Parse JSON fields efficiently
                approved_items = result[2] if result[2] else []
                ineligible_items = result[3] if result[3] else []
                
                # Handle JSON strings
                if isinstance(approved_items, str):
                    approved_items = json.loads(approved_items)
                if isinstance(ineligible_items, str):
                    ineligible_items = json.loads(ineligible_items)
                
                line_item_count = len(approved_items) + len(ineligible_items)
                
                # Parse other JSON fields
                flags = result[10] if result[10] else {}
                if isinstance(flags, str):
                    flags = json.loads(flags)
                
                missing_data = result[11] if result[11] else {}
                if isinstance(missing_data, str):
                    missing_data = json.loads(missing_data)
                
                reasoning = result[12] if result[12] else {}
                if isinstance(reasoning, str):
                    reasoning = json.loads(reasoning)
                
                return {
                    "id": result[0],
                    "claim_id": result[1],
                    "tracking_number": result[17],
                    "decision_type": result[4],
                    "proposed_status": result[5],
                    "proposed_benefit_amount": float(result[6]),
                    "eligible_total": float(result[7]),
                    "invoice_total": float(result[8]),
                    "cap_amount": float(result[9]) if result[9] else None,
                    "claim_amount": float(result[18]) if result[18] else 0.0,
                    "max_benefit": float(result[19]) if result[19] else None,
                    "document_count": document_count,
                    "line_item_count": line_item_count,
                    "approved_line_items": approved_items,
                    "ineligible_line_items": ineligible_items,
                    "flags": flags,
                    "missing_data": missing_data,
                    "reasoning": reasoning,
                    "confidence_score": float(result[13]),
                    "engine_version": result[14],
                    "processing_time_ms": result[15],
                    "decided_at": result[16].isoformat() if result[16] else None,
                }
        except Exception as e:
            logger.error(f"Error fetching latest decision for tracking number {tracking_number}: {e}", exc_info=True)
            return None
    
    async def create_or_get_claim(
        self,
        tracking_number: str,
        claim_amount: float,
        max_benefit: Optional[float],
        claim_date: str,
        policyholder_id: Optional[str] = None,
        property_id: Optional[str] = None,
        lease_start_date: Optional[str] = None,
        lease_end_date: Optional[str] = None,
        move_out_date: Optional[str] = None,
        security_deposit_amount: Optional[float] = None,
    ) -> dict:
        """Create a claim if it doesn't exist, or return existing claim."""
        from shared.config import Config
        from sqlalchemy import create_engine, text
        
        if not Config.DATABASE_URL:
            raise ValueError("Database not configured")
        
        try:
            engine = _get_engine()
            if not engine:
                logger.warning("Database not configured, returning mock data")
                return {
                    "id": claim_id,
                    "claim_tracking_number": f"CLM-2024-{claim_id:06d}",
                    "claim_amount": 5000.0,
                    "max_benefit": 5000.0,
                    "lease_start_date": "2023-01-01",
                }
            
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                # Check if claim exists
                existing = conn.execute(
                    text("SELECT id FROM claims WHERE claim_tracking_number = :tracking_number"),
                    {"tracking_number": tracking_number}
                ).fetchone()
                
                if existing:
                    # Return existing claim
                    return await self.get_claim(existing[0])
                
                # Create new claim
                result = conn.execute(
                    text("""
                        INSERT INTO claims (
                            claim_tracking_number, claim_amount, max_benefit,
                            security_deposit_amount, policyholder_id, property_id,
                            claim_date, move_out_date, lease_start_date, lease_end_date,
                            status, created_by
                        ) VALUES (
                            :tracking_number, :claim_amount, :max_benefit,
                            :security_deposit, :policyholder_id, :property_id,
                            CAST(:claim_date AS DATE), 
                            CAST(:move_out_date AS DATE),
                            CAST(:lease_start_date AS DATE),
                            CAST(:lease_end_date AS DATE),
                            'pending', 'system'
                        ) RETURNING id
                    """),
                    {
                        'tracking_number': tracking_number,
                        'claim_amount': float(claim_amount),
                        'max_benefit': float(max_benefit) if max_benefit else None,
                        'security_deposit': float(security_deposit_amount) if security_deposit_amount else None,
                        'policyholder_id': policyholder_id,
                        'property_id': property_id,
                        'claim_date': claim_date,
                        'move_out_date': move_out_date,
                        'lease_start_date': lease_start_date,
                        'lease_end_date': lease_end_date,
                    }
                )
                claim_id = result.scalar()
                conn.commit()
                
                logger.info(f"Created new claim {tracking_number} with ID {claim_id}")
                return await self.get_claim(claim_id)
                
        except Exception as e:
            logger.error(f"Error creating/getting claim {tracking_number}: {e}", exc_info=True)
            raise

