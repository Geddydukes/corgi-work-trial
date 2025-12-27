# ADR-002: PostgreSQL with Read Replicas

## Status
Accepted

## Context
We need a database solution that can handle:
- 100M+ claims over 7 years
- 10:1 read:write ratio
- Sub-10ms lookups by tracking_number
- Complex queries with JSONB data
- Full-text search capabilities
- ACID transactions for decision consistency
- Partitioning for performance and maintenance

## Decision
We will use **PostgreSQL 14+** with **3 read replicas** for read operations.

## Rationale

### PostgreSQL
- **ACID Compliance**: Critical for financial decision data
- **JSONB Support**: Native JSONB for flexible decision data (flags, reasoning, line items)
- **Full-Text Search**: Built-in TSVECTOR for document search
- **Partitioning**: Native table partitioning (yearly for claims, monthly for audit logs)
- **Mature Ecosystem**: SQLAlchemy ORM, Alembic migrations
- **Performance**: Optimized indexes, query planner, connection pooling
- **Open Source**: No vendor lock-in, active community

### Read Replicas
- **Read Scaling**: Distribute read load across 3 replicas
- **High Availability**: Failover to replica if primary fails
- **Performance**: Sub-10ms lookups with proper indexing
- **Cost Effective**: Read replicas cheaper than scaling primary

## Alternatives Considered

### 1. MySQL
- **Pros**: Widely used, good performance
- **Cons**: Weaker JSON support, no native partitioning (requires manual sharding)
- **Decision**: Rejected due to JSONB and partitioning requirements

### 2. MongoDB
- **Pros**: Flexible schema, horizontal scaling
- **Cons**: No ACID transactions across documents, weaker query capabilities
- **Decision**: Rejected due to ACID requirements and complex queries

### 3. Amazon Aurora PostgreSQL
- **Pros**: Managed service, auto-scaling, high availability
- **Cons**: Vendor lock-in, higher cost
- **Decision**: Considered but not required initially (can migrate later)

### 4. CockroachDB
- **Pros**: Distributed, horizontal scaling
- **Cons**: Newer technology, less mature, overkill for current scale
- **Decision**: Rejected due to complexity and current scale requirements

## Implementation Details

### Primary Database
- **Instance**: Single primary for writes
- **Connection Pool**: Max 100 connections per service
- **Backup**: Continuous WAL archiving, daily full backups
- **Failover**: Active-passive with < 5 minute RTO

### Read Replicas
- **Count**: 3 replicas for read operations
- **Routing**: Application-level routing (read operations to replicas)
- **Lag**: < 1 second replication lag target
- **Failover**: Automatic promotion if primary fails

### Partitioning Strategy
- **Claims Table**: Yearly partitions (2020-2027)
- **Audit Log Table**: Monthly partitions
- **Benefits**: Faster queries, easier maintenance, archive old data

### Indexing Strategy
- **B-Tree Indexes**: For equality and range queries
- **GIST Indexes**: For full-text search (TSVECTOR)
- **Partial Indexes**: For filtered queries (e.g., active decisions only)

## Consequences

### Positive
- Strong ACID guarantees for financial data
- Excellent JSONB support for flexible decision data
- Native partitioning for performance
- Full-text search without external service
- Mature ecosystem (SQLAlchemy, Alembic)

### Negative
- Vertical scaling limits (mitigated by read replicas)
- Manual partition management required
- Connection pool management needed

### Mitigations
- Use read replicas for all read operations
- Automate partition creation (cron job)
- Connection pooling with SQLAlchemy
- Monitor replication lag and query performance

## References
- [PostgreSQL Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [PostgreSQL JSONB Performance](https://www.postgresql.org/docs/current/datatype-json.html)
- [Read Replica Best Practices](https://www.postgresql.org/docs/current/high-availability.html)

