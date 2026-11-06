I independently reproduced this on both the exact reported revision (`62cf9fb51a6ac16`) and current trunk as checked today (`6107f5affe4f`). **Verdict: confirmed** — the query returns 13 rows rather than the expected 15.

The loss appears to come from compound flattening copying the outer multi-row `VALUES` source into each `UNION ALL` arm. Those copies share the same parser-generated coroutine state. The `ORDER BY` merge path interleaves the arms, so one arm can advance/reinitialize state used by the other. Reversing the `FROM` order and adding one or two wrapper subqueries still reproduce it, which rules out a direct-sibling-only guard.

A proof-of-concept guard that declines this specific flattening when an ordered compound has another coroutine-backed source fixes the report and a 540-case matrix:

- report: 13/15 -> 15/15 rows
- differential matrix: 216/540 mismatches -> 0/540
- focused regression: 7/10 failures -> 0/10 (release and debug)
- related suites: 38,624 checks, 0 failures
- allocation-resilience sweep: 231 checks, 0 failures
- veryquick: the same 140 baseline issues before and after; no new named failure

Reproducer analysis, candidate diff, regression test, exact provenance, and compact receipts:

https://github.com/lehenbauer/sqlite-investigations/tree/main/1b06e712af3a3d18

This is an independent proof of mechanism, not a request to accept the patch. I did not run the full release-test matrix, other platforms/compilers, sanitizers, or performance benchmarks.
