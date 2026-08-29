**Feature Value Percentage**

| Bob's Feature | Percentage Claimable Now | Correct Meaning |
| :---- | :---- | :---- |
| Scope/blast-radius detector | Covers 35% of PRs | This group accounts for roughly 50% of total review wait time |
| Scope-aware priority queue | Theoretical maximum 23% reduction in mean wait time | Upper theoretical limit if multi-module delay drops to small/local PR levels |
| Security/policy routing | Covers 28% of PRs | Important as a guardrail; not yet proven to reduce review delay |
| Small/local fast-lane candidate | Maximum 65% of PRs by scope | Does not automatically mean 65% are safe for auto-merge |
| AI provenance classifier | 0% in sample | No explicit AI provenance detected across 100 PRs |
| Author-quality scoring | 0% validation value | Do not use in MVP |
| Evidence-gap detector | Not yet measured | Requires post-merge CI, test, scan, rework, and defect data |

**Bob's Experiment Targets**  
Use these as pilot targets, not current result claims:

| KPI | Current Baseline | Bob's Realistic Target |
| :---- | :---- | :---- |
| Mean first human review | 2.39 hours | 10–15% decrease |
| Mean multi-module review | 3.41 hours | 20–25% decrease |
| P90 multi-module review | 12.88 hours | 25–30% decrease |
| Human review coverage for high-risk | 100% | Remain 100% |
| High-risk PRs without relevant owner | Not yet measured | Near 0% |
| Fast-lane PRs with missing checks | Not yet measured | 0% |
| Reverts/defects on fast-lane PRs | Not yet measured | Must not increase compared to baseline |

**Bob's Strongest MVP Features are:**

1. Scope and blast-radius detection  
2. AI provenance detection  
3. Reviewer/code-owner routing  
4. Missing-evidence checklist  
5. Priority queue for complex and AI-explicit PRs  
6. Security/policy gate for sensitive PRs

**Features that do NOT need to be included in the MVP yet:**

* Auto-merge without human review  
* Quality scoring based on developer name  
* Claiming that security PRs are the main cause of review bottlenecks  
* Claiming that all AI PRs are inherently bad or slow

**Product Validation Conclusion**

The review delay problem certainly exists, but it is not distributed evenly across all pull requests. Review delays are heavily concentrated in PRs with large scopes, cross-module impacts, or—in the VS Code dataset—PRs with explicit AI provenance. Therefore, developers and maintainers need a system that helps prioritize complex PRs, clarify the blast radius, complete missing evidence, and route changes to the right reviewers.
