# Equal Start — Evaluation Summary

**Evaluation date:** November 4, 2026 (US Central)
**Model:** Nebius GLM-5.3-Flash
**Evaluation framework:** Equal Start custom Python evaluation runner
**Dataset:** 2026-11-02-v1, expanded locally with six new cases

## 1. Objective

Evaluate the correctness and reliability of Equal Start's Discovery, Evidence, Fit, and Planning agents using manually labeled synthetic scenarios.

## 2. Evaluation Coverage

The original evaluation dataset contained 32 cases. Six additional cases were introduced to challenge the agents on financial accessibility, conflicting funding information, transfer eligibility uncertainty, semantic relevance, and application prerequisites.

| Agent | Original cases | New cases | Total |
|---|---:|---:|---:|
| Discovery | 8 | 1 | 9 |
| Evidence | 8 | 2 | 10 |
| Fit | 8 | 2 | 10 |
| Planning | 8 | 1 | 9 |
| **Total** | **32** | **6** | **38** |

## 3. Evaluation Results

| Agent | Baseline pass rate | Nebius pass rate |
|---|---:|---:|
| Discovery | 11.1% | 100% |
| Evidence | 30.0% | 100% |
| Fit | 30.0% | 100% |
| Planning | 44.4% | 100% |
| **Overall** | **28.9%** | **100%** |

**Live evaluation:** 38/38 cases passed.

**Contract validity:** 100%.

**Model calls:** 34.

**Estimated evaluation cost:** $0.002064.

All four agents satisfied the evaluation runner's existing release gates.

## 4. New Evaluation Scenarios

| Case | Scenario | Outcome |
|---|---|---|
| D09 | Funded summer research versus superficial keyword matches | Pass |
| E09 | Contradictory scholarship funding conditions | Pass |
| E10 | Uncertain transfer-student eligibility | Pass |
| F09 | Financial accessibility versus higher stipend | Pass |
| F10 | Housing and upfront travel-cost constraints | Pass |
| P09 | Multi-step application prerequisites | Pass |

The actual outputs of all six new cases were inspected and matched their manually authored labels.

## 5. Regression Testing

The project test suite completed successfully with **74/74 tests passing**.

Existing tests were updated to accommodate evaluation dataset expansion without weakening their case-accounting checks.

Nebius live inference and Fireworks configuration compatibility were also verified. Fireworks live inference was not tested.

## 6. Limitations

- All evaluation scenarios are synthetic. They do not measure accuracy against real scholarship provider websites.
- The six new cases were manually authored and reviewed during development, but have not undergone independent external annotation.
- The expanded dataset was evaluated in one live repetition; repeatability and output stability were not assessed for the expanded suite.
- Agent-level correctness does not establish end-to-end workflow reliability.
- Evidence evaluation checks uncertainty and conflicts within supplied summaries, not factual entailment against primary sources.
- The baseline represents simple deterministic behavior, not a competing LLM.

## 7. Recommended Future Work

Expand independently reviewed holdout cases, evaluate grounding against primary sources, test full student journeys, and add realistic failure scenarios covering incomplete profiles, eligibility restrictions, and changing scholarship conditions.

## Conclusion

Nebius GLM-5.3-Flash passed all 38 existing and expanded synthetic evaluation cases in the recorded live run. The additional cases strengthen coverage of financial and eligibility considerations, but further independent and end-to-end evaluation is needed before making real-world accuracy claims.