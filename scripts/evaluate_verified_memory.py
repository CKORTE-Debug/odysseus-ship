"""Small, synthetic retrieval regression benchmark; no model or network calls.

The reserved subset is separately reported, not an independently authored or
statistically representative benchmark. This measures source retrieval and
integrity, not answer correctness, semantic entailment or model abstention.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from verified_memory.contracts.project_contract import (
    EvidenceQuery,
    RequestScope,
    SourceInput,
)
from verified_memory.service import VerifiedMemoryWorkspace


def evaluate() -> dict:
    cases = json.loads((ROOT / 'benchmarks/verified_memory_cases.json').read_text())
    sources = json.loads((ROOT / 'benchmarks/verified_memory_sources.json').read_text())
    results = []
    with tempfile.TemporaryDirectory() as directory:
        service = VerifiedMemoryWorkspace(directory).create_project(RequestScope('benchmark', 'synthetic'))
        for source in sources:
            service.register_source(SourceInput(**source))
        for case in cases:
            bundle = service.query_evidence(EvidenceQuery(case['question'], limit=5, as_of=case['as_of']))
            if case['expected_source'] is None:
                correct = not bundle.passages
            else:
                correct = any(p.source.source_key == case['expected_source'] for p in bundle.passages)
            integrity = all(
                p.text == '\n'.join(p.source.text.splitlines()[p.line_start - 1:p.line_end])
                and hashlib.sha256(p.source.text.encode()).hexdigest() == p.source.content_sha256
                for p in bundle.passages
            )
            # The correction fixture must return the appropriate revision,
            # not just another passage bearing the same filename.
            if case['expected_source'] == 'architecture.md':
                expected = 'is allowed' if case['as_of'] else 'is prohibited'
                correct = correct and any(expected in p.text for p in bundle.passages if p.source.source_key == 'architecture.md')
            results.append({**case, 'passed': bool(correct and integrity), 'integrity': integrity})
    summary = {}
    for split in ('development', 'reserved'):
        subset = [r for r in results if r['split'] == split]
        answerable = [r for r in subset if r['expected_source'] is not None]
        summary[split] = {
            'cases': len(subset), 'passed': sum(r['passed'] for r in subset),
            'supporting_source_recall_at_5': sum(r['passed'] for r in answerable) / len(answerable),
        }
    critical = [r for r in results if r['critical']]
    gates = all(r['passed'] for r in critical) and all(v['supporting_source_recall_at_5'] >= .90 for v in summary.values())
    return {
        'summary': summary, 'critical_passed': sum(r['passed'] for r in critical),
        'critical_total': len(critical), 'source_integrity_passed': all(r['integrity'] for r in results),
        'gates_passed': gates, 'failures': [r['id'] for r in results if not r['passed']],
        'measures': 'synthetic source retrieval only; no answer generation or independent holdout',
    }


if __name__ == '__main__':
    report = evaluate()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['gates_passed'] else 1)
