-- ============================================================================
-- Index Analysis Queries
-- Verify index usage, size, and effectiveness
-- ============================================================================

SET search_path TO claims, public;

-- ============================================================================
-- 1. Index Usage Statistics
-- ============================================================================

SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan AS index_scans,
    idx_tup_read AS tuples_read,
    idx_tup_fetch AS tuples_fetched,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'claims'
ORDER BY idx_scan DESC, tablename, indexname;

-- ============================================================================
-- 2. Index Sizes and Bloat Analysis
-- ============================================================================

SELECT
    t.schemaname,
    t.tablename,
    i.indexname,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size,
    pg_size_pretty(pg_relation_size(t.relid)) AS table_size,
    ROUND(100.0 * pg_relation_size(i.indexrelid) / 
          NULLIF(pg_relation_size(t.relid), 0), 2) AS index_to_table_ratio,
    i.idx_scan AS scans,
    i.idx_tup_read AS tuples_read,
    i.idx_tup_fetch AS tuples_fetched
FROM pg_stat_user_indexes i
JOIN pg_stat_user_tables t ON i.relid = t.relid
WHERE t.schemaname = 'claims'
ORDER BY pg_relation_size(i.indexrelid) DESC;

-- ============================================================================
-- 3. Unused Indexes (candidates for removal)
-- ============================================================================

SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan AS total_scans
FROM pg_stat_user_indexes
WHERE schemaname = 'claims'
    AND idx_scan = 0
    AND indexrelid NOT IN (
        SELECT conindid FROM pg_constraint
    )
ORDER BY pg_relation_size(indexrelid) DESC;

-- ============================================================================
-- 4. Duplicate Indexes
-- ============================================================================

SELECT
    pg_size_pretty(SUM(pg_relation_size(idx))::BIGINT) AS total_size,
    (array_agg(idx))[1] AS idx1, (array_agg(idx))[2] AS idx2,
    (array_agg(idx))[3] AS idx3, (array_agg(idx))[4] AS idx4
FROM (
    SELECT
        indrelid::regclass,
        array_agg(indexrelid::regclass) AS idx
    FROM pg_index
    WHERE indrelid IN (
        SELECT oid FROM pg_class WHERE relnamespace = (
            SELECT oid FROM pg_namespace WHERE nspname = 'claims'
        )
    )
    GROUP BY indrelid, indkey
    HAVING COUNT(*) > 1
) sub
GROUP BY indrelid, idx;

-- ============================================================================
-- 5. Index Fragmentation and Bloat
-- ============================================================================

SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    CASE
        WHEN idx_scan = 0 THEN 'UNUSED'
        WHEN idx_scan < 100 THEN 'LOW_USAGE'
        WHEN idx_scan < 1000 THEN 'MEDIUM_USAGE'
        ELSE 'HIGH_USAGE'
    END AS usage_category
FROM pg_stat_user_indexes
WHERE schemaname = 'claims'
ORDER BY pg_relation_size(indexrelid) DESC;

-- ============================================================================
-- 6. Index Coverage by Table
-- ============================================================================

SELECT
    t.relname AS table_name,
    COUNT(i.indexrelid) AS index_count,
    pg_size_pretty(SUM(pg_relation_size(i.indexrelid))) AS total_index_size,
    pg_size_pretty(pg_relation_size(t.oid)) AS table_size,
    ROUND(100.0 * SUM(pg_relation_size(i.indexrelid)) / 
          NULLIF(pg_relation_size(t.oid), 0), 2) AS index_overhead_pct
FROM pg_class t
JOIN pg_index ix ON t.oid = ix.indrelid
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'claims'
    AND t.relkind = 'r'
GROUP BY t.relname, t.oid
ORDER BY SUM(pg_relation_size(i.indexrelid)) DESC;

-- ============================================================================
-- 7. Partial Index Effectiveness
-- ============================================================================

SELECT
    schemaname,
    tablename,
    indexname,
    pg_get_indexdef(indexrelid) AS index_definition,
    idx_scan AS scans,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'claims'
    AND indexrelid IN (
        SELECT oid FROM pg_class WHERE relname LIKE '%_where_%'
    )
    OR indexname LIKE '%_where_%'
ORDER BY idx_scan DESC;

-- ============================================================================
-- 8. GIN/GIST Index Analysis (for full-text search)
-- ============================================================================

SELECT
    i.schemaname,
    i.tablename,
    i.indexname,
    am.amname AS index_type,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size,
    i.idx_scan AS scans,
    i.idx_tup_read AS tuples_read
FROM pg_stat_user_indexes i
JOIN pg_class c ON c.oid = i.indexrelid
JOIN pg_am am ON am.oid = c.relam
WHERE i.schemaname = 'claims'
    AND am.amname IN ('gin', 'gist')
ORDER BY pg_relation_size(i.indexrelid) DESC;

-- ============================================================================
-- 9. Index Maintenance Recommendations
-- ============================================================================

WITH index_stats AS (
    SELECT
        schemaname,
        tablename,
        indexname,
        idx_scan,
        pg_relation_size(indexrelid) AS index_size_bytes,
        pg_relation_size(indexrelid) / 1024.0 / 1024.0 AS index_size_mb
    FROM pg_stat_user_indexes
    WHERE schemaname = 'claims'
)
SELECT
    tablename,
    indexname,
    CASE
        WHEN idx_scan = 0 AND index_size_mb > 10 THEN
            'CANDIDATE_FOR_REMOVAL - Large unused index'
        WHEN idx_scan < 10 AND index_size_mb > 100 THEN
            'REVIEW_NEEDED - Large index with low usage'
        WHEN idx_scan > 1000 THEN
            'HEALTHY - High usage'
        ELSE
            'MONITOR - Normal usage'
    END AS recommendation,
    idx_scan AS scans,
    ROUND(index_size_mb, 2) AS size_mb
FROM index_stats
ORDER BY 
    CASE 
        WHEN idx_scan = 0 AND index_size_mb > 10 THEN 1
        WHEN idx_scan < 10 AND index_size_mb > 100 THEN 2
        ELSE 3
    END,
    index_size_mb DESC;

-- ============================================================================
-- 10. Partition Index Analysis
-- ============================================================================

SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size,
    pg_stat_get_numscans(i.oid) AS scans
FROM pg_class t
JOIN pg_index ix ON t.oid = ix.indrelid
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'claims'
    AND t.relkind = 'r'
    AND t.relname LIKE 'claims_%'
ORDER BY pg_relation_size(i.oid) DESC;

