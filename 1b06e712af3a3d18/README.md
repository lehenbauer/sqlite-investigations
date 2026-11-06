# Ordered `UNION ALL` flattening can share a `VALUES` coroutine

**Verdict: confirmed.** The report's query returns 13 rows instead of 15 on both the reported revision and current trunk as checked on 2026-11-05. A narrow planner guard restores all 15 rows across the original case and a broader differential matrix.

- Forum report: [1b06e712af3a3d18](https://sqlite.org/bugs/forumpost/1b06e712af3a3d18)
- Reported source ID: `62cf9fb51a6ac16a7d5c9b27aa905e110f48bd3d186440c9be5cc029e68aae6e`
- Current trunk source ID tested: `6107f5affe4ff1cfa39689a899877301bdd9f8f210dd8e11bfb4a0f26ff681c1`

## Mechanism

`flattenSubquery()` distributes the outer query's other `FROM` terms into every arm of the compound subquery. A multi-row `VALUES` term is implemented as a parser-generated coroutine. Copying its `SrcItem` into multiple arms copies references to the same coroutine state; it does not create independently iterable state.

With `ORDER BY`, `multiSelectByMerge()` interleaves the compound arms. One arm advances the shared `VALUES` coroutine and the other reinitializes or consumes that same state. In the reported three-by-five Cartesian product, two rows disappear.

This is broader than the exact syntax in the report. Reversing the `FROM` order and wrapping the `VALUES` term in one or two subqueries still reproduce the loss. That is why a direct-sibling-only check is insufficient.

## Candidate change

[candidate.patch](candidate.patch) recursively checks the outer sibling source trees for an already-generated coroutine. It declines this compound flattening only when:

1. the compound query has `ORDER BY`; and
2. another outer source subtree contains a `viaCoroutine` source.

The no-`ORDER BY` plan remains unchanged. This is a proof-of-concept candidate for maintainer evaluation, not a proposed upstream contribution.

## Evidence

| Check | Unmodified | Candidate |
|---|---:|---:|
| Report query | 13 of 15 rows | 15 of 15 rows |
| Generated differential matrix | 216 mismatches / 540 | 0 mismatches / 540 |
| Focused regression file | 7 failing checks / 10 | 0 / 10, release and debug |
| Allocation-resilience sweep | — | 0 issues / 231 checks |
| Related compound/`VALUES` suites | — | 0 issues / 804 checks |
| `select1` through `selectH` | — | 0 issues / 37,820 checks |
| Veryquick suite | 140 issues / 334,161 | 140 issues / 334,172 |

The veryquick run has the same 44 named failures in both builds; these are existing environment/baseline failures. The candidate adds 11 checks and introduces no new named failure.

The matrix varies `VALUES` cardinality, compound shape, wrapper depth, source order, ordering direction/key, predicates, and indexed/plain source tables. Its oracle forces materialization of the compound source.

Files:

- [unionall3.test](unionall3.test) — ten focused regression checks
- [validate.py](validate.py) — 540-case differential harness
- [results.json](results.json) — compact test receipt
- [provenance.json](provenance.json) — exact source and artifact identifiers

Run the matrix with label/binary pairs, for example:

```sh
python3 validate.py baseline /path/to/unmodified/sqlite3 candidate /path/to/candidate/sqlite3
```

## Scope not covered

This was tested on macOS/arm64. I did not run SQLite's full release-test configuration matrix, other operating systems or compilers, sanitizer builds, or a performance benchmark. One omit-feature configuration fails identically before and after the change; the supported omit-view build succeeds with the candidate.
