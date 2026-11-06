# SQLite investigations

Reproducible, AI-assisted investigations of reported SQLite bugs. Each case includes a short explanation, a proof-of-concept change, regression coverage, and recorded results from actual builds.

| Forum report | Finding | Evidence |
|---|---|---|
| [56594be107](https://sqlite.org/bugs/forumpost/56594be107) | `sqlite_dbpage` equality can return incorrect pages and miss valid numeric-text matches. | [Investigation, patch, and tests](56594be107/) |

This is an independent collection. Candidates are for maintainer evaluation and have not undergone full SQLite release qualification. SQLite source revisions use the official Fossil check-in identifiers.
