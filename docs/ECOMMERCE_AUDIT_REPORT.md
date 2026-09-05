# E-commerce mission audit

## Test scope

Mission question:

> Decide whether retrieval augmented generation is reliable enough for an
> e-commerce product.

This is an offline deterministic test. It uses the repository's frozen raw
arXiv and GitHub RAG responses plus `MockLLMClient`; it does not claim to be a
fresh e-commerce literature search or a Gemini result. The purpose is to test
the result API and whether the audit layer reveals a poor evidence-to-decision
fit.

## Observed result

| Measure | Value |
| --- | ---: |
| Workflow status | completed |
| Re-search iterations | 0 |
| Retrieved sources | 8 |
| arXiv / GitHub | 6 / 2 |
| Support-eligible evidence | 2 / 8 |
| Challenge-eligible evidence | 5 / 8 |
| Challenge-only evidence | 3 / 8 |
| Fully excluded evidence | 3 / 8 |
| Independent effective sources | 2 |
| Result-bearing effective evidence | 0 |
| Limitation-bearing effective evidence | 2 |
| Claim verdicts | 0 supported, 0 contested, 2 unknown, 0 refuted |
| Opposing evidence | 0 |
| Highest candidate score | 10.0 / 100 |
| Workflow decision | proceed_with_poc |
| Audit status | needs_review |

The two effective sources were:

- `AR-RAG: Autoregressive Retrieval Augmentation for Image Generation`
- `Ragas: Automated Evaluation of Retrieval Augmented Generation`

Six sources failed the stricter support threshold for low relevance. Three of
them still contain a result or limitation and meet the challenge threshold, so
Critic and claim review may use them as challenge-only evidence. The other
three are fully excluded from both support and challenge use.

## Generated directions

The mock Analyst retained two PoC candidates, one derived from AR-RAG and one
from Ragas. Both had evidence coverage `0.4286`, one supporting source, no
opposing source, an `unknown` claim verdict, and PoC testability `0.8`.

The Decision stage selected the AR-RAG-derived direction. Both candidates
scored `10.0 / 100`; the deterministic tie order selected the first ranked
result.
The Action stage then generated a roughly three-day plan to test the unsettled
claim and its documented limitation.

## Audit findings

- `no_result_bearing_evidence`: neither eligible card records an experiment
  result in the structured evidence field.
- `all_claims_unknown`: no candidate claim reached supported, contested, or
  refuted.
- `no_counterevidence`: no opposing evidence ID was cited.

## Conclusion

The software path works and the audit now distinguishes support, challenge-only,
and fully excluded evidence, but this run is not sufficient evidence for an
e-commerce investment decision. The workflow decision and the audit conclusion
intentionally remain separate: the former currently chooses the best Phase C
candidate without a minimum score, while the audit correctly marks the output
`needs_review`.

A defensible live follow-up should search specifically for e-commerce retrieval
quality, conversion or support-resolution impact, latency and cost, privacy,
prompt injection, and controlled comparisons against non-RAG baselines. The
Decision stage should not automatically proceed on a `10.0 / 100` winner; a
minimum decision threshold is the next product rule to agree on rather than a
rule silently invented by this report endpoint.
