import logging
from typing import Optional, Dict
from datetime import datetime

from decision_service.repositories.base_repository import BaseRepository
from shared.config import Config
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ClaimRepository(BaseRepository):
    async def get_claim(self, claim_id: int) -> Optional[dict]:
        if not self.is_database_configured():
            logger.warning("Database not configured, returning mock data")
            return {
                "id": claim_id,
                "claim_tracking_number": f"CLM-2024-{claim_id:06d}",
                "claim_amount": 5000.0,
                "max_benefit": 5000.0,
                "lease_start_date": "2023-01-01",
            }
        
        try:
            with self.get_connection() as conn:
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
        if not self.is_database_configured():
            logger.warning("Database not configured, returning mock data")
            return {
                "id": 12345,
                "claim_tracking_number": tracking_number,
                "claim_amount": 5000.0,
                "max_benefit": 5000.0,
                "lease_start_date": "2023-01-01",
            }
        
        try:
            with self.get_connection() as conn:
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
        import json
        
        if not self.is_database_configured():
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
            with self.get_connection() as conn:
                
                conn.execute(
                    text("UPDATE decisions SET is_active = false WHERE claim_id = :claim_id AND is_active = true"),
                    {"claim_id": decision.claim_id}
                )
                
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
                        'invoice': max(0.0, float(decision.invoice_total)),
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
        import json
        
        if not self.is_database_configured():
            logger.warning("Database not configured, returning None")
            return None
        
        # Fast fail if engine is None
        if self.engine is None:
            logger.error("Database engine is None - cannot connect")
            raise TimeoutError("Database not available")
        
        try:
            import asyncio
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
            import signal
            
            # Wrap the entire database operation in a timeout to prevent hanging
            def _fetch_decision():
                import time
                query_start = time.time()
                try:
                    # get_connection() already sets statement_timeout and search_path
                    with self.get_connection() as conn:
                        conn_start = time.time()
                        logger.info(f"[DB] Getting connection took {time.time() - conn_start:.3f}s for tracking_number={tracking_number}")
                        
                        # Optimized query: get claim_id first, then decision
                        # This uses the unique index on claim_tracking_number more efficiently
                        claim_query_start = time.time()
                        claim_result = conn.execute(
                            text("""
                                SELECT id, claim_amount, max_benefit
                                FROM claims
                                WHERE claim_tracking_number = :tracking_number
                                LIMIT 1
                            """),
                            {"tracking_number": tracking_number}
                        ).fetchone()
                        logger.info(f"[DB] Claim query took {time.time() - claim_query_start:.3f}s for tracking_number={tracking_number}")
                        
                        if not claim_result:
                            logger.info(f"Claim not found for tracking number: {tracking_number}")
                            return None
                        
                        claim_id = claim_result[0]
                        
                        # Now get the decision using claim_id (uses idx_decisions_claim_id_active)
                        decision_query_start = time.time()
                        result = conn.execute(
                            text("""
                                SELECT 
                                    d.id, d.claim_id, d.approved_line_items, d.ineligible_line_items,
                                    d.decision_type, d.proposed_status, d.proposed_benefit_amount,
                                    d.eligible_total, d.invoice_total, d.cap_amount, d.flags, d.missing_data,
                                    d.reasoning, d.confidence_score, d.engine_version, d.processing_time_ms,
                                    d.decided_at
                                FROM decisions d
                                WHERE d.claim_id = :claim_id
                                    AND d.is_active = TRUE
                                ORDER BY d.decided_at DESC
                                LIMIT 1
                            """),
                            {"claim_id": claim_id}
                        ).fetchone()
                        logger.info(f"[DB] Decision query took {time.time() - decision_query_start:.3f}s for claim_id={claim_id}")
                        
                        if not result:
                            logger.info(f"No active decision found for claim_id: {claim_id}")
                            return None
                        
                        # Skip document count query - it's not critical and can be slow
                        # We'll set it to 0 or make it optional
                        document_count = 0
                        # Removed document count query to speed up - can be added back if needed
                        
                        import json
                        
                        # Parse JSON fields efficiently
                        approved_items = result[2] if result[2] else []
                        ineligible_items = result[3] if result[3] else []
                        
                        # Handle JSON strings
                        if isinstance(approved_items, str):
                            try:
                                approved_items = json.loads(approved_items)
                            except json.JSONDecodeError:
                                approved_items = []
                        if isinstance(ineligible_items, str):
                            try:
                                ineligible_items = json.loads(ineligible_items)
                            except json.JSONDecodeError:
                                ineligible_items = []
                        
                        line_item_count = len(approved_items) + len(ineligible_items)
                        
                        # Parse other JSON fields
                        flags = result[10] if result[10] else {}
                        if isinstance(flags, str):
                            try:
                                flags = json.loads(flags)
                            except json.JSONDecodeError:
                                flags = {}
                        
                        missing_data = result[11] if result[11] else {}
                        if isinstance(missing_data, str):
                            try:
                                missing_data = json.loads(missing_data)
                            except json.JSONDecodeError:
                                missing_data = {}
                        
                        reasoning = result[12] if result[12] else {}
                        if isinstance(reasoning, str):
                            try:
                                reasoning = json.loads(reasoning)
                            except json.JSONDecodeError:
                                reasoning = {}
                        
                        parse_start = time.time()
                        return {
                            "id": result[0],
                            "claim_id": result[1],
                            "tracking_number": tracking_number,
                            "decision_type": result[4],
                            "proposed_status": result[5],
                            "proposed_benefit_amount": float(result[6]),
                            "eligible_total": float(result[7]),
                            "invoice_total": float(result[8]),
                            "cap_amount": float(result[9]) if result[9] else None,
                            "claim_amount": float(claim_result[1]) if claim_result[1] else 0.0,
                            "max_benefit": float(claim_result[2]) if claim_result[2] else None,
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
                    logger.error(f"Error in _fetch_decision: {e}", exc_info=True)
                    raise
                finally:
                    total_time = time.time() - query_start
                    logger.info(f"[DB] Total query time: {total_time:.3f}s for tracking_number={tracking_number}")
            
            # Run the database operation with a 10 second timeout (increased from 5)
            loop = asyncio.get_event_loop()
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(executor, _fetch_decision),
                    timeout=10.0  # Increased to 10 seconds to handle slow queries
                )
                return result
            except asyncio.TimeoutError:
                logger.error(f"Database query timed out after 10 seconds for tracking number: {tracking_number}")
                # Force shutdown the executor
                executor.shutdown(wait=False, cancel_futures=True)
                raise TimeoutError("Database query timed out")
            except Exception as e:
                logger.error(f"Database error: {e}", exc_info=True)
                executor.shutdown(wait=False)
                raise
            finally:
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except:
                    pass
        except TimeoutError:
            raise
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
        if not self.is_database_configured():
            raise ValueError("Database not configured")
        
        try:
            with self.get_connection() as conn:
                
                existing = conn.execute(
                    text("SELECT id FROM claims WHERE claim_tracking_number = :tracking_number"),
                    {"tracking_number": tracking_number}
                ).fetchone()
                
                if existing:
                    return await self.get_claim(existing[0])
                
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
    
    async def get_variance_data(self, claim_id: int) -> Optional[Dict]:
        """Get variance data comparing proposed decision to actual decision."""
        if not self.is_database_configured():
            return None
        
        try:
            with self.get_connection() as conn:
                result = conn.execute(
                    text("""
                        SELECT 
                            dv.actual_status,
                            dv.actual_paid_amount,
                            dv.actual_decision_date,
                            dv.adjudication_notes
                        FROM decision_validation dv
                        WHERE dv.claim_id = :claim_id
                        ORDER BY dv.actual_decision_date DESC
                        LIMIT 1
                    """),
                    {"claim_id": claim_id}
                ).fetchone()
                
                if not result:
                    return None
                
                return {
                    "actual_status": result[0],
                    "actual_paid_amount": float(result[1]) if result[1] else 0.0,
                    "actual_decision_date": result[2].isoformat() if result[2] else None,
                    "adjudication_notes": result[3],
                }
        except Exception as e:
            logger.error(f"Error fetching variance data for claim {claim_id}: {e}")
            return None
                
        except Exception as e:
            logger.error(f"Error creating/getting claim {tracking_number}: {e}", exc_info=True)
            raise

