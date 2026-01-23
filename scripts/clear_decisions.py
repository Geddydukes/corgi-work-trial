#!/usr/bin/env python3.11
"""
Clear decisions for claims 900-904.
"""

from sqlalchemy import create_engine, text

engine = create_engine('postgresql://postgres:postgres@localhost:5432/app_dev')
with engine.connect() as conn:
    conn.execute(text('SET search_path TO claims, public'))
    # Delete existing decisions for claims 900-904
    claim_ids = conn.execute(
        text('SELECT id FROM claims WHERE claim_tracking_number::int BETWEEN 900 AND 904')
    ).fetchall()
    
    for (claim_id,) in claim_ids:
        conn.execute(
            text('DELETE FROM decisions WHERE claim_id = :claim_id'),
            {'claim_id': claim_id}
        )
    conn.commit()
    print(f'Deleted existing decisions for {len(claim_ids)} claims (900-904)')

