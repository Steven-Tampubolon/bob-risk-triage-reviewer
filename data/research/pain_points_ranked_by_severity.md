**Pain Points Ranked from Largest to Smallest**

| Pain Area | Severity / Scale | Interpretation |
| :---- | :---- | :---- |
| Finding information, documentation, system context, and ownership | Ranked #1 source of friction in Atlassian's survey | This is the most widespread pain in team workflows: developers do not know which service, which API, where the latest documentation is, or who owns a component. [dam-cdn.atl.orangelogic](https://dam-cdn.atl.orangelogic.com/AssetLink/5yt05dl5q8s1xljrs8747h8x6240c32p.pdf) |
| Organizational inefficiency and context switching | 50% lose 10+ hours/week; 90% lose 6+ hours/week | This includes fragmented tools, unclear requirements, cross-team handoffs, access, approvals, and context searching. [dam-cdn.atl.orangelogic](https://dam-cdn.atl.orangelogic.com/AssetLink/5yt05dl5q8s1xljrs8747h8x6240c32p.pdf) |
| AI code verification | 95% spend effort reviewing/testing/correcting AI output; 59% rate the effort as moderate or substantial | This is a very real, emerging pain point for teams heavily adopting AI for coding. [sonarsource](https://www.sonarsource.com/state-of-code-developer-survey-report.pdf) |
| Trust gap | 96% do not fully trust AI code to be correct; only 48% always check before committing | There is a **48 percentage point gap** between distrust and consistent verification discipline. This creates quality, security, and technical debt risks. [sonarsource](https://www.sonarsource.com/state-of-code-developer-survey-report.pdf) |
| AI security and governance | 57% are very/moderately concerned about corporate/customer data exposure; 35% access AI tools via personal accounts | This is more dominant in enterprise organizations or regulated domains. [sonarsource](https://www.sonarsource.com/state-of-code-developer-survey-report.pdf) |
| Toil and maintenance | Average 24% of the work week is spent on toil | AI does not automatically eliminate toil; it shifts it—including toward correcting/rewriting AI output and managing technical debt. [sonarsource](https://www.sonarsource.com/state-of-code-developer-survey-report.pdf) |

**Assessment:**

1. For overall team application development workflows, the most widespread pain point is a **lack of context and self-service access to information**: documentation, architecture decisions, service ownership, API contracts, dependencies, requirements, and deployment status.  
2. For teams with high AI adoption, the most acute pain point is **verification debt**: the faster code is generated, the greater the burden to prove that the code is correct, secure, compliant with design, and not adding technical debt.  
3. LinearB's review bottleneck is primarily **the queue wait time before review begins**. This means buying or adding an AI code-review bot alone will not necessarily solve the issue; while a bot might assist with initial checks, reviewer allocation, routing, ownership, and prioritization issues still need to be addressed. [linearb](https://linearb.io/resources/software-engineering-benchmarks-report)

There is also a crucial paradox: Atlassian found that 68% of developers report saving more than 10 hours per week using AI, yet 50% still lose more than 10 hours per week to organizational inefficiencies. These two facts are not mutually exclusive: AI can speed up individual tasks while team-level working systems remain slow. [dam-cdn.atl.orangelogic](https://dam-cdn.atl.orangelogic.com/AssetLink/5yt05dl5q8s1xljrs8747h8x6240c32p.pdf)
