# sqlite_dbpage equality: false matches and missed matches

Reproduced the [original report](https://sqlite.org/bugs/forumpost/56594be107) on **`62cf9fb51a6ac16a`** (SQLite 3.55.0), using Apple clang 21 on macOS ARM64.

**Additional finding:** `pgno='0.2e1'` and `pgno='20e-1'` miss page 2, although both numeric strings compare equal to integer 2. Clearing the equality constraint's `omit` flag alone still misses these rows. An experimental build of that incomplete fix confirmed this.

The [small source patch](candidate.patch) applies numeric affinity before selecting the candidate page, then lets SQLite perform the final comparison. The direct page lookup is retained. [Regression tests](dbpagecmp.test) cover explicitly bound types and reused statements, `pgno`/`rowid`, `IN`, and update selection.

| Check | Original revision | Candidate |
|---|---:|---:|
| New regression file | [30 failures / 67](results/baseline-dbpagecmp-test.txt) | [0 failures / 67](results/candidate-dbpagecmp-test.txt) |
| Existing `dbpage.test` | — | [0 failures / 34](results/dbpage-test.txt) |
| Existing `dbpagefault.test` | — | [0 failures / 813](results/dbpagefault-test.txt) |
| Differential comparisons with ordinary integer-key tables | [612 mismatches / 1,800](results/reported-validation.json) | [0 mismatches / 1,800](results/candidate-validation.json) |

The 612 mismatches are variants exercised by the harness, not 612 distinct bugs. These are recorded results from the original investigation. Host names and absolute binary paths were removed from the published receipts; numerical results are unchanged. Full source IDs, archive hash, compiler, and counts are in [provenance.json](provenance.json).

The following script demonstrates the missed matches on a fresh connection:

```sql
CREATE TABLE t1(x);
SELECT pgno FROM sqlite_dbpage WHERE pgno='0.2e1';
SELECT pgno FROM sqlite_dbpage WHERE pgno='20e-1';
```

Both queries should return 2; the unmodified revision returns no rows. The original examples `pgno=1.5`, `pgno='2abc'`, and `pgno=x'32'` return pages that do not satisfy equality. An `IN` list can also produce duplicate pages.

`dbpageBestIndex()` promises to enforce the equality condition by setting `omit=1`, while `dbpageFilter()` uses `sqlite3_value_int64()`. That conversion truncates real values and reads integer prefixes from text. It maps the two numeric strings above to 0 and 20 respectively. Applying numeric affinity first locates the correct candidate; retaining the core comparison rejects candidates that are not equal.

With raw-page writes explicitly enabled, the faulty condition also selects rows for `UPDATE`. No-op `SET data=data` tests inside rolled-back transactions confirm that `pgno=1.5` selects one page instead of zero. This is evidence of incorrect selection, not observed corruption or a defensive-mode bypass. The candidate corrects that selection.

The candidate is a proof of concept with focused validation. Full release qualification and other platforms/configurations have not been tested. The related `generate_series` correction has different affinity rules: its output column has no affinity, while `pgno` has INTEGER affinity. Rejecting all text operands would be wrong here.

To reproduce, start in this case directory with a C toolchain, make, Tcl development libraries, Python 3, curl, tar, and patch installed. Use a fresh build directory:

```sh
packet_dir=$(pwd)
work_dir=$(mktemp -d)
cd "$work_dir"
curl --fail --location --output sqlite.tar.gz \
  https://sqlite.org/src/tarball/62cf9fb51a6ac16a7d5c9b27aa905e110f48bd3d186440c9be5cc029e68aae6e/sqlite.tar.gz
mkdir reported-src
tar -xzf sqlite.tar.gz -C reported-src --strip-components=1
cp -R reported-src candidate-src
patch -p1 -d candidate-src < "$packet_dir/candidate.patch"
cp "$packet_dir/dbpagecmp.test" reported-src/test/
cp "$packet_dir/dbpagecmp.test" candidate-src/test/
mkdir reported-build candidate-build
(cd reported-build && ../reported-src/configure && make -j4 sqlite3 testfixture)
(cd candidate-build && ../candidate-src/configure && make -j4 sqlite3 testfixture)
cp "$packet_dir/validate.py" "$packet_dir/matrix-values.json" .
python3 validate.py reported candidate
```

On the original Mac, the testfixture link additionally needed `LDFLAGS.configure=-L/opt/homebrew/opt/libtommath/lib` on the make command. That flag is specific to the installed Homebrew Tcl dependencies.

The differential harness runs both known-bad and candidate binaries, so it prints mismatch counts without treating baseline mismatches as a shell failure. Check that it reports 1,800 completed comparisons, 612 baseline mismatches, and zero candidate mismatches. It writes fresh JSON receipts in the build directory.

Then run the Tcl tests. The first invocation is expected to exit nonzero with 30 failures. The three candidate invocations should report zero errors:

```sh
(cd reported-build && ./testfixture ../reported-src/test/dbpagecmp.test)
(cd candidate-build && ./testfixture ../candidate-src/test/dbpagecmp.test)
(cd candidate-build && ./testfixture ../candidate-src/test/dbpage.test)
(cd candidate-build && ./testfixture ../candidate-src/test/dbpagefault.test)
```

Investigation, candidate, and test harness were developed with an AI assistant. All reported execution results came from actual local builds. Nothing here claims upstream acceptance.
