# ADR-003: Celery with Redis for Asynchronous Processing

## Status
Accepted

## Context
We need an asynchronous task queue system for:
- Document OCR processing (can take 30+ seconds)
- Batch evaluation jobs (100-1000 claims)
- Retry logic with exponential backoff
- Dead letter queue for failed tasks
- Webhook notifications on completion
- Horizontal scaling of workers

## Decision
We will use **Celery** with **Redis** as the message broker for asynchronous task processing.

## Rationale

### Celery
- **Python Native**: Integrates seamlessly with FastAPI and existing Python code
- **Mature**: Battle-tested, used by Instagram, Pinterest, Spotify
- **Flexible**: Supports multiple brokers (Redis, RabbitMQ, SQS)
- **Features**: Retry logic, rate limiting, task prioritization, result backends
- **Monitoring**: Flower for task monitoring
- **Scalability**: Horizontal scaling of workers

### Redis as Broker
- **Performance**: In-memory, sub-millisecond latency
- **Simplicity**: Single service for both broker and cache
- **Cost**: Lower cost than managed message queue services
- **Features**: Pub/sub, lists, sorted sets for task queues
- **Persistence**: Optional persistence for durability

## Alternatives Considered

### 1. RabbitMQ
- **Pros**: Mature, feature-rich, durable queues
- **Cons**: More complex setup, separate service from cache
- **Decision**: Rejected due to complexity and Redis already needed for cache

### 2. AWS SQS
- **Pros**: Managed service, auto-scaling, dead letter queues
- **Cons**: Vendor lock-in, additional cost, network latency
- **Decision**: Rejected due to vendor lock-in and cost

### 3. Apache Kafka
- **Pros**: High throughput, distributed, event streaming
- **Cons**: Overkill for task queues, complex setup, higher operational overhead
- **Decision**: Rejected due to complexity and use case mismatch

### 4. RQ (Redis Queue)
- **Pros**: Simpler than Celery, Redis-native
- **Cons**: Less features, smaller ecosystem, less mature
- **Decision**: Rejected due to feature requirements (retry, prioritization)

## Implementation Details

### Celery Configuration
- **Broker**: Redis (connection pooling)
- **Result Backend**: Redis (for task results)
- **Task Serialization**: JSON (human-readable, secure)
- **Worker Concurrency**: 4-8 workers per pod (CPU-bound tasks)
- **Task Timeout**: 5 minutes for OCR, 30 minutes for batch jobs

### Task Types
1. **OCR Processing Tasks**: High priority, retry 3 times
2. **Batch Evaluation Tasks**: Normal priority, retry 2 times
3. **Webhook Notification Tasks**: Low priority, retry 1 time
4. **Dead Letter Queue Tasks**: Manual review, no retry

### Retry Strategy
- **Max Retries**: 3 attempts
- **Backoff**: Exponential (1s, 2s, 4s)
- **Jitter**: ±20% of backoff time
- **Dead Letter Queue**: After max retries

### Worker Scaling
- **Auto-Scaling**: Based on queue depth
- **Min Workers**: 10 (OCR), 5 (batch)
- **Max Workers**: 50 (OCR), 20 (batch)
- **Scale Trigger**: Queue depth > 100

## Consequences

### Positive
- Seamless Python integration
- Single Redis service for broker and cache
- Mature ecosystem with good documentation
- Flexible task configuration
- Horizontal scaling support

### Negative
- Redis single point of failure (mitigated by Redis Sentinel/Cluster)
- Task visibility requires monitoring tools (Flower)
- No built-in task scheduling (use Celery Beat or cron)

### Mitigations
- Redis Sentinel for high availability
- Flower for task monitoring
- Celery Beat for scheduled tasks
- Dead letter queue monitoring and alerts

## References
- [Celery Best Practices](https://docs.celeryproject.org/en/stable/userguide/tasks.html#best-practices)
- [Redis as Celery Broker](https://docs.celeryproject.org/en/stable/getting-started/backends-and-brokers/redis.html)
- [Celery Scaling](https://docs.celeryproject.org/en/stable/userguide/workers.html)

