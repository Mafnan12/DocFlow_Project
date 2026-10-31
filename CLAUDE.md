# CLAUDE.md / AI Coding Assistant Operating Instructions

You are helping build **DocFlow**, a multimodal invoice and receipt processing agent for a portfolio project.
Owner: Muhammad Afnan, BS Artificial Intelligence, FAST-NUCES.

Single source of truth: `DocFlow_Project_Spec.md` (or `docs/PROJECT_SPEC.md`).

## The Six Unbreakable Rules

1. **I must understand everything.** I will be interviewed on this project for 20 to 30 minutes. Write simple, readable code. Explain what you do and why. Work in small steps. If you introduce a concept or library I may not know, explain it briefly.
2. **Zero cost.** Only free tiers, free datasets, and local open-source models. Never add a paid service. Ask before adding any new external service or dependency.
3. **Never fabricate results.** Every number in `RESULTS.md` or the README must come from actually running the evaluation scripts. Use placeholders like `[X]` until then.
4. **Never hardcode secrets.** Use environment variables. Keep `.env.example` updated.
5. **Money is `Decimal`, validation is code.** Amounts are parsed and compared with `Decimal` in deterministic, unit-tested Python. The LLM reads documents; code checks the arithmetic and decides confidence and routing.
6. **Never tune on the test set.** Prompts, thresholds, and confidence weights are tuned on the **dev** split only. The **test** split is used only for final reported numbers.

## Assistant Workflow
- Work on one ticket at a time.
- Before coding, explain the approach and list the files you'll change.
- After finishing, run the project's tests, summarize what was built, and provide 3 interview questions about it.
- If anything is unclear or a decision would significantly affect architecture, cost, or accuracy methodology, ask instead of guessing.
