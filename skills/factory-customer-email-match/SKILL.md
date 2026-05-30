---
name: factory-customer-email-match
description: Generate or review structured English B2B outbound email drafts for Dingsheng Plastic and Silicone by combining upstream customer research signals with stored factory facts. Use when implementing or operating an email-draft node that must return a short prospecting email plus machine-readable metadata for review and sending workflows.
---

# Factory Customer Email Match

Use this skill as the specification for an email-draft node in a broader outreach workflow.

This skill does not own the full pipeline. It should only:
- consume upstream customer research and stored factory facts
- draft or review a short outbound email
- return structured metadata that downstream nodes can consume

This skill should not:
- crawl websites
- maintain the source-of-truth factory database
- send the email
- replace a dedicated review node

Read `references/dingsheng-profile.md` when you need the company profile, product scope, credibility points, or customer-fit mapping.
If the application provides stored factory facts from the database, use those stored facts as the primary source of truth for certificates, audit support, MOQ, lead time, response speed, and signature details.
Prefer stored database facts over older memory, generic defaults, or broad profile summaries when they conflict.
If `references/dingsheng-profile.md` is unavailable, continue with the core positioning already defined in this skill:
- Dingsheng is a stable supplier of food-grade silicone kitchen tools and related kitchenware.
- Default strengths are stable quality, workable MOQ, reliable lead times, and practical OEM/ODM support when clearly relevant.
- Do not invent factory scale claims, customer lists, certifications, or testing details that are not available in the current evidence.

## Node Role

Recommended node name:

`personalized_email_draft_node`

Primary responsibility:
- turn `customer + research + factory_context + draft_policy` into `subject + body + metadata`

Success condition:
- the draft reads like a real export salesperson wrote it
- the claims stay inside supported evidence and stored factory facts
- the output is structured enough for downstream review and send nodes

## Input Schema

Expect a structured input object from upstream systems.

Use this shape unless the application already has an equivalent schema:

```json
{
  "request_id": "req_20260527_001",
  "customer": {
    "company_name": "Hello Housewares Germany",
    "website": "https://example.com",
    "country": "DE",
    "market_region": "EU",
    "language": "en",
    "buyer_type": "distributor",
    "contact_name": "",
    "contact_role": "",
    "crm_context": {
      "has_prior_contact": false,
      "last_contact_at": null,
      "owner": "sales_01"
    }
  },
  "research": {
    "customer_signal": "Website shows a broad kitchen and serving assortment.",
    "signal_strength": "medium",
    "evidence": [
      {
        "source_type": "website",
        "page": "/kitchen",
        "quote": "Kitchen and serving assortment",
        "category": "product_range"
      }
    ],
    "inference_flags": [],
    "personalization_angle": "kitchenware_supply"
  },
  "factory_context": {
    "source": "factory_knowledge_db",
    "proof_points": ["LFGB", "FDA", "ISO 9001"],
    "operational_facts": {
      "silicone_moq_simple": "2,000 units",
      "sample_lead_time": "7-14 days",
      "quote_dfm_turnaround": "within 48 hours"
    },
    "signature": {
      "sender_name": "Dingsheng Sales Team",
      "company_name": "Dingsheng Plastic & Silicone Co., Ltd.",
      "email": "admin@hzhesheng.com.cn",
      "phone": "+86 150 1809 1819"
    }
  },
  "draft_policy": {
    "email_type": "first_touch",
    "tone": "professional",
    "language": "en",
    "manual_review_mode": "flag_only",
    "max_words": 110
  }
}
```

Required input fields:
- `customer.company_name`
- `research.evidence`
- `research.signal_strength`
- `factory_context` or equivalent stored-facts source
- `draft_policy.language`

Preferred optional fields:
- `customer.contact_name`
- `customer.contact_role`
- `customer.country`
- `customer.market_region`
- `customer.crm_context`
- `research.personalization_angle`
- `research.inference_flags`
- `factory_context.operational_facts`

If the application uses different field names, map them to this schema before applying the drafting logic.

## Standard Input Fields

Treat these as standard workflow fields, not informal writing hints.

- `signal_strength`
  - allowed values: `strong`, `medium`, `weak`
  - upstream research should supply this whenever possible
  - this node may derive a fallback value only if upstream omitted it

- `language`
  - allowed value: `en`
  - this node always drafts directly in English
  - do not use this node to route or decide multilingual output

- `manual_review_mode`
  - allowed values:
    - `flag_only`
    - `block_on_weak_signal`
    - `always_review`
  - this field controls workflow behavior, not just writing style

## Signal Consumption Rules

Use upstream research fields as the default source of truth.

- Default source:
  - `research.customer_signal`
  - `research.signal_strength`
  - `research.evidence`
  - `research.personalization_angle`
- Do not silently replace upstream values just because a different interpretation also seems possible.
- Only derive local fallback values when:
  - `research.customer_signal` is missing or empty
  - `research.signal_strength` is missing
  - upstream evidence is clearly inconsistent with the provided label
- If local fallback is used, expose that in output metadata:
  - `metadata.signal_source = "local_fallback"`
- If upstream values are used without conflict, expose:
  - `metadata.signal_source = "upstream"`
- If upstream values appear inconsistent with the supplied evidence, do not silently overwrite them. Instead:
  - keep the workflow auditable
  - set `review_required = true`
  - add a review reason such as `signal_evidence_conflict`
  - use a metadata marker such as `metadata.signal_source = "upstream_conflicted"`

## Output Schema

Return a structured result object that downstream nodes can consume directly.

Use this shape unless the application already has a compatible schema:

```json
{
  "request_id": "req_20260527_001",
  "status": "ok",
  "review_required": false,
  "review_reason": [],
  "draft": {
    "subject": "Silicone Kitchen Tools for Your Housewares Range",
    "body": "Hello Housewares Germany team,\n\nI noticed your website features a broad kitchen and serving range.\n\nWe manufacture food-grade silicone kitchen tools, backed by LFGB and FDA food-contact testing and an ISO 9001-certified quality system. Sample lead time is typically 7-14 days.\n\nIf useful, I can send a short overview with suitable items and the relevant compliance documents.\n\nBest regards,\nDingsheng Sales Team\nDingsheng Plastic & Silicone Co., Ltd.\nadmin@hzhesheng.com.cn\n+86 150 1809 1819"
  },
  "metadata": {
    "language": "en",
    "buyer_type": "distributor",
    "email_type": "first_touch",
    "signal_strength": "medium",
    "personalization_angle": "kitchenware_supply",
    "proof_points_used": ["LFGB", "FDA", "ISO 9001"],
    "operational_facts_used": ["sample_lead_time"],
    "evidence_used": [
      {
        "page": "/kitchen",
        "quote": "Kitchen and serving assortment"
      }
    ],
    "contains_inference": false,
    "tone_risk": "low"
  }
}
```

Standard output fields:
- `status`
  - allowed values: `ok`, `needs_review`, `blocked`
- `review_required`
  - boolean workflow flag for downstream routing
- `review_reason`
  - array of machine-readable reasons from a controlled set
- `draft.subject`
- `draft.body`
- `metadata.signal_strength`
- `metadata.proof_points_used`
- `metadata.operational_facts_used`
- `metadata.evidence_used`
- `metadata.language`

Do not return only free-form prose if the workflow expects downstream automation.

### Output Contract

Treat this as a contract, not as an illustrative example only.

Required for every output:
- `request_id`
- `status`
- `review_required`
- `review_reason`
- `metadata.language`
- `metadata.signal_strength` if known from upstream or local fallback
- `metadata.evidence_used`
- `metadata.signal_source`

Status-specific requirements:

- `status = ok`
  - `draft.subject`: required
  - `draft.body`: required
  - `review_required`: may be `false` or `true`
  - `review_reason`: may be empty

- `status = needs_review`
  - `draft.subject`: required
  - `draft.body`: required
  - `review_required`: must be `true`
  - `review_reason`: must contain at least one machine-readable reason

- `status = blocked`
  - `draft.subject`: optional
  - `draft.body`: optional
  - `review_required`: must be `true`
  - `review_reason`: must contain at least one machine-readable reason
  - `metadata.signal_strength`: required if known
  - `metadata.evidence_used`: still required, even if the draft body is absent

Allowed `review_reason` values:
- `weak_signal`
- `signal_evidence_conflict`
- `missing_evidence`
- `missing_factory_context`
- `missing_signature`
- `inference_present`
- `unsupported_private_label_claim`
- `unsupported_brand_owner_claim`
- `forbidden_phrase_detected`
- `too_many_claims`
- `manual_review_policy`

Optional output fields:
- `draft.notes`
- `metadata.personalization_angle`
- `metadata.proof_points_used`
- `metadata.operational_facts_used`
- `metadata.contains_inference`
- `metadata.tone_risk`
- `metadata.buyer_type`

Null and empty-value rules:
- Prefer empty arrays over missing keys for list fields such as `review_reason`, `proof_points_used`, and `operational_facts_used`.
- Prefer omitting optional scalar fields instead of filling them with guessed placeholders.
- Do not return a fake draft body just to satisfy a schema shape when `status = blocked`.

### Boundary Examples

Weak signal with blocking policy:

```json
{
  "request_id": "req_20260527_002",
  "status": "blocked",
  "review_required": true,
  "review_reason": ["weak_signal"],
  "draft": {},
  "metadata": {
    "language": "en",
    "signal_strength": "weak",
    "signal_source": "upstream",
    "evidence_used": [
      {
        "page": "/",
        "quote": "Kitchen products"
      }
    ]
  }
}
```

Evidence conflict from upstream research:

```json
{
  "request_id": "req_20260527_003",
  "status": "needs_review",
  "review_required": true,
  "review_reason": ["signal_evidence_conflict"],
  "draft": {
    "subject": "Quick question about your kitchen assortment",
    "body": "Hello Team,\n\nI noticed your website features kitchen-related items.\n\nWe manufacture food-grade silicone kitchen tools and can share a short overview if useful.\n\nBest regards,\nDingsheng Sales Team\nDingsheng Plastic & Silicone Co., Ltd.\nadmin@hzhesheng.com.cn\n+86 150 1809 1819"
  },
  "metadata": {
    "language": "en",
    "signal_strength": "strong",
    "signal_source": "upstream_conflicted",
    "evidence_used": [
      {
        "page": "/products",
        "quote": "Kitchen accessories"
      }
    ]
  }
}
```

Upstream signal missing, local fallback used:

```json
{
  "request_id": "req_20260527_004",
  "status": "ok",
  "review_required": false,
  "review_reason": [],
  "draft": {
    "subject": "Quick question about your kitchen assortment",
    "body": "Hello Housewares Germany team,\n\nI noticed your website features a broad kitchen and serving range.\n\nWe manufacture food-grade silicone kitchen tools backed by LFGB and FDA food-contact testing, with an ISO 9001-certified quality system.\n\nIf useful, I can send a short overview with a few suitable items.\n\nBest regards,\nDingsheng Sales Team\nDingsheng Plastic & Silicone Co., Ltd.\nadmin@hzhesheng.com.cn\n+86 150 1809 1819"
  },
  "metadata": {
    "language": "en",
    "buyer_type": "distributor",
    "signal_strength": "medium",
    "signal_source": "local_fallback",
    "proof_points_used": ["LFGB", "FDA", "ISO 9001"],
    "operational_facts_used": [],
    "evidence_used": [
      {
        "page": "/kitchen",
        "quote": "Kitchen and serving assortment"
      }
    ],
    "contains_inference": false,
    "tone_risk": "low"
  }
}
```

Buyer-type routing example for `hotel_supplier`:

```json
{
  "request_id": "req_20260527_005",
  "status": "ok",
  "review_required": false,
  "review_reason": [],
  "draft": {
    "subject": "Silicone Kitchen Tools for Your Hospitality Range",
    "body": "Hello Hospitality Supply Team,\n\nI noticed your assortment includes kitchen and service items for hospitality buyers.\n\nWe manufacture food-grade silicone kitchen tools, backed by LFGB and FDA food-contact testing and an ISO 9001-certified quality system. For hospitality supply projects, we mainly focus on consistent quality and reliable lead times.\n\nIf useful, I can send a short overview of suitable silicone items.\n\nBest regards,\nDingsheng Sales Team\nDingsheng Plastic & Silicone Co., Ltd.\nadmin@hzhesheng.com.cn\n+86 150 1809 1819"
  },
  "metadata": {
    "language": "en",
    "buyer_type": "hotel_supplier",
    "signal_strength": "strong",
    "signal_source": "upstream",
    "proof_points_used": ["LFGB", "FDA", "ISO 9001"],
    "operational_facts_used": [],
    "evidence_used": [
      {
        "page": "/hospitality",
        "quote": "Kitchen and service products for hospitality and catering buyers"
      }
    ],
    "contains_inference": false,
    "tone_risk": "low"
  }
}
```

Inference present and routed to review:

```json
{
  "request_id": "req_20260527_006",
  "status": "needs_review",
  "review_required": true,
  "review_reason": ["inference_present"],
  "draft": {
    "subject": "Quick question about your kitchen assortment",
    "body": "Hello Team,\n\nI noticed your website includes kitchen-related items.\n\nWe manufacture food-grade silicone kitchen tools and can share a short overview if useful.\n\nBest regards,\nDingsheng Sales Team\nDingsheng Plastic & Silicone Co., Ltd.\nadmin@hzhesheng.com.cn\n+86 150 1809 1819"
  },
  "metadata": {
    "language": "en",
    "buyer_type": "supplier",
    "signal_strength": "medium",
    "signal_source": "upstream",
    "proof_points_used": [],
    "operational_facts_used": [],
    "evidence_used": [
      {
        "page": "/products",
        "quote": "Kitchen accessories"
      }
    ],
    "contains_inference": true,
    "tone_risk": "low"
  }
}
```

## Node Boundaries

Upstream research node responsibilities:
- collect website or directory evidence
- classify `buyer_type`
- assign `signal_strength`
- provide `customer_signal`
- mark facts versus inference

Factory knowledge or database node responsibilities:
- provide approved proof points
- provide approved MOQ, lead time, response speed, and signature defaults
- maintain dynamic updates such as new certificates or contact changes

This drafting node responsibilities:
- select the smallest useful subset of facts for the email
- draft the subject and body
- expose structured metadata about what was used
- set `status`, `review_required`, and `review_reason`

Downstream review node responsibilities:
- check compliance, tone, and evidence consistency
- approve, revise, or route for manual handling

Downstream send node responsibilities:
- deliver the email
- write back delivery or CRM state

English-only routing rule:
- this node always outputs English
- set `draft_policy.language = "en"`
- set `metadata.language = "en"`
- if upstream provides a non-English language request, handle that outside this node or flag it as a workflow-policy mismatch

## Core Principle

Position us as a stable silicone kitchenware manufacturer and professional supplier, not as a factory trying to impress with size.
For most EU and US buyers, the real concerns are:
- stable quality
- smooth communication
- reliable lead times
- practical OEM/private-label execution
- food-contact compliance
- repeat-order reliability

Let the buyer notice fit, sourcing relevance, and reliability before noticing `factory` language.
Use manufacturer language only when it helps explain supply stability, quality control, OEM capability, or long-term cooperation.
Prefer identities such as:
- `food-grade silicone kitchenware manufacturer`
- `OEM silicone kitchen tools supplier`
- `private-label kitchenware supplier`

## Hard Execution Rules

These are not style suggestions. Treat them as pass/fail rules.

- Draft only after receiving or deriving one usable website signal.
- Consume upstream `customer_signal` and `signal_strength` by default.
- Do not re-research the customer when upstream research is already present, unless values are missing or evidence conflict must be flagged.
- If upstream omitted `signal_strength`, derive a fallback value using this scale:
  - `strong`: clear evidence such as `private label`, `own brand`, `OEM`, `importer`, `distributor`, `supplier`, or a clearly relevant product/category statement
  - `medium`: relevant assortment or category evidence is visible, but buyer role is not fully explicit
  - `weak`: only vague assortment wording, noisy navigation text, legal/footer text, marketplace links, or generic site language
- If `signal_strength = weak`, follow `manual_review_mode`:
  - `flag_only` -> return a draft with `status = needs_review`
  - `block_on_weak_signal` -> return `status = blocked` or a minimal review-only output
  - `always_review` -> return a draft with `review_required = true` even if the text is usable
- The email body must stay within 3-4 short body sentences before the sign-off.
- Use at most:
  - one customer-specific observation
  - one product family
  - one practical cooperation strength group
  - one CTA
- Prefer one concrete proof point over multiple vague quality adjectives whenever proof is available.
- Remove any sentence that sounds like explanation, interpretation, or market analysis instead of direct sales communication.
- If any forbidden phrase or forbidden sentence pattern appears, rewrite before finalizing.

## Evidence Rules

- Trust real website evidence before model inference.
- Use private-label or own-brand wording only when the site evidence clearly supports it.
- Do not let a generic AI summary force a `private label` angle if the quotes do not support it.
- If the website evidence is weak, say the draft needs manual review instead of forcing personalization.
- If you mention a market signal, ground it in real website evidence such as assortment breadth, distributor positioning, retail channel language, or baking/kitchen specialization.
- Do not claim products are `performing well`, `popular`, or `best-selling` unless the evidence explicitly supports it.
- Do not build the opening line from legal text, cookie text, marketplace links, navigation strings, or raw product-code blocks.
- If the top evidence is noisy, do not improvise. Return a manual-review draft.

## Workflow

1. Read upstream research fields first.
Use `research.customer_signal`, `research.signal_strength`, `research.evidence`, and `research.personalization_angle` if they are provided.
Treat upstream research as the default input, not as a suggestion to be routinely reinterpreted.

2. Validate upstream signal inputs.
Check whether the provided `customer_signal` is grounded in the supplied evidence.
Do not replace upstream values unless they are missing or clearly inconsistent.
If there is an evidence conflict, keep the issue visible in structured output instead of silently rewriting the research judgment.

3. Derive fallback signal values only when needed.
If `customer_signal` or `signal_strength` is missing, derive the smallest safe fallback from the available evidence.
Use the same `strong` / `medium` / `weak` scale defined above.
Record that fallback in metadata.

4. Match one product family and one buyer-facing cooperation strength.
Do not dump every advantage into the email.
Select the smallest set that logically matches the customer.

Prefer `customer.buyer_type` as the primary routing field.
Only fall back to keyword matching when `buyer_type` is missing, too broad, or clearly inconsistent with the evidence.

Buyer-type routing:
- `distributor`
  - opening angle: broad product range, trade supply, assortment coverage
  - strength angle: stable export supply, workable MOQ, reliable lead times, QC consistency
  - proof preference: LFGB, FDA, ISO 9001
  - avoid: strong OEM/private-label claims unless site evidence explicitly supports them
- `importer`
  - opening angle: sourcing range, product categories, import or supply focus
  - strength angle: repeat-order support, stable quality, lead-time discipline, MOQ practicality
  - proof preference: LFGB, FDA, ISO 9001
  - avoid: retail-facing language unless the evidence supports it
- `wholesaler`
  - opening angle: product breadth, supply to trade buyers, assortment relevance
  - strength angle: stable supply, practical MOQ, reliable replenishment
  - proof preference: LFGB, FDA, ISO 9001
  - avoid: brand-owner assumptions
- `brand_owner`
  - opening angle: own-brand range, product-line fit, or category expansion
  - strength angle: OEM/ODM support and compliance support
  - proof preference: LFGB, FDA, ISO 9001, BSCI when relevant
  - avoid: generic distributor wording if own-brand evidence is explicit
- `private_label`
  - opening angle: private-label or OEM sourcing signal on the site
  - strength angle: OEM/ODM support and practical execution
  - proof preference: LFGB, FDA, ISO 9001, BSCI when relevant
  - avoid: weak or guessed private-label phrasing, or unsupported execution-detail claims
- `retailer`
  - opening angle: consumer-facing kitchen range or category assortment
  - strength angle: compliance support, stable supply, consistent presentation and repeat orders
  - proof preference: LFGB, FDA, ISO 9001, BSCI when relevant
  - avoid: overloading the first-touch note with factory-detail jargon
- `hotel_supplier`
  - opening angle: hospitality, catering, foodservice, or service-item assortment
  - strength angle: durable repeat supply, consistency, lead-time reliability
  - proof preference: LFGB, FDA, ISO 9001
  - avoid: heavy private-label assumptions unless explicitly supported
- `supplier`
  - opening angle: kitchenware sourcing or trade-supply positioning
  - strength angle: stable export cooperation, MOQ flexibility, lead-time predictability
  - proof preference: LFGB, FDA, ISO 9001
  - avoid: overstating end-market knowledge

Keyword fallback mapping:
- `private label`, `brand owner`, `OEM`, `eigenmarke`, `own brand` -> OEM/ODM support and private-label execution.
- `distributor`, `wholesaler`, `importer`, `supplier` -> stable export supply, flexible MOQ, consistent lead time, QC support.
- `kitchen tools`, `utensils`, `baking`, `housewares` -> silicone spatulas, scrapers, brushes, baking tools, daily kitchen accessories.
- `food-contact`, `bakery`, `kitchen`, `quality-sensitive` -> FDA/LFGB materials, TUV/SGS testing support.
- `EU distributors`, `retailers`, `private-label programs` -> stable quality control, flexible MOQ, reliable repeat-order support, OEM customization when relevant.

Mixed-signal routing:
- If `buyer_type` is explicit, keep it as the primary route unless the evidence clearly contradicts it.
- If the customer shows both `distributor/importer` and `private label/own brand` signals, prefer the more specific commercial model in the cooperation-strength line.
- Use `OEM/ODM` or `private-label` language only when those signals are explicit on the site.
- If both are explicit, keep the opening line based on the clearest visible website observation, then choose the third line based on this priority:
  - `private label/own brand` signal -> OEM/ODM support
  - otherwise `distributor/importer` signal -> stable supply, MOQ, lead times, QC support
- Do not stack both buyer angles in the same short draft unless the site evidence is unusually clear and the email still stays concise.
- When in doubt, choose the safer distributor/importer angle over a guessed private-label angle.
- If `buyer_type` is unknown, route by the safest evidence-supported trade angle rather than by the most aggressive commercial angle.

5. Produce or preserve the decision metadata before drafting.
If upstream already provided these values, keep them unless there is a clear contradiction.
Use this exact structure internally or map it to application metadata:

```text
customer_signal:
signal_strength:
matched_product_family:
matched_strength:
market_signal_allowed:
```

Rules:
- `customer_signal` must be one short website-based observation only.
- `matched_product_family` should normally be one of: `silicone spatulas`, `silicone scrapers`, `silicone brushes`, `baking tools`, or `silicone kitchen tools`.
- `matched_strength` should be one short group such as `stable quality + workable MOQ + reliable lead times` or `OEM/ODM support`.
- `market_signal_allowed` must be `yes` only when the market-oriented sentence is grounded in real website evidence. Otherwise use `no`.
- If the system supports structured output, expose these values in `metadata` instead of leaving them hidden in prompt-only reasoning.

6. Write the email as a short first-touch note.
- First line: mention one real customer observation in natural language.
- Second line: connect that observation to one relevant product group from our side.
- Third line: mention one practical cooperation strength. If a concrete proof point is available and relevant, prefer that over generic reassurance.
- Optional fourth line: add one short credibility cue only if it clearly helps the target buyer type.
- Optional fifth line: add one light market-signal sentence only if the evidence supports it.
- Final line: ask one light question.

Preferred body skeleton:

```text
Line 1: I noticed your website [specific observation].
Line 2: We manufacture [one relevant product family].
Line 3: For [buyer type] projects, we mainly focus on [one practical cooperation strength group].
Line 4: If useful, I can send [one light CTA].
```

If the evidence is only medium strength, keep Line 1 broad but factual. Do not add interpretive claims.

7. Keep tone natural.
- Write like a real export salesperson, not a brochure and not a market analyst.
- Keep the message concise and easy to scan.
- Convert raw website evidence into a short buyer-friendly observation.
- Prefer direct language over explanatory transitions.

## Proof And Specificity Rules

- If stored factory facts are available from the database, check them before writing any proof, MOQ, lead-time, or signature claim.
- If the factory website or provided evidence clearly supports compliance or audit proof, prefer naming the proof directly instead of saying only `stable quality` or `strict QC`.
- One concrete fact is usually enough for a first-touch email. Do not stack proof points and operational facts unless the extra detail clearly lowers buyer risk.
- For EU kitchenware or food-contact projects, `LFGB` is usually the strongest first proof point when supported by evidence.
- `FDA` and `ISO 9001` are strong supporting proof points for first-touch emails when supported by evidence.
- For EU buyers or `market_region = EU`, prefer `LFGB` as the first proof point. Use `FDA` and `ISO 9001` only as supporting proof when they materially help.
- For `buyer_type = distributor` or `buyer_type = importer`, prefer one approved operational fact over a stack of generic adjectives:
  - first choice: `sample lead time: 7-14 days`
  - second choice: `MOQ from 2,000 units`
  - third choice: `quote / DFM turnaround: within 48 hours`
- Add `BSCI`, `SMETA`, or similar social/audit language only when it fits the buyer type and the sentence still stays concise.
- Do not stack too many proof items in one line. In most first-touch emails, 2-3 proof points are enough.
- If using proof points, write them in plain sales language, not as a compliance dump.
- When real numeric facts are available and relevant, one concrete fact such as MOQ, lead time, or response time is stronger than an extra vague reassurance sentence.
- Only use numeric facts such as MOQ or lead time when they are publicly supported or stored as approved factory facts. Do not guess.
- OEM/ODM direction is allowed, but do not mention `logo printing`, `Pantone color matching`, `packaging customization`, or similar execution details unless upstream research explicitly provides supporting evidence for those details.

### Single Best Fact Table

When choosing between multiple true facts, prefer the one that reduces the buyer's most likely first concern fastest.

- `buyer_type = distributor`
  - first choice: `sample lead time: 7-14 days`
  - second choice: `MOQ from 2,000 units`
  - third choice: `quote / DFM turnaround: within 48 hours`
  - use proof points only as support, not as the main fact, unless compliance is clearly the buyer's main concern

- `buyer_type = importer`
  - first choice: `sample lead time: 7-14 days`
  - second choice: `MOQ from 2,000 units`
  - third choice: `quote / DFM turnaround: within 48 hours`
  - use proof points only as support, not as the main fact, unless compliance is clearly the buyer's main concern

- `buyer_type = wholesaler`
  - first choice: `sample lead time: 7-14 days`
  - second choice: `MOQ from 2,000 units`
  - third choice: `quote / DFM turnaround: within 48 hours`

- `buyer_type = hotel_supplier`
  - first choice: `sample lead time: 7-14 days`
  - second choice: `LFGB`
  - third choice: `MOQ from 2,000 units`

- `buyer_type = retailer`
  - first choice: `LFGB` for EU food-contact relevance
  - second choice: `sample lead time: 7-14 days`
  - third choice: `ISO 9001`

- `buyer_type = brand_owner`
  - first choice: `OEM/ODM support`
  - second choice: `MOQ from 2,000 units`
  - third choice: `sample lead time: 7-14 days`
  - keep OEM claims directional unless the evidence explicitly supports execution details

- `buyer_type = private_label`
  - first choice: `OEM/ODM support`
  - second choice: `MOQ from 2,000 units`
  - third choice: `sample lead time: 7-14 days`
  - keep OEM claims directional unless the evidence explicitly supports execution details

- `buyer_type = supplier`
  - first choice: `sample lead time: 7-14 days`
  - second choice: `quote / DFM turnaround: within 48 hours`
  - third choice: `MOQ from 2,000 units`

- `buyer_type = unknown`
  - choose the safest fact from the evidence-supported trade angle
  - default order: `sample lead time` -> `LFGB` -> `MOQ`

- `new customer similarity concern`
  - do not claim similar-buyer cooperation unless approved evidence explicitly supports it
  - no default public proof for this claim currently exists in stored factory facts

### Tie-Break Rules

Use these rules when the same buyer type could reasonably receive either a proof point or an operational fact.

- `buyer_type = distributor` or `buyer_type = importer`
  - if the evidence clearly emphasizes EU food-contact, compliance, testing, bakery safety, or food-contact approval, prefer `LFGB` over `sample lead time`
  - otherwise prefer `sample lead time` over `LFGB`
  - practical reading:
    - compliance-first buyer concern -> `LFGB`
    - supply-speed buyer concern -> `sample lead time`

- `buyer_type = wholesaler`
  - follow the same rule as distributor/importer unless the evidence is too weak to justify compliance emphasis

- `buyer_type = private_label` or `buyer_type = brand_owner`
  - if the evidence clearly emphasizes urgent sampling, development speed, drawings, tooling timing, or quick sample review, prefer `sample lead time` over `MOQ`
  - otherwise prefer `MOQ` over `sample lead time`
  - practical reading:
    - urgency-first buyer concern -> `sample lead time`
    - commitment / feasibility-first buyer concern -> `MOQ`

- `buyer_type = hotel_supplier` or `buyer_type = retailer`
  - if food-contact or EU compliance is explicit, prefer `LFGB`
  - otherwise prefer `sample lead time`

- When tie-break conditions are not explicit, choose the safer, less interpretive fact.
- Do not put both the proof point and the operational fact into the same short first-touch sentence unless the added detail clearly reduces buyer risk.

## Greeting And Signature Rules

- Do not use a placeholder-looking greeting.
- Avoid all-uppercase company names in the greeting unless that is clearly the brand's normal public styling.
- If a real contact name is available, use it.
- If no contact name is available, use a natural fallback such as:
  - `Hi [Company Name] team,`
  - `Hello [Company Name] team,`
  - `Hi Purchasing Team,`
- The sign-off must include a real sender identity block, not only a brand fragment.
- Minimum signature block:
  - sender name
  - company name
  - email or website
- Add phone or WhatsApp when available and appropriate.
- Do not end with only `Plastic-Dingsheng` unless the user explicitly asks for an ultra-short signature.
- If stored factory facts provide the current signature defaults, use those instead of an older placeholder signature.

## Hedging Control

- Avoid stacking multiple softening phrases in one short email.
- Use at most one light softener in the body, unless the user explicitly wants a very deferential tone.
- Examples of over-hedging to avoid when combined in one draft:
  - `seemed relevant`
  - `usually points to`
  - `may fit`
  - `would it make sense`
- The email should sound respectful and low-pressure, but still confident that there is a relevant reason to reach out.

## Length Control Rules

If the draft runs long, cut in this order:

1. Remove the optional market-signal sentence.
2. Remove the optional credibility cue.
3. Compress the product list to `silicone kitchen tools` instead of listing spatulas, scrapers, brushes, and baking items.
4. Compress the strength line to the two most relevant points only.

Do not cut these unless manual review is required:
- the real customer observation
- the matched product family
- the main cooperation strength
- the one light CTA

When shortening, preserve specificity before polish. Do not replace a concrete website observation with generic sales wording just to save words.

## Website Extraction Notes

When reviewing extracted evidence, prefer:
- about/company text
- product or assortment pages
- private-label or own-brand pages
- clear distributor/importer/supplier statements

Treat these as noisy unless clearly useful:
- footer legal text
- privacy or cookie text
- marketplace link lists such as Amazon, OTTO, Kaufland, eBay, or QVC
- navigation strings like `Contact Jobs Menu`
- raw product codes, cart, checkout, or stock messages
- third-party embed disclaimers

If the top evidence is mostly noise, do not trust the personalization automatically.

## Style Notes

Prefer this kind of positioning:
- `We are a manufacturer of food-grade silicone kitchen tools, including spatulas, scrapers, brushes, and baking items.`
- `For importer and distributor projects, we mainly focus on stable quality control, workable MOQ, and reliable lead times.`
- `Our silicone kitchen tools are backed by LFGB and FDA food-contact testing, with an ISO 9001-certified quality system.`
- `We can also support OEM/ODM programs when that sourcing model is relevant on your side.`
- `Many of our kitchen-tool projects are for distributor, importer, and private-label programs in Europe.`

Avoid this kind of positioning:
- repeated `we are a factory`
- long factory introductions
- machine counts unless the user explicitly wants them
- broad factory bragging without buyer relevance
- generic `we supply silicone spatulas` with no sourcing context
- heavy sales language that sounds like AI or mass mailing
- analyst-style sentences such as `That kind of channel-focused assortment usually points to...`
- filler transitions such as `That seemed relevant because...`
- CTA wording such as `for reference`

## Forbidden Phrases And Patterns

Rewrite the draft if any of these appear:

- `That seemed relevant because...`
- `That kind of ... usually points to...`
- `Would it make sense for me to...`
- `for your reference`
- `your products are performing well`
- `popular in your market`
- `best-selling`
- unsupported detail claims such as `Pantone color matching`, `logo printing`, or `packaging customization` when upstream evidence does not support them
- any sentence that starts by explaining why the previous sentence matters instead of directly moving to the offer
- any sentence that sounds like a market analyst summarizing the buyer's business model
- any opening line that could be reused for almost any kitchenware buyer without sounding different
- any greeting that looks like an unfilled template or list-export artifact
- any signature that does not let the buyer identify who is writing and how to verify the sender

Prefer this kind of opening:
- `I noticed your website highlights a baking-focused kitchen range.`
- `I noticed your assortment includes kitchen and serving items for hospitality buyers.`
- `I noticed on your website that you offer private-label support alongside your wider kitchen range.`
- `I saw that your business focuses on importing and supplying kitchenware products.`

Avoid this kind of opening:
- long copied catalog strings
- raw product codes
- generic compliments
- unsupported statements like `your products are performing well in the EU market`
- website-summary wording that could fit almost any customer

Prefer this kind of CTA:
- `If useful, I can send a short overview of a few suitable silicone items.`
- `If relevant, I can send a brief selection of items that may fit your range.`
- `If helpful, I can share a short overview of suitable OEM options.`

Avoid this kind of CTA:
- `Would it make sense for me to...`
- `for your reference`
- any CTA with more than one ask

## Subject Guidance

- When the customer clearly fits private label or brand-owner sourcing, a direct subject can work well:
  - `OEM Silicone Kitchen Tools for Culinarta`
- When the site clearly shows distributor, importer, or broad trade-supply positioning but not explicit private label, use a direct but neutral subject:
  - `Silicone Kitchen Tools for Your Housewares Range`
  - `Silicone Kitchenware Supply for Your Product Range`
- Otherwise prefer short, neutral subjects tied to the product category:
  - `Quick question about your kitchen tools range`
  - `Quick question about your baking accessories range`
  - `Quick question about your kitchenware range`

Subject-line routing:
- Use a brand- or OEM-specific subject only when private-label, OEM, own-brand, or equivalent sourcing language is clearly supported by the site.
- Use a neutral product-range subject when the site clearly fits housewares, kitchenware, distributor, or importer positioning but the sourcing model is not fully explicit.
- Use the `Quick question about...` default when the evidence is only medium strength and you want the safest option.
- Do not force a highly personalized subject line if the body evidence is weak enough to require manual review.

## Output Rules

- Keep drafts short, usually around 60-110 English words.
- Use one customer-specific fact only if it is grounded in the website evidence.
- Use one product family and one practical cooperation strength by default.
- Add at most one short credibility cue.
- Add at most one light market-signal sentence, and only when evidence supports it.
- Sound like a mature export salesperson from a stable manufacturer, not like a generic trading company and not like a factory brochure.
- Prefer practical buyer-facing language over factory bragging.
- Default signature should use a real sender block tied to Dingsheng Plastic & Silicone Co., Ltd., not a bare brand fragment.
- If evidence is weak, say the draft needs manual review instead of forcing personalization.
- If `market_signal_allowed = no`, do not include any sentence about channel logic, repeat-order demand, market fit, or what the assortment suggests.
- If mixed signals exist, the chosen buyer angle should be explicit in the internal decision block and consistent with the body and subject line.
- If concrete proof points are available, prefer them over extra generic quality adjectives.
- The signature should make the sender look real and reachable.
- If the workflow is automated, pair the natural-language draft with structured metadata that downstream nodes can consume without another extraction pass.

## Self-check

Split validation into machine-verifiable checks and model-judgment checks.

### Machine-verifiable checks

These checks should be enforced by code, deterministic post-processing, or a downstream review node whenever possible.

- `draft.subject` must be present unless `status = blocked`
- `draft.body` must be present unless `status = blocked`
- `metadata.language` must equal `en`
- `status` must be one of `ok`, `needs_review`, `blocked`
- `review_required` must be `true` when `status = needs_review` or `status = blocked`
- `review_reason` must contain at least one value when `status = needs_review` or `status = blocked`
- If `status = blocked`, `review_reason` must not be empty
- `metadata.signal_source` must be one of `upstream`, `local_fallback`, `upstream_conflicted`
- The draft should usually stay within 60-110 English words unless a blocking or review-only path is being returned
- No forbidden phrase or forbidden pattern should appear
- The greeting should not look like an unfilled template or uppercase list-export artifact
- The signature should include at least:
  - sender name
  - company name
  - email or website
- Do not allow more than one question mark in the final body
- Do not allow unsupported `private label` or `own brand` wording when the evidence does not support it
- If `market_signal_allowed = no`, do not allow market-analysis sentences in the body

Recommended machine-readable failure reasons:
- `missing_subject`
- `missing_body`
- `invalid_status`
- `missing_review_reason`
- `invalid_signal_source`
- `forbidden_phrase_detected`
- `placeholder_greeting`
- `weak_signature`
- `too_many_questions`
- `unsupported_private_label_claim`
- `unsupported_brand_owner_claim`
- `market_signal_not_allowed`

### Model-judgment checks

These checks are still important, but they depend on language judgment rather than deterministic validation.

- The first paragraph clearly comes from the customer's website
- The supplier strengths are relevant to that specific customer type
- The email does not sound mass-mailed
- The CTA asks only one light question
- The buyer notices reliability and fit before noticing `factory` language
- Any `private label` wording feels commercially justified, not opportunistic
- Any market-signal sentence is light, commercially useful, and grounded in evidence
- The email reads like a real foreign-trade salesperson, not like AI summary text
- The same draft would not feel equally plausible if sent unchanged to five different buyers
- The draft uses the decision metadata consistently
- The draft does not overuse hedging language
- The signature feels real and reachable, not just technically complete

If any machine-verifiable check fails, return or route the draft as a review-required or blocked output instead of treating it as a normal success.
If any model-judgment check fails, rewrite the draft or send it to a review node instead of softening the issue in commentary.
