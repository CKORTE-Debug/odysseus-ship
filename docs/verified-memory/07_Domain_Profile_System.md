# 07 - Domain Profile System

## Purpose
Verified Memory should not be hardcoded only for IT. Different industries need different source priorities, staleness windows, privacy rules, and confidence requirements.

The Domain Profile System lets the same Verified Memory engine support IT, legal, medical, finance, academic research, gaming, business, and personal knowledge.

## Core idea
A `DomainProfile` is a policy bundle.

Each profile defines:

- Source priority
- Staleness periods
- Allowed / blocked source types
- Whether web verification is allowed
- Whether manual approval is required
- Whether special disclaimers or warnings are required
- Sensitivity defaults
- Confidence rules

## Recommended location

```text
verified_memory/domain_profiles/
  it_software.yaml
  legal.yaml
  medical.yaml
  finance.yaml
  academic.yaml
  gaming.yaml
  general_business.yaml
  personal_knowledge.yaml
```

## Base schema

```yaml
domain: it_software
description: Software, IT operations, devices, SaaS, and troubleshooting.
default_stale_after_days: 60
web_search_allowed: true
manual_approval_required: false
requires_disclaimer: false

claim_type_staleness:
  software_behavior: 60
  microsoft_365: 30
  pricing: 3

source_priority:
  - official_vendor_docs
  - official_release_notes
  - official_github
  - government_or_institution
  - trusted_technical_blog
  - wikipedia_background
  - forum_or_reddit

never_final_sources:
  - forum_or_reddit
  - unknown

sensitivity_defaults:
  local_document: private
  official_vendor_docs: public

verification_rules:
  stale_claims_require_refresh: true
  low_quality_sources_create_leads_only: true
  overwrite_requires_approval: true
```

## Built-in profiles

### IT / Software
Use for Microsoft 365, Windows, Intune, Surface, SaaS tools, infrastructure, game/software troubleshooting, and technical SOPs.

```yaml
domain: it_software
default_stale_after_days: 60
web_search_allowed: true
manual_approval_required: false
source_priority:
  - official_vendor_docs
  - official_release_notes
  - official_github
  - vendor_support_forum
  - trusted_technical_blog
  - wikipedia_background
  - forum_or_reddit
claim_type_staleness:
  microsoft_365: 30
  software_behavior: 60
  driver_or_firmware: 30
  pricing: 3
never_final_sources:
  - forum_or_reddit
  - unknown
```

### Legal
Use for laws, contracts, policy interpretation, compliance, and legal research. This profile must be conservative.

```yaml
domain: legal
default_stale_after_days: 30
web_search_allowed: true
manual_approval_required: true
requires_disclaimer: true
source_priority:
  - user_uploaded_contract
  - official_government_law_source
  - court_or_regulator_source
  - licensed_legal_database
  - law_firm_article_background_only
  - wikipedia_background
never_final_sources:
  - forum_or_reddit
  - unknown
claim_type_staleness:
  law_or_regulation: 30
  contract_clause: null
  legal_news: 7
```

### Medical / Health
Use for medication, health questions, symptoms, and clinical information. This profile must be conservative and should not replace professional advice.

```yaml
domain: medical
default_stale_after_days: 30
web_search_allowed: true
manual_approval_required: true
requires_disclaimer: true
source_priority:
  - doctor_user_provided_instruction
  - official_medication_insert
  - government_health_source
  - hospital_or_medical_institution
  - peer_reviewed_source
  - wikipedia_background
never_final_sources:
  - supplement_blog
  - seo_health_blog
  - forum_or_reddit
  - unknown
claim_type_staleness:
  medication_guidance: 30
  general_health_info: 90
  personal_doctor_instruction: null
```

### Finance
Use for investing, taxes, exchange rates, bank products, and market information.

```yaml
domain: finance
default_stale_after_days: 7
web_search_allowed: true
manual_approval_required: true
requires_disclaimer: true
source_priority:
  - official_regulator
  - official_company_filing
  - official_pricing_or_rate_page
  - major_financial_data_provider
  - reputable_financial_news
  - wikipedia_background
never_final_sources:
  - forum_or_reddit
  - unknown
claim_type_staleness:
  stock_price: 1
  exchange_rate: 1
  pricing: 3
  tax_rule: 30
```

### Academic / Research
Use for papers, citations, technical research, and literature reviews.

```yaml
domain: academic
default_stale_after_days: 180
web_search_allowed: true
manual_approval_required: false
source_priority:
  - peer_reviewed_paper
  - official_preprint
  - university_or_institution
  - official_dataset
  - reputable_secondary_summary
  - wikipedia_background
never_final_sources:
  - forum_or_reddit
  - unknown
claim_type_staleness:
  active_research_area: 90
  historical_paper: null
```

### Gaming / Entertainment
Use for games, patch notes, streaming availability, hardware/game performance, and community reports.

```yaml
domain: gaming
default_stale_after_days: 14
web_search_allowed: true
manual_approval_required: false
source_priority:
  - official_patch_notes
  - official_game_website
  - official_store_page
  - official_social_verified
  - community_wiki
  - forum_or_reddit
claim_type_staleness:
  patch_status: 7
  server_status: 1
  streaming_availability: 3
never_final_sources:
  - forum_or_reddit
  - unknown
```

### General business
Use for business writing, SOPs, internal policies, client communication templates, and project notes.

```yaml
domain: general_business
default_stale_after_days: 180
web_search_allowed: true
manual_approval_required: false
source_priority:
  - user_uploaded_policy
  - official_company_document
  - official_vendor_docs
  - reputable_business_source
  - wikipedia_background
claim_type_staleness:
  internal_sop: 180
  email_template: null
  project_note: 90
```

### Personal knowledge
Use for user preferences, routines, pet notes, household instructions, and stable personal preferences.

```yaml
domain: personal_knowledge
default_stale_after_days: null
web_search_allowed: false
manual_approval_required: true
source_priority:
  - user_statement
  - user_uploaded_document
claim_type_staleness:
  personal_preference: null
  household_note: 365
```

## Domain selection rules
The system should select a domain using deterministic hints first:

- User-selected domain overrides automatic detection.
- Document folder/profile metadata overrides content guess.
- Claim type may imply domain.
- LLM classification may suggest a domain, but deterministic config should decide final policy.

## Required behavior
- Unknown domains use `general_business` or `default` with conservative staleness.
- High-risk domains such as `medical`, `legal`, and `finance` require extra warnings and usually manual approval.
- Domain profiles should be data files, not hardcoded throughout the app.

## First implementation recommendation
Start with only:

- `it_software.yaml`
- `general_business.yaml`
- `default.yaml`

Add legal/medical/finance profiles after the core policy engine and tests are stable.
