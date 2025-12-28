"""
Document Analyzer: Uses Gemini 2.5 Pro to analyze documents for denial reasons.
"""

import logging
import json
from typing import Dict, List, Optional
from decimal import Decimal
from shared import config
from decision_service.engine.json_validator import (
    parse_and_validate_line_item_analysis,
    enforce_claim_amount_constraint,
    LineItemAnalysis
)
from decision_service.engine.deterministic_rules import apply_deterministic_rules

logger = logging.getLogger(__name__)


class DocumentAnalyzer:
    """Analyzes documents using Gemini 2.5 Pro to identify denial reasons."""
    
    def __init__(self):
        self.version = "v1.0.0"
    
    def analyze_document(
        self,
        text: str,
        filename: str,
        document_type: str
    ) -> Dict:
        """
        Analyze a document to identify potential denial reasons.
        
        Args:
            text: Extracted text from the document
            filename: Original filename
            document_type: Type of document (invoice, addendum, lease, etc.)
        
        Returns:
            Dict with denial_reasons, is_normal_wear_tear, has_eligible_charges, analysis
        """
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=config.Config.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            
            prompt = f"""Analyze this security deposit claim document to identify potential denial reasons.

DOCUMENT TYPE: {document_type}
FILENAME: {filename}

DOCUMENT TEXT:
{text[:10000]}

TASK:
Analyze the document and identify:
1. What charges or information are listed (if any)
2. Whether there are any issues that would cause a DENIAL:
   - Normal wear and tear (not covered)
   - Charges not covered by addendum
   - Missing required information
   - Ineligible charges
   - No security deposit collected (waiver)
   - Other denial reasons

Be specific and cite evidence from the document.

RESPONSE FORMAT (JSON only):
{{
    "charges_found": ["list of charges or information found"],
    "denial_reasons": ["specific reason 1", "specific reason 2"],
    "is_normal_wear_tear": true/false,
    "has_eligible_charges": true/false,
    "no_deposit_collected": true/false,
    "missing_information": ["list of missing items"],
    "analysis": "Detailed explanation with evidence from document"
}}"""
            
            logger.debug(f"Analyzing document {filename} with Gemini 2.5 Pro...")
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Extract JSON from response
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            
            result = json.loads(response_text)
            
            return {
                'denial_reasons': result.get('denial_reasons', []),
                'is_normal_wear_tear': result.get('is_normal_wear_tear', False),
                'has_eligible_charges': result.get('has_eligible_charges', False),
                'no_deposit_collected': result.get('no_deposit_collected', False),
                'missing_information': result.get('missing_information', []),
                'charges_found': result.get('charges_found', []),
                'analysis': result.get('analysis', ''),
                'document_type': document_type,
                'filename': filename
            }
            
        except Exception as e:
            logger.error(f"Document analysis error for {filename}: {e}")
            return {
                'denial_reasons': [],
                'is_normal_wear_tear': False,
                'has_eligible_charges': False,
                'no_deposit_collected': False,
                'missing_information': [],
                'charges_found': [],
                'analysis': f'Analysis error: {str(e)}',
                'document_type': document_type,
                'filename': filename
            }
    
    def extract_line_items_from_invoice(
        self,
        invoice_text: str,
        filename: str
    ) -> List[Dict]:
        """
        Extract line items directly from invoice text using Gemini.
        Bypasses the broken invoice parser.
        """
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=config.Config.GEMINI_API_KEY)
            
            prompt = f"""Extract line items from this invoice/statement document.

FILENAME: {filename}

INVOICE TEXT:
{invoice_text[:8000]}

TASK:
Extract ALL line items from this invoice/statement, including:
- Initial balance / Beginning balance (if present - this is a prior balance that should be included)
- All charges (rent, fees, cleaning, repairs, etc.)
- All payments/credits (negative amounts)
- All transactions listed in the statement

For each line item, provide:
- description: Clear description of what the charge/payment/balance is for
- amount: The dollar amount (positive for charges and balances, negative for payments/credits)
- line_number: Approximate line number if visible

IMPORTANT:
- Extract ALL line items including initial balances, beginning balances, and prior balances
- Extract all charges, fees, payments, and credits
- Do NOT extract: page numbers, invoice numbers, final totals (unless they're line items), or other non-transaction metadata
- If amounts seem unrealistic (over $10,000 for a single item), verify carefully
- Group related items together if they appear on the same line
- Include the initial/beginning balance as a separate line item if it appears in the statement

RESPONSE FORMAT (JSON only):
{{
    "line_items": [
        {{
            "description": "Description of the charge/payment/balance",
            "amount": 123.45,
            "line_number": 1
        }},
        ...
    ],
    "total_amount": 1234.56,
    "confidence": 0.0-1.0
}}"""
            
            logger.info(f"Extracting line items from {filename} with Gemini 2.5 Flash...")
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Extract JSON from response
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            
            result = json.loads(response_text)
            return result.get('line_items', [])
            
        except Exception as e:
            logger.error(f"Line item extraction error for {filename}: {e}")
            return []
    
    def analyze_line_items_batch(
        self,
        line_items: List[Dict],
        addendum_text: Optional[str],
        claim_context: Dict
    ) -> List[Dict]:
        """
        Analyze multiple line items in a single batch request to Gemini.
        More efficient than individual requests.
        
        Args:
            line_items: List of line item dicts with 'description', 'amount', etc.
            addendum_text: Text from addendum document
            claim_context: Claim context (max_benefit, security_deposit, etc.)
        
        Returns:
            List of line items with added flags
        """
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=config.Config.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            
            # Prepare line items for batch analysis
            items_text = "\n".join([
                f"{i+1}. {item.get('description', 'No description')} - ${item.get('amount', 0):.2f}"
                for i, item in enumerate(line_items)
            ])
            
            # Get critical constraints
            claim_amount = claim_context.get('claim_amount')
            max_benefit = claim_context.get('max_benefit')
            
            # Calculate cap
            if claim_amount is not None and max_benefit is not None:
                cap = min(claim_amount, max_benefit)
                cap_message = f"min(claim_amount=${claim_amount:.2f}, max_benefit=${max_benefit:.2f}) = ${cap:.2f}"
            elif claim_amount is not None:
                cap = claim_amount
                cap_message = f"claim_amount=${claim_amount:.2f}"
            elif max_benefit is not None:
                cap = max_benefit
                cap_message = f"max_benefit=${max_benefit:.2f}"
            else:
                cap = None
                cap_message = "N/A"
            
            # Format claim_amount and max_benefit for prompt
            claim_amount_str = f"${claim_amount:.2f}" if claim_amount is not None else "N/A"
            max_benefit_str = f"${max_benefit:.2f}" if max_benefit is not None else "N/A"
            
            # Include lease text if available for improper notice analysis
            lease_text = claim_context.get('lease_text', '')
            lease_section = f"""
LEASE TEXT (for verifying lease end date and payment status):
{lease_text if lease_text else 'No lease document found'}
""" if lease_text else ""

            prompt = f"""Analyze these security deposit claim line items and provide CATEGORY TAGS and SUGGESTIONS only.

IMPORTANT: You are NOT making coverage decisions. You are only providing category tags and suggestions.
Coverage decisions will be made by deterministic rules based on your tags.

LINE ITEMS:
{items_text}

CLAIM CONTEXT:
Claim Amount: {claim_amount_str}
Max Benefit: {max_benefit_str}
Security Deposit: ${claim_context.get('security_deposit', 'N/A')}

ADDENDUM TEXT (Security Deposit Waiver/Addendum):
{addendum_text if addendum_text else 'No addendum found'}
{lease_section}

TASK:
For EACH line item, provide:
1. **Category tags** (for deterministic rule matching):
   - Is this a rent charge? (residential rent, garage rent, month-to-month rent, future months rent)
   - Is this a cleaning charge? (cleaning, carpet cleaning, stains, etc.)
   - Is this a repair charge? (drywall, paint, broken items, drip pans, etc.)
   - Is this a damage charge? (damage, holes, scratches, etc.)
   - Is this an improper notice charge?
   - Is this covered by other insurance? (pet insurance, renters insurance for fire/water damage)
   - Is this a contractual fee? (reletting fee, late charge, utility revenue, etc.)

2. **Normal wear/tear suggestion** (is_normal_wear_tear):
   - Only mark as true if it's CLEARLY normal wear/tear (minor scuffs, expected wear)
   - Actual damage, broken items, excessive cleaning, carpet cleaning = NOT normal wear/tear
   - This is a SUGGESTION only - deterministic rules will make final decision

3. **Confidence level** (0.0-1.0): How confident are you in your categorization?

4. **Brief reasoning**: Explain your categorization

The "should_be_included" field is required by the schema but will be ignored. Deterministic rules will decide coverage based on category tags, not this field.

REQUIRED OUTPUT FORMAT (JSON ONLY - no markdown, no explanations outside JSON):
{{
    "line_item_analyses": [
        {{
            "line_item_number": 1,
            "should_be_included": true,
            "is_normal_wear_tear": false,
            "is_covered_by_addendum": true,
            "is_covered_by_other_insurance": false,
            "confidence": 0.9,
            "reasoning": "Brief explanation of categorization",
            "addendum_reference": "Quote from addendum if relevant, or 'N/A'"
        }}
    ]
}}

VALIDATION RULES:
- Return ONLY the JSON object, no markdown code blocks
- All boolean values must be true/false (not "true"/"false" strings)
- confidence must be a number between 0.0 and 1.0
- reasoning must be a non-empty string
- line_item_number must be sequential integers starting at 1
- Array length must match the number of line items provided ({len(line_items)})
"""
            
            logger.info(f"Batch analyzing {len(line_items)} line items with Gemini 2.5 Flash...")
            
            # Retry LLM call if JSON validation fails
            max_llm_retries = 3
            validated_analyses = None
            validation_errors = []
            json_validation_failed = False
            response_text = None
            
            for llm_attempt in range(max_llm_retries):
                try:
                    response = model.generate_content(prompt)
                    response_text = response.text.strip()
                    
                    # Use JSON validator with retries for parsing
                    validated_analyses, validation_errors, json_validation_failed = parse_and_validate_line_item_analysis(
                        response_text, len(line_items), max_retries=2, default_on_failure=False
                    )
                    
                    # If validation succeeded, break out of retry loop
                    if validated_analyses and not json_validation_failed:
                        if llm_attempt > 0:
                            logger.info(f"JSON validation succeeded on retry attempt {llm_attempt + 1}")
                        break
                    
                    # If this is not the last attempt, log and retry
                    if llm_attempt < max_llm_retries - 1:
                        logger.warning(f"JSON validation failed on attempt {llm_attempt + 1}/{max_llm_retries}: {validation_errors[:3]}")
                        logger.info(f"Retrying LLM call...")
                    else:
                        # Last attempt failed - use default fallback
                        logger.error(f"JSON validation failed after {max_llm_retries} LLM attempts. Using default-include fallback.")
                        validated_analyses, validation_errors, json_validation_failed = parse_and_validate_line_item_analysis(
                            response_text, len(line_items), max_retries=0, default_on_failure=True
                        )
                        
                except Exception as e:
                    logger.error(f"Error calling LLM on attempt {llm_attempt + 1}: {e}")
                    if llm_attempt == max_llm_retries - 1:
                        # Final attempt failed - use default fallback
                        logger.error("All LLM retry attempts failed. Using default-include fallback.")
                        validated_analyses, validation_errors, json_validation_failed = parse_and_validate_line_item_analysis(
                            "", len(line_items), max_retries=0, default_on_failure=True
                        )
            
            if validation_errors:
                logger.warning(f"JSON validation errors: {validation_errors[:5]}")  # Show first 5 errors
                if response_text:
                    logger.debug(f"Response was: {response_text[:500]}")
            
            if not validated_analyses:
                logger.error("Failed to validate JSON response even with default fallback")
                # Mark all items as having JSON validation failed
                for item in line_items:
                    item['json_validation_failed'] = True
                return line_items
            
            if json_validation_failed:
                logger.warning("JSON validation failed - using default-include analyses, deterministic rules will filter")
                # Flag this in all items for tracking
                for item in line_items:
                    item['json_validation_failed'] = True
            
            analyses = validated_analyses
            
            # Extract LLM suggestions (advisory only)
            llm_suggestions = []
            for i, analysis in enumerate(analyses):
                llm_suggestions.append({
                    'is_normal_wear_tear': analysis.is_normal_wear_tear,
                    'is_covered_by_addendum': analysis.is_covered_by_addendum,
                    'confidence': analysis.confidence,
                    'reasoning': analysis.reasoning
                })
            
            # Apply deterministic rules (coverage decisions made here)
            lease_end_date = claim_context.get('lease_end_date')
            flagged_items = apply_deterministic_rules(
                line_items=line_items,
                lease_end_date=lease_end_date,
                llm_suggestions=llm_suggestions
            )
            
            # Preserve LLM metadata for audit trail
            for i, (item, analysis) in enumerate(zip(flagged_items, analyses)):
                item['llm_confidence'] = analysis.confidence
                item['llm_reasoning'] = analysis.reasoning
                item['llm_addendum_reference'] = analysis.addendum_reference
                item['llm_suggested_included'] = analysis.should_be_included
                item['is_covered_by_addendum'] = analysis.is_covered_by_addendum  # Preserve for deterministic rules
            
            # Enforce claim_amount constraint (after deterministic rules applied)
            if claim_amount is not None and flagged_items:
                claim_amount_decimal = Decimal(str(claim_amount))
                max_benefit_decimal = Decimal(str(max_benefit)) if max_benefit is not None else None
                
                # Convert flagged items back to LineItemAnalysis format for constraint enforcement
                updated_analyses = []
                for i, flagged in enumerate(flagged_items):
                    analysis = LineItemAnalysis(
                        line_item_number=i + 1,
                        should_be_included=flagged.get('should_be_included', False),
                        is_normal_wear_tear=flagged.get('is_normal_wear_tear', False),
                        is_covered_by_addendum=flagged.get('is_covered_by_addendum', True),
                        is_covered_by_other_insurance=flagged.get('is_covered_by_other_insurance', False),
                        confidence=flagged.get('llm_confidence', 0.5),
                        reasoning=flagged.get('llm_reasoning', 'Deterministic rule applied'),
                        addendum_reference=flagged.get('llm_addendum_reference', 'N/A')
                    )
                    updated_analyses.append(analysis)
                
                flagged_items, eligible_total, constraint_messages = enforce_claim_amount_constraint(
                    flagged_items, updated_analyses, claim_amount_decimal, max_benefit_decimal
                )
                
                if constraint_messages:
                    logger.info(f"Claim amount constraint applied: {constraint_messages}")
            
            return flagged_items
            
        except Exception as e:
            logger.error(f"Batch line item analysis error: {e}")
            # Return items without flags if analysis fails
            return line_items
    
    def analyze_line_item(
        self,
        line_item: Dict,
        addendum_text: Optional[str],
        claim_context: Dict
    ) -> Dict:
        """
        Analyze a single line item to determine if it should be included.
        
        Args:
            line_item: Dict with 'description', 'amount', etc.
            addendum_text: Text from addendum document
            claim_context: Claim context (max_benefit, security_deposit, etc.)
        
        Returns:
            Dict with flags: should_be_included, is_normal_wear_tear, is_covered_by_addendum, confidence, reasoning
        """
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=config.Config.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            
            description = line_item.get('description', 'No description')
            amount = line_item.get('amount', 0)
            
            prompt = f"""Analyze this security deposit claim line item to determine if it should be approved.

LINE ITEM:
Description: {description}
Amount: ${amount:.2f}

CLAIM CONTEXT:
Max Benefit: ${claim_context.get('max_benefit', 'N/A')}
Security Deposit: ${claim_context.get('security_deposit', 'N/A')}

ADDENDUM TEXT (Security Deposit Waiver/Addendum):
{addendum_text if addendum_text else 'No addendum found'}

ANALYSIS FRAMEWORK:
Think through each line item systematically:

1. **IMPROPER NOTICE CHARGES**: If a line item is labeled as "Improper Notice" or similar notice-related charges:
   - ALWAYS DENY (should_be_included = false)
   - Assume the invoice labeling is correct - if it says "Improper Notice", it is an improper notice charge
   - These charges are NOT covered by security deposit protection
   - These are lease violation fees, not property damage

2. **OTHER INSURANCE COVERAGE**: Is this charge covered by OTHER insurance policies?
   - Check if the charge might be covered by renters insurance, pet insurance, or other policies
   - If covered by other insurance, DENY (should_be_included = false) - security deposit protection should not duplicate other coverage
   - Examples: pet-related damages (may be covered by pet insurance), fire damage (may be covered by renters insurance)

3. **SCOPE CHECK**: Is this charge within the scope of security deposit protection?
   - Security deposit protection typically covers tenant-caused damage, repairs, and cleaning beyond normal wear/tear
   - Consider if this charge might be covered by OTHER policies or deposits (pet deposit, pet policy, separate fees, etc.)
   - Consider if this charge is for something OUTSIDE the scope of security deposit protection (e.g., rent charges, fees that should be handled separately)

4. **COVERAGE CHECK**: Is this charge covered by the addendum protections?
   - Review the addendum text to see what types of charges are explicitly covered
   - If the addendum doesn't mention this type of charge, consider whether it falls under general security deposit protection

5. **NORMAL WEAR AND TEAR**: Is this normal wear and tear?
   - Normal wear and tear is NOT covered (e.g., minor scuffs, expected wear)
   - Actual damage beyond normal wear IS covered

6. **REPAIR CHARGES**: Repair charges (drywall, paint, broken items) ARE typically covered IF:
   - They represent actual damage (not normal wear/tear)
   - They are within the scope of security deposit protection
   - They are NOT covered by other insurance policies
   - They are NOT improper notice charges

TASK:
1. Review the line item description and amount
2. Check if this is an "Improper Notice" charge - if so, DENY
3. Check if this is covered by OTHER insurance (renters, pet, etc.) - if so, DENY
4. Check if the addendum covers this type of charge
5. Apply the critical rules above
6. Determine if this line item should be INCLUDED in the approved benefit amount
7. Check if it's normal wear and tear

RESPONSE FORMAT (JSON only):
{{
    "should_be_included": true/false,
    "is_normal_wear_tear": true/false,
    "is_covered_by_addendum": true/false,
    "is_covered_by_other_insurance": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation (must state which rule applies)",
    "addendum_reference": "Quote from addendum if relevant, or 'N/A'"
}}"""
            
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Extract JSON from response
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            
            result = json.loads(response_text)
            
            # Auto-deny improper notice charges
            description_lower = description.lower()
            is_improper_notice = (
                'improper notice' in description_lower or
                ('improper' in description_lower and 'notice' in description_lower)
            )
            
            # Auto-deny items that should be covered by other insurance
            # Check for common patterns indicating other insurance coverage
            is_pet_related = any(keyword in description_lower for keyword in [
                'flea', 'pet', 'dog', 'cat', 'animal', 'pest control', 'pest treatment',
                'pet deposit', 'pet damage', 'pet cleaning'
            ])
            
            is_fire_related = any(keyword in description_lower for keyword in [
                'fire', 'smoke', 'burn', 'flame'
            ])
            
            is_water_damage = any(keyword in description_lower for keyword in [
                'water damage', 'flood', 'leak', 'overflow', 'sewer', 'drain', 'sump'
            ])
            
            # If Gemini flagged it as covered by other insurance, or if it matches patterns
            is_covered_by_other_insurance = (
                result.get('is_covered_by_other_insurance', False) or
                is_pet_related or  # Pet-related charges should be covered by pet insurance
                is_fire_related or  # Fire damage should be covered by renters insurance
                is_water_damage  # Water damage should be covered by renters insurance
            )
            
            should_include = result.get('should_be_included', False)
            if is_improper_notice:
                should_include = False
            
            # Auto-deny if covered by other insurance (assume it was necessary, so deny)
            if is_covered_by_other_insurance:
                should_include = False
            
            return {
                'should_be_included': should_include,
                'is_normal_wear_tear': result.get('is_normal_wear_tear', False),
                'is_covered_by_addendum': result.get('is_covered_by_addendum', False),
                'is_covered_by_other_insurance': is_covered_by_other_insurance,
                'confidence': float(result.get('confidence', 0.5)),
                'reasoning': result.get('reasoning', 'No reasoning provided'),
                'addendum_reference': result.get('addendum_reference', 'N/A')
            }
            
        except Exception as e:
            logger.error(f"Line item analysis error: {e}")
            return {
                'should_be_included': False,
                'is_normal_wear_tear': False,
                'is_covered_by_addendum': False,
                'confidence': 0.0,
                'reasoning': f'Analysis error: {str(e)}',
                'addendum_reference': 'N/A'
            }
    
    def analyze_all_documents_batch(
        self,
        documents: List[Dict]
    ) -> Dict:
        """
        Analyze all documents for a claim in a single batch request to Gemini.
        More efficient than individual requests.
        
        Args:
            documents: List of document dicts with extracted_text, original_filename, document_type
        
        Returns:
            Aggregated analysis with combined denial reasons and flags
        """
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=config.Config.GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            
            # Prepare document summaries for batch analysis
            document_summaries = []
            for doc in documents:
                text = doc.get('extracted_text', '')
                filename = doc.get('original_filename', 'Unknown')
                doc_type = doc.get('document_type', 'unknown')
                
                if not text:
                    continue
                
                # Truncate long documents but keep important info
                text_preview = text[:3000] if len(text) > 3000 else text
                document_summaries.append({
                    'filename': filename,
                    'type': doc_type,
                    'text_preview': text_preview,
                    'full_length': len(text)
                })
            
            if not document_summaries:
                logger.warning("No documents with text to analyze")
                return self._empty_analysis()
            
            # Create batch prompt
            documents_text = "\n\n".join([
                f"=== DOCUMENT {i+1}: {doc['filename']} (Type: {doc['type']}) ===\n{doc['text_preview']}"
                for i, doc in enumerate(document_summaries)
            ])
            
            prompt = f"""Analyze ALL these security deposit claim documents together to identify potential denial reasons.

DOCUMENTS PROVIDED:
{documents_text}

TASK:
Analyze all documents together and identify:
1. What charges are listed in invoices/statements
2. What protections/coverage are specified in the addendum (if present)
3. Whether there are any issues that would cause a DENIAL:
   - Charges are normal wear and tear (not covered)
   - Charges are NOT covered by the addendum protections
   - Missing required information (invoices, evidence)
   - Ineligible charges that don't qualify under addendum
   - Other denial reasons

IMPORTANT:
- If there's a security deposit waiver addendum, that's EXPECTED - don't deny just because no deposit was collected
- Focus on whether the CHARGES qualify under the addendum protections
- Deny if charges are normal wear/tear OR not covered by addendum protections
- Approve if charges ARE covered by addendum protections

Look for patterns across documents (e.g., addendum shows what's covered, invoice shows charges, check if charges match addendum coverage)

RESPONSE FORMAT (JSON only):
{{
    "charges_found": ["list of all charges found across documents"],
    "addendum_protections": ["what the addendum covers/protects"],
    "denial_reasons": ["specific reason 1", "specific reason 2"],
    "is_normal_wear_tear": true/false,
    "charges_covered_by_addendum": true/false,
    "has_eligible_charges": true/false,
    "missing_information": ["list of missing items"],
    "analysis": "Detailed explanation with evidence from documents",
    "document_specific_findings": {{
        "filename1": ["finding 1", "finding 2"],
        "filename2": ["finding 1"]
    }}
}}"""
            
            logger.info(f"Batch analyzing {len(document_summaries)} documents with Gemini 2.5 Pro...")
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Extract JSON from response
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            
            result = json.loads(response_text)
            
            # Process results
            all_denial_reasons = result.get('denial_reasons', [])
            has_normal_wear_tear = result.get('is_normal_wear_tear', False)
            charges_covered_by_addendum = result.get('charges_covered_by_addendum', False)
            has_eligible_charges = result.get('has_eligible_charges', False)
            missing_information = result.get('missing_information', [])
            addendum_protections = result.get('addendum_protections', [])
            
            # Determine critical denial flags
            # Only flag as critical if charges are EXCLUSIVELY normal wear/tear
            # Missing documentation should be warnings, not denials
            critical_flags = []
            warnings = []
            
            # Only critical if ALL charges are normal wear/tear with NO eligible charges
            if has_normal_wear_tear and not has_eligible_charges:
                critical_flags.append("charges_are_normal_wear_tear")
            elif has_normal_wear_tear and has_eligible_charges:
                # Some normal wear/tear but also eligible charges - just warn
                warnings.append("some_charges_may_be_normal_wear_tear")
            
            # Missing "Explanation of Protections" is common - don't deny for it, just warn
            if missing_information:
                for info in missing_information:
                    if 'explanation of protections' in info.lower():
                        warnings.append("missing_explanation_of_protections_document")
                    else:
                        warnings.append(f"missing_information: {info[:50]}")
            
            # Should deny ONLY if charges are EXCLUSIVELY normal wear/tear with no eligible charges
            # Don't deny just because of missing documentation - flag for review instead
            should_deny = (
                has_normal_wear_tear and not has_eligible_charges
            )
            
            # If there are eligible charges but also normal wear/tear, don't deny - approve eligible portion
            # If charges are covered by addendum, don't deny even if some are normal wear/tear
            if charges_covered_by_addendum:
                should_deny = False
            
            return {
                'denial_reasons': all_denial_reasons,
                'is_normal_wear_tear': has_normal_wear_tear,
                'charges_covered_by_addendum': charges_covered_by_addendum,
                'has_eligible_charges': has_eligible_charges,
                'addendum_protections': addendum_protections,
                'missing_information': missing_information,
                'charges_found': result.get('charges_found', []),
                'document_specific_findings': result.get('document_specific_findings', {}),
                'analysis': result.get('analysis', ''),
                'critical_flags': critical_flags,
                'warnings': warnings,
                'should_deny': should_deny
            }
            
        except Exception as e:
            logger.error(f"Batch document analysis error: {e}")
            return self._empty_analysis()
    
    def _empty_analysis(self) -> Dict:
        """Return empty analysis structure."""
        return {
            'denial_reasons': [],
            'is_normal_wear_tear': False,
            'charges_covered_by_addendum': False,
            'has_eligible_charges': False,
            'addendum_protections': [],
            'missing_information': [],
            'charges_found': [],
            'document_specific_findings': {},
            'analysis': '',
            'critical_flags': [],
            'warnings': [],
            'should_deny': False
        }
    
    def analyze_all_documents(
        self,
        documents: List[Dict]
    ) -> Dict:
        """
        Analyze all documents for a claim using batch processing.
        
        Args:
            documents: List of document dicts with extracted_text, original_filename, document_type
        
        Returns:
            Aggregated analysis with combined denial reasons and flags
        """
        return self.analyze_all_documents_batch(documents)

