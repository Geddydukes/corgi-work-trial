import logging
from typing import List, Dict, Optional
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class OverrideRepository:
    async def save_line_item_overrides(
        self,
        decision_id: int,
        claim_id: int,
        overrides: List[Dict],
        user_id: str,
        user_role: Optional[str] = None
    ) -> bool:
        """Save line item overrides to the database."""
        from shared.config import Config
        from sqlalchemy import create_engine, text
        
        if not Config.DATABASE_URL:
            logger.warning("Database not configured, skipping override save")
            return True
        
        try:
            engine = create_engine(Config.DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                batch_id = f"batch_{datetime.utcnow().strftime('%Y_%m_%d')}"
                
                for override in overrides:
                    # Check if override already exists
                    existing = conn.execute(
                        text("""
                            SELECT id FROM user_line_item_overrides
                            WHERE decision_id = :decision_id AND line_item_index = :index
                        """),
                        {
                            'decision_id': decision_id,
                            'index': override['line_item_index']
                        }
                    ).fetchone()
                    
                    if existing:
                        # Update existing override
                        conn.execute(
                            text("""
                                UPDATE user_line_item_overrides
                                SET user_should_be_included = :included,
                                    user_reasoning = :reasoning,
                                    override_timestamp = NOW()
                                WHERE id = :id
                            """),
                            {
                                'id': existing[0],
                                'included': override['user_should_be_included'],
                                'reasoning': override.get('user_reasoning')
                            }
                        )
                    else:
                        # Insert new override
                        conn.execute(
                            text("""
                                INSERT INTO user_line_item_overrides (
                                    decision_id, claim_id, line_item_index,
                                    line_item_description, line_item_amount,
                                    system_should_be_included, system_categories,
                                    system_reasoning, system_confidence,
                                    user_should_be_included, user_reasoning,
                                    user_id, user_role, batch_id
                                ) VALUES (
                                    :decision_id, :claim_id, :index,
                                    :description, :amount,
                                    :system_included, CAST(:categories AS jsonb),
                                    :system_reasoning, :system_confidence,
                                    :user_included, :user_reasoning,
                                    :user_id, :user_role, :batch_id
                                )
                            """),
                            {
                                'decision_id': decision_id,
                                'claim_id': claim_id,
                                'index': override['line_item_index'],
                                'description': override.get('line_item_description', ''),
                                'amount': override.get('line_item_amount', 0),
                                'system_included': override.get('system_should_be_included', False),
                                'categories': json.dumps(override.get('system_categories', {})),
                                'system_reasoning': override.get('system_reasoning'),
                                'system_confidence': override.get('system_confidence'),
                                'user_included': override['user_should_be_included'],
                                'user_reasoning': override.get('user_reasoning'),
                                'user_id': user_id,
                                'user_role': user_role,
                                'batch_id': batch_id
                            }
                        )
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error saving line item overrides: {e}", exc_info=True)
            return False
    
    async def get_line_item_overrides(
        self,
        decision_id: int
    ) -> List[Dict]:
        """Get all line item overrides for a decision."""
        from shared.config import Config
        from sqlalchemy import create_engine, text
        
        if not Config.DATABASE_URL:
            return []
        
        try:
            engine = create_engine(Config.DATABASE_URL)
            with engine.connect() as conn:
                conn.execute(text("SET search_path TO claims, public"))
                
                result = conn.execute(
                    text("""
                        SELECT 
                            line_item_index, user_should_be_included, user_reasoning,
                            system_should_be_included, override_timestamp
                        FROM user_line_item_overrides
                        WHERE decision_id = :decision_id
                        ORDER BY line_item_index
                    """),
                    {'decision_id': decision_id}
                ).fetchall()
                
                return [
                    {
                        'line_item_index': row[0],
                        'user_should_be_included': row[1],
                        'user_reasoning': row[2],
                        'system_should_be_included': row[3],
                        'override_timestamp': row[4].isoformat() if row[4] else None
                    }
                    for row in result
                ]
        except Exception as e:
            logger.error(f"Error fetching line item overrides: {e}", exc_info=True)
            return []

