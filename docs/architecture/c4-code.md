# C4 Model - Code Level (Decision Engine Core)

## Code Structure - Decision Engine

```
decision_service/
├── engine/
│   ├── __init__.py
│   ├── decision_engine.py          # Main decision orchestrator
│   ├── eligibility.py               # Eligibility calculation
│   ├── invoice_parser.py           # Invoice parsing logic
│   ├── rule_evaluator.py            # Rule execution
│   └── confidence_scorer.py         # Confidence scoring
│
├── repositories/
│   ├── __init__.py
│   ├── claim_repository.py          # Claim data access
│   ├── decision_repository.py       # Decision data access
│   └── document_repository.py       # Document data access
│
├── schemas/
│   ├── __init__.py
│   ├── request.py                   # Request models
│   ├── response.py                  # Response models
│   └── decision.py                  # Decision domain models
│
└── clients/
    ├── __init__.py
    ├── cache_client.py              # Redis client
    └── s3_client.py                 # S3 client
```

## Key Code Components

### 1. Decision Engine Orchestrator

```python
# engine/decision_engine.py
class DecisionEngine:
    """
    Main orchestrator for claim decision processing.
    Coordinates eligibility, parsing, and rule evaluation.
    """

    def __init__(
        self,
        eligibility_engine: EligibilityEngine,
        invoice_parser: InvoiceParser,
        rule_evaluator: RuleEvaluator,
        confidence_scorer: ConfidenceScorer
    ):
        self.eligibility_engine = eligibility_engine
        self.invoice_parser = invoice_parser
        self.rule_evaluator = rule_evaluator
        self.confidence_scorer = confidence_scorer

    async def evaluate_claim(
        self,
        claim_id: int,
        override_max_benefit: Optional[Decimal] = None
    ) -> Decision:
        """
        Evaluate a claim and generate a decision.

        Returns:
            Decision object with status, amounts, and reasoning
        """
        # 1. Load claim and documents
        claim = await self._load_claim(claim_id)
        documents = await self._load_documents(claim_id)

        # 2. Parse invoice documents
        invoice_data = await self._parse_invoices(documents)

        # 3. Calculate eligibility
        eligibility_result = await self.eligibility_engine.calculate(
            claim=claim,
            invoice_data=invoice_data
        )

        # 4. Evaluate business rules
        rule_result = await self.rule_evaluator.evaluate(
            claim=claim,
            eligibility_result=eligibility_result
        )

        # 5. Calculate confidence
        confidence = await self.confidence_scorer.calculate(
            claim=claim,
            eligibility_result=eligibility_result,
            rule_result=rule_result
        )

        # 6. Build decision
        decision = Decision(
            claim_id=claim_id,
            proposed_status=rule_result.status,
            proposed_benefit_amount=rule_result.benefit_amount,
            eligible_total=eligibility_result.eligible_total,
            invoice_total=invoice_data.total_amount,
            cap_amount=override_max_benefit or claim.max_benefit,
            approved_line_items=eligibility_result.approved_items,
            ineligible_line_items=eligibility_result.ineligible_items,
            flags=rule_result.flags,
            missing_data=rule_result.missing_data,
            reasoning=rule_result.reasoning,
            confidence_score=confidence,
            engine_version=self.rule_evaluator.version
        )

        return decision
```

### 2. Eligibility Engine

```python
# engine/eligibility.py
class EligibilityEngine:
    """
    Determines eligibility of line items based on policy rules.
    """

    async def calculate(
        self,
        claim: Claim,
        invoice_data: InvoiceData
    ) -> EligibilityResult:
        """
        Calculate eligible amounts for each line item.

        Policy Rules:
        - Normal wear and tear: Ineligible
        - Pre-existing damage: Ineligible
        - Tenant-caused damage: Eligible (up to cap)
        - Cleaning fees: Eligible if beyond normal wear
        """
        approved_items = []
        ineligible_items = []

        for line_item in invoice_data.line_items:
            eligibility = await self._evaluate_line_item(
                line_item=line_item,
                claim=claim
            )

            if eligibility.is_eligible:
                approved_items.append({
                    "description": line_item.description,
                    "amount": line_item.amount,
                    "reason": eligibility.reason
                })
            else:
                ineligible_items.append({
                    "description": line_item.description,
                    "amount": line_item.amount,
                    "reason": eligibility.reason
                })

        eligible_total = sum(item["amount"] for item in approved_items)

        return EligibilityResult(
            approved_items=approved_items,
            ineligible_items=ineligible_items,
            eligible_total=Decimal(str(eligible_total))
        )
```

### 3. Invoice Parser

```python
# engine/invoice_parser.py
class InvoiceParser:
    """
    Extracts structured data from invoice documents.
    """

    async def parse_documents(
        self,
        documents: List[Document]
    ) -> InvoiceData:
        """
        Parse invoice documents and extract line items.
        """
        invoice_docs = [
            doc for doc in documents
            if doc.document_type == DocumentType.INVOICE
        ]

        if not invoice_docs:
            raise NoInvoiceFoundError("No invoice documents found")

        all_line_items = []

        for doc in invoice_docs:
            text = await self._get_document_text(doc)
            line_items = await self._extract_line_items(text)
            all_line_items.extend(line_items)

        total_amount = sum(item.amount for item in all_line_items)

        return InvoiceData(
            line_items=all_line_items,
            total_amount=Decimal(str(total_amount)),
            document_count=len(invoice_docs)
        )

    async def _extract_line_items(self, text: str) -> List[LineItem]:
        """
        Extract line items using regex patterns and NLP.
        """
        # Pattern matching for common invoice formats
        # NLP for complex cases
        # Amount validation
        pass
```

### 4. Rule Evaluator

```python
# engine/rule_evaluator.py
class RuleEvaluator:
    """
    Executes business rules and generates decision.
    """

    def __init__(self, rule_loader: RuleLoader):
        self.rule_loader = rule_loader
        self.version = rule_loader.get_current_version()

    async def evaluate(
        self,
        claim: Claim,
        eligibility_result: EligibilityResult
    ) -> RuleResult:
        """
        Evaluate all applicable business rules.
        """
        rules = await self.rule_loader.load_rules(claim.claim_date)

        flags = {"critical": [], "warnings": [], "info": []}
        missing_data = {"fields": [], "needs_user_input": False}

        # Apply cap rule
        benefit_amount = min(
            eligibility_result.eligible_total,
            claim.max_benefit or Decimal("999999.99")
        )

        # Check for missing required data
        if not claim.lease_start_date:
            missing_data["fields"].append("lease_start_date")
            flags["warnings"].append("Missing lease start date")

        # Determine status
        if benefit_amount > 0:
            status = DecisionStatus.APPROVE
        else:
            status = DecisionStatus.DENY

        reasoning = {
            "eligible_total": str(eligibility_result.eligible_total),
            "cap_applied": str(claim.max_benefit),
            "final_amount": str(benefit_amount),
            "rule_version": self.version
        }

        return RuleResult(
            status=status,
            benefit_amount=benefit_amount,
            flags=flags,
            missing_data=missing_data,
            reasoning=reasoning
        )
```

### 5. Repository Pattern

```python
# repositories/decision_repository.py
class DecisionRepository:
    """
    Data access layer for decisions.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        cache_client: CacheClient
    ):
        self.db = db_session
        self.cache = cache_client

    async def create_decision(
        self,
        decision: Decision,
        user_id: str
    ) -> DecisionRecord:
        """
        Create a new decision with audit logging.
        """
        async with self.db.begin():
            # Supersede old decisions
            await self._supersede_old_decisions(decision.claim_id)

            # Create decision record
            decision_record = DecisionRecord(
                claim_id=decision.claim_id,
                decision_type=DecisionType.AUTOMATED,
                proposed_status=decision.proposed_status,
                proposed_benefit_amount=decision.proposed_benefit_amount,
                eligible_total=decision.eligible_total,
                invoice_total=decision.invoice_total,
                cap_amount=decision.cap_amount,
                approved_line_items=decision.approved_line_items,
                ineligible_line_items=decision.ineligible_line_items,
                flags=decision.flags,
                missing_data=decision.missing_data,
                reasoning=decision.reasoning,
                confidence_score=decision.confidence_score,
                engine_version=decision.engine_version,
                decided_by=user_id,
                is_active=True
            )

            self.db.add(decision_record)
            await self.db.flush()

            # Create audit log entry
            await self._create_audit_log(decision_record, user_id)

            # Invalidate cache
            await self.cache.delete(f"decision:{decision.claim_id}")

        return decision_record

    async def get_active_decision(
        self,
        claim_id: int
    ) -> Optional[DecisionRecord]:
        """
        Get active decision for a claim (with caching).
        """
        cache_key = f"decision:{claim_id}"

        # Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            return DecisionRecord.parse_raw(cached)

        # Query database
        result = await self.db.execute(
            select(DecisionRecord)
            .where(
                DecisionRecord.claim_id == claim_id,
                DecisionRecord.is_active == True
            )
        )
        decision = result.scalar_one_or_none()

        # Cache result
        if decision:
            await self.cache.set(
                cache_key,
                decision.model_dump_json(),
                ttl=3600
            )

        return decision
```

## Code Quality Standards

- **Type Hints**: All functions use Python type hints
- **Async/Await**: All I/O operations are async
- **Error Handling**: Custom exceptions with proper inheritance
- **Logging**: Structured JSON logging with context
- **Testing**: Unit tests with >80% coverage
- **Documentation**: Docstrings for all public methods

## Design Patterns Used

- **Repository Pattern**: Data access abstraction
- **Strategy Pattern**: Rule evaluation strategies
- **Factory Pattern**: Service creation
- **Circuit Breaker**: External service resilience
- **Retry Pattern**: Exponential backoff for failures
