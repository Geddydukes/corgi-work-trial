# Architecture Decision Records (ADR)

This directory contains Architecture Decision Records (ADRs) documenting key architectural decisions for the Security Deposit Claims Decision Engine.

## What is an ADR?

An Architecture Decision Record is a document that captures an important architectural decision made along with its context and consequences. ADRs help:
- Document why decisions were made
- Provide context for future developers
- Enable decision review and reconsideration
- Share knowledge across the team

## ADR Format

Each ADR follows this structure:
- **Status**: Proposed, Accepted, Rejected, Deprecated, Superseded
- **Context**: The situation and requirements
- **Decision**: What was decided
- **Rationale**: Why this decision was made
- **Alternatives Considered**: Other options evaluated
- **Consequences**: Positive and negative impacts
- **References**: Links to relevant documentation

## Current ADRs

1. **[ADR-001: Use Python 3.11 with FastAPI](./001-python-fastapi.md)**
   - Decision to use Python 3.11 and FastAPI framework

2. **[ADR-002: PostgreSQL with Read Replicas](./002-postgresql-with-read-replicas.md)**
   - Decision to use PostgreSQL with read replicas for database

3. **[ADR-003: Celery with Redis for Asynchronous Processing](./003-celery-redis-task-queue.md)**
   - Decision to use Celery with Redis for task queue

4. **[ADR-004: Tiered OCR Approach](./004-ocr-tiered-approach.md)**
   - Decision to use tiered OCR (Tesseract → Textract fallback)

5. **[ADR-005: Kubernetes for Container Orchestration](./005-kubernetes-deployment.md)**
   - Decision to use Kubernetes for container orchestration

6. **[ADR-006: Terraform for Infrastructure as Code](./006-terraform-infrastructure.md)**
   - Decision to use Terraform for infrastructure management

## Adding a New ADR

1. Create a new file: `NNN-short-title.md` (where NNN is the next number)
2. Use the template below
3. Update this README with the new ADR
4. Submit for team review

## ADR Template

```markdown
# ADR-NNN: [Short Title]

## Status
[Proposed | Accepted | Rejected | Deprecated | Superseded]

## Context
[Describe the situation and requirements]

## Decision
[State the decision]

## Rationale
[Explain why this decision was made]

## Alternatives Considered
1. [Alternative 1]
   - Pros: ...
   - Cons: ...
   - Decision: Rejected/Accepted

## Consequences

### Positive
- ...

### Negative
- ...

### Mitigations
- ...

## References
- [Link to relevant documentation]
```

## Review Process

1. **Proposed**: ADR is created and submitted for review
2. **Accepted**: ADR is approved and decision is implemented
3. **Rejected**: ADR is rejected, alternative chosen
4. **Deprecated**: ADR is no longer relevant but kept for history
5. **Superseded**: ADR is replaced by a newer ADR

## References

- [ADR GitHub Template](https://github.com/joelparkerhenderson/architecture-decision-record)
- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)

