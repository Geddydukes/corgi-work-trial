# Performance Requirements Analysis

**Date**: December 28, 2025  
**Requirements Source**: `docs/CODE_REVIEW_OVERVIEW.md` (lines 362-367)

## Requirements Summary

1. **Latency**: Target < 3 seconds per claim, hard timeout 10 seconds
2. **Throughput**: 5,000 claims per hour on typical instance
3. **Determinism**: Identical input and engine version must produce identical output
4. **Retry**: Two retries on OCR/parsing errors
5. **Database Queries**: < 10ms for existing decisions (with connection pooling)

---

## 1. Latency: Target < 3 seconds per claim, hard timeout 10 seconds

### Status: ⚠️ **PARTIALLY MET**

#### Current Implementation:

**SLA Configuration** (`shared/config.py`):
- `SLA_TARGET_AVG_MS`: 5000ms (5 seconds) - **EXCEEDS 3 second target**
- `SLA_TARGET_P95_MS`: 15000ms (15 seconds) - **EXCEEDS 3 second target**
- `SLA_TARGET_P99_MS`: 30000ms (30 seconds) - **EXCEEDS 3 second target**
- `SLA_TARGET_MAX_MS`: 60000ms (60 seconds) - **EXCEEDS 10 second hard timeout**

**Processing Timeout** (`shared/config.py`):
- `PROCESSING_TIMEOUT_SEC`: 60 seconds - **EXCEEDS 10 second hard timeout**

**Celery Task Timeouts** (`tasks/celery_app.py`):
- `task_time_limit`: 300 seconds (5 minutes) - **EXCEEDS 10 second hard timeout**
- `task_soft_time_limit`: 240 seconds (4 minutes) - **EXCEEDS 10 second hard timeout**

**OCR Tier Timeouts** (`shared/config.py`):
- `OCR_TIER1_TIMEOUT_MS`: 100ms ✅
- `OCR_TIER2_TIMEOUT_MS`: 3000ms (3 seconds) ⚠️
- `OCR_TIER3_TIMEOUT_MS`: 5000ms (5 seconds) ⚠️

#### Issues Found:

1. **No 10-second hard timeout enforcement**: The system allows processing up to 60 seconds, which is 6x the required hard timeout
2. **SLA targets are too lenient**: Current targets (5s avg, 15s p95, 30s p99, 60s max) don't align with the 3-second target requirement
3. **No timeout enforcement in decision engine**: The `DecisionEngine.evaluate_claim()` method doesn't have a timeout wrapper

#### Recommendations:

1. **Add timeout enforcement**:
   ```python
   # In decision_service/engine/decision_engine.py
   import asyncio
   
   async def evaluate_claim(self, claim_id: int, ...):
       try:
           return await asyncio.wait_for(
               self._evaluate_claim_internal(claim_id, ...),
               timeout=10.0  # 10 second hard timeout
           )
       except asyncio.TimeoutError:
           raise TimeoutError("Claim evaluation exceeded 10 second timeout")
   ```

2. **Update SLA targets** to match requirements:
   - `SLA_TARGET_AVG_MS`: 3000ms (3 seconds)
   - `SLA_TARGET_MAX_MS`: 10000ms (10 seconds hard timeout)

3. **Add timeout to API routes**:
   ```python
   # In decision_service/routes/claims.py
   from fastapi import Request
   from fastapi.responses import JSONResponse
   
   @app.post("/claims/{tracking_number}/decision")
   async def create_decision(...):
       try:
           return await asyncio.wait_for(
               decision_engine.evaluate_claim(...),
               timeout=10.0
           )
       except asyncio.TimeoutError:
           return JSONResponse(
               status_code=504,
               content={"detail": "Request timeout after 10 seconds"}
           )
   ```

---

## 2. Throughput: 5,000 claims per hour on typical instance

### Status: ❌ **NOT VERIFIED**

#### Current Configuration:

**Queue Configuration** (`shared/config.py`):
- `MAX_CONCURRENT_WORKERS`: 10 (default)
- `MAX_QUEUE_DEPTH`: 1000 (default)
- `RATE_LIMIT_PER_CLAIM`: 10 requests per minute
- `RATE_LIMIT_PER_USER`: 100 requests per minute

**Celery Workers** (`docker-compose.yml`):
- `--concurrency=4` per worker
- Single worker instance configured

#### Throughput Calculation:

**Required**: 5,000 claims/hour = ~83.3 claims/minute = ~1.39 claims/second

**Current Capacity** (theoretical):
- 10 concurrent workers × 1 claim per 3 seconds = ~3.33 claims/second = ~200 claims/minute = ~12,000 claims/hour ✅

**However**, this assumes:
- All workers are available
- No queue delays
- No external API (Gemini) rate limits
- No database bottlenecks

#### Issues Found:

1. **No throughput testing**: No performance benchmarks or load tests found
2. **Gemini API rate limits**: External API calls may bottleneck throughput
3. **No monitoring**: No metrics tracking actual throughput vs. target
4. **Queue depth limits**: 1000 max queue depth could be a bottleneck under load

#### Recommendations:

1. **Add throughput monitoring**:
   ```python
   # Track claims processed per hour
   class ThroughputTracker:
       def record_claim_processed(self):
           # Track in Redis or database
           pass
       
       def get_claims_per_hour(self) -> float:
           # Calculate from recent history
           pass
   ```

2. **Load testing**: Create performance test suite to verify 5,000 claims/hour
3. **Scale workers**: Ensure Celery workers can scale horizontally
4. **Monitor bottlenecks**: Track Gemini API latency, database query times, queue depth

---

## 3. Determinism: Identical input and engine version must produce identical output

### Status: ✅ **MOSTLY MET** (with caveats)

#### Current Implementation:

**Engine Versioning** (`decision_service/engine/decision_engine.py`):
- `engine_version` is stored with each decision
- Version comes from `RuleEvaluator.version` (rules version)

**Deterministic Rules** (`decision_service/engine/deterministic_rules.py`):
- ✅ Phrase-based category detection (deterministic)
- ✅ Coverage decisions based on deterministic rules
- ✅ No random number generation
- ✅ No time-based logic that would vary

**LLM Usage** (`decision_service/engine/document_analyzer.py`):
- ⚠️ **NON-DETERMINISTIC**: Gemini API calls are probabilistic
- However, LLM output is now **advisory only** - final decisions use deterministic rules

**Scikit-learn Model** (`document_service/classifier.py`):
- ✅ `random_state=42` set in LogisticRegression (deterministic)
- ✅ Model is trained on initialization (consistent)

#### Potential Non-Determinism Sources:

1. **LLM Temperature**: If Gemini API uses temperature > 0, responses will vary
   - **Status**: Not explicitly controlled in code
   - **Impact**: Low - LLM output is advisory only

2. **Dictionary/Set Iteration Order**: Python 3.7+ preserves insertion order, but should verify
   - **Status**: Should be deterministic in Python 3.7+

3. **Floating Point Precision**: Decimal operations should be deterministic
   - **Status**: Uses `Decimal` type ✅

4. **Database Query Order**: If queries don't specify ORDER BY, results may vary
   - **Status**: Need to verify all queries have deterministic ordering

#### Recommendations:

1. **Add determinism tests**:
   ```python
   def test_determinism():
       """Test that identical inputs produce identical outputs."""
       engine = DecisionEngine()
       claim_id = 123
       
       # Run twice with same input
       result1 = await engine.evaluate_claim(claim_id)
       result2 = await engine.evaluate_claim(claim_id)
       
       assert result1.proposed_status == result2.proposed_status
       assert result1.proposed_benefit_amount == result2.proposed_benefit_amount
   ```

2. **Verify database query ordering**: Ensure all queries have ORDER BY clauses
3. **Document LLM non-determinism**: Clearly document that LLM output may vary but doesn't affect final decisions
4. **Add engine version to all decisions**: ✅ Already implemented

---

## 4. Retry: Two retries on OCR/parsing errors

### Status: ✅ **MET** (with variations)

#### Current Implementation:

**JSON Validation Retries** (`decision_service/engine/json_validator.py`):
- ✅ `max_retries=2` parameter (line 225)
- ✅ Retries JSON parsing on failure (lines 256-273)
- ✅ Returns default-include analyses on final failure

**LLM Call Retries** (`decision_service/engine/document_analyzer.py`):
- ✅ `max_llm_retries` variable (line 334)
- ✅ Retries LLM call if JSON validation fails (lines 334-365)
- ✅ Uses default fallback after retries exhausted

**Celery Task Retries** (`tasks/celery_app.py`):
- ✅ `max_retries=3` for `process_document_task` (line 28)
- ✅ `max_retries=3` for `evaluate_claim_task` (line 77)
- ⚠️ **Note**: 3 retries (not 2), but this is for task-level failures

**OCR Tier Escalation** (`document_service/processor.py`):
- ✅ Automatic escalation from Tier 1 → Tier 2 → Tier 3
- ✅ This is a form of retry with different methods

#### Issues Found:

1. **Inconsistent retry counts**: 
   - JSON validation: 2 retries ✅
   - LLM calls: Variable (depends on `max_llm_retries`)
   - Celery tasks: 3 retries (exceeds requirement, but acceptable)

2. **No explicit OCR retry**: OCR failures escalate to next tier, but don't retry same tier
   - **Status**: This is acceptable as tier escalation is a form of retry

#### Recommendations:

1. **Document retry strategy**: Clearly document that:
   - JSON parsing: 2 retries ✅
   - OCR: Tier escalation (Tier 1 → Tier 2 → Tier 3) ✅
   - Task failures: 3 retries (acceptable, exceeds minimum)

2. **Add retry metrics**: Track retry rates to monitor error rates

---

## 5. Database Queries: < 10ms for existing decisions (with connection pooling)

### Status: ⚠️ **NOT VERIFIED**

#### Current Implementation:

**Connection Pooling** (`shared/database.py`):
- ✅ Shared engine with connection pooling
- ✅ `pool_size=5, max_overflow=10`
- ✅ `pool_pre_ping=True`
- ✅ `pool_recycle=3600` (1 hour)

**BaseRepository Pattern** (`decision_service/repositories/base_repository.py`):
- ✅ All repositories use shared connection pool
- ✅ Consistent connection management

**Query Optimization** (`decision_service/repositories/claim_repository.py`):
- ✅ `get_latest_decision_by_tracking_number()` uses indexed query
- ✅ SELECT only required columns
- ✅ Uses JOIN for related data

#### Issues Found:

1. **No query performance monitoring**: No timing/logging of query execution times
2. **No performance tests**: No tests verifying < 10ms query time
3. **Index verification needed**: Need to verify database indexes exist for:
   - `decisions.claim_id`
   - `decisions.is_active`
   - `claims.claim_tracking_number`

#### Recommendations:

1. **Add query timing**:
   ```python
   import time
   
   def get_latest_decision_by_tracking_number(self, tracking_number: str):
       start = time.time()
       result = conn.execute(...)
       elapsed_ms = (time.time() - start) * 1000
       
       if elapsed_ms > 10:
           logger.warning(f"Slow query: {elapsed_ms:.2f}ms > 10ms")
       
       return result
   ```

2. **Verify database indexes**:
   ```sql
   -- Check indexes exist
   SELECT indexname, indexdef 
   FROM pg_indexes 
   WHERE tablename IN ('decisions', 'claims');
   ```

3. **Add performance tests**:
   ```python
   def test_decision_query_performance():
       """Test that decision queries complete in < 10ms."""
       repo = ClaimRepository()
       start = time.time()
       result = await repo.get_latest_decision_by_tracking_number("CLM-2024-000001")
       elapsed_ms = (time.time() - start) * 1000
       assert elapsed_ms < 10, f"Query took {elapsed_ms}ms, expected < 10ms"
   ```

4. **Monitor slow queries**: Add logging for queries exceeding 10ms

---

## Summary

| Requirement | Status | Notes |
|------------|--------|-------|
| **Latency < 3s, timeout 10s** | ⚠️ Partially Met | Timeouts configured but too lenient (60s vs 10s) |
| **Throughput 5,000/hour** | ❌ Not Verified | Theoretical capacity exists, but no testing |
| **Determinism** | ✅ Mostly Met | Deterministic rules implemented, LLM is advisory |
| **Retry (2x)** | ✅ Met | JSON validation has 2 retries, OCR has tier escalation |
| **DB Queries < 10ms** | ⚠️ Not Verified | Connection pooling exists, but no performance monitoring |

## Priority Actions

### 🔴 Critical
1. **Add 10-second hard timeout** to `DecisionEngine.evaluate_claim()`
2. **Update SLA targets** to match 3-second requirement
3. **Add query performance monitoring** to verify < 10ms

### 🟠 High Priority
4. **Create throughput load tests** to verify 5,000 claims/hour
5. **Add determinism tests** to ensure identical inputs produce identical outputs
6. **Verify database indexes** exist for performance-critical queries

### 🟡 Medium Priority
7. **Document retry strategy** clearly
8. **Add performance metrics dashboard** for monitoring
9. **Create performance regression tests** in CI/CD














