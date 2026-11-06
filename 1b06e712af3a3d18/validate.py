#!/usr/bin/env python3
"""Compare affected plans with a MATERIALIZED-VALUES oracle."""
import json
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parent
values_sets = [
    "(1),(2)",
    "(1),(2),(3)",
    "(3),(1),(4),(2)",
]
unions = [
    "SELECT a FROM tpk UNION ALL SELECT a FROM t2",
    "SELECT a FROM t2 UNION ALL SELECT a FROM tpk",
    "SELECT a FROM tpk UNION ALL SELECT a FROM tidx",
    "SELECT a FROM tpk UNION ALL SELECT a FROM t2 UNION ALL SELECT a FROM tplain",
    "SELECT a FROM tplain UNION ALL SELECT a FROM t2",
]
orderings = ["1,2", "1 DESC,2 DESC", "2,1"]
wrappers = [
    "(VALUES {values})",
    "(SELECT * FROM (VALUES {values}) LIMIT -1)",
    "(SELECT * FROM (SELECT * FROM (VALUES {values}) LIMIT -1) LIMIT -1)",
]

setup = """
.bail on
.headers off
.mode list
CREATE TABLE tpk(a INTEGER PRIMARY KEY);
CREATE TABLE tplain(a INT);
CREATE TABLE t2(a INT);
CREATE TABLE tidx(a INT);
CREATE INDEX tidx_a ON tidx(a);
INSERT INTO tpk VALUES(1),(2),(3);
INSERT INTO tplain VALUES(1),(2),(3);
INSERT INTO t2 VALUES(1),(5);
INSERT INTO tidx VALUES(1),(2),(3);
"""
cases = []
statements = [setup]
case_id = 0
for values in values_sets:
    for union in unions:
        for wrapper in wrappers:
            for reverse in (False, True):
                for order_by in orderings:
                    for use_where in (False, True):
                        q0 = wrapper.format(values=values) + " AS q0"
                        q1 = "(" + union + ") AS q1"
                        sources = q1 + "," + q0 if reverse else q0 + "," + q1
                        where = " WHERE q0.column1>0" if use_where else ""
                        actual = (
                            "SELECT q1.a,q0.column1 FROM " + sources + where
                            + " ORDER BY " + order_by
                        )
                        oracle = (
                            "WITH q0(column1) AS MATERIALIZED (VALUES " + values + ") "
                            "SELECT q1.a,q0.column1 FROM q0," + q1 + where
                            + " ORDER BY " + order_by
                        )
                        statements.append(
                            "SELECT %d,(SELECT json_group_array(json_array(a,column1)) "
                            "FROM (%s)),(SELECT json_group_array(json_array(a,column1)) "
                            "FROM (%s));" % (case_id, actual, oracle)
                        )
                        cases.append({
                            "values": values,
                            "union": union,
                            "wrapper": wrapper,
                            "reverse": reverse,
                            "order_by": order_by,
                            "where": use_where,
                        })
                        case_id += 1

script = "\n".join(statements) + "\n"
(root / "validation.sql").write_text(script)
(root / "validation-cases.json").write_text(json.dumps(cases, indent=2) + "\n")

for label, binary in zip(sys.argv[1::2], sys.argv[2::2]):
    result = subprocess.run(
        [binary, "-batch", ":memory:"], input=script,
        text=True, capture_output=True,
    )
    failures = []
    checked = 0
    for line in result.stdout.splitlines():
        fields = line.split("|", 2)
        if len(fields) == 3 and fields[0].isdigit():
            checked += 1
            ident, actual, expected = fields
            if actual != expected:
                failures.append({
                    "case": int(ident),
                    "input": cases[int(ident)],
                    "actual": actual,
                    "expected": expected,
                })
    receipt = {
        "binary": binary,
        "exit": result.returncode,
        "expected_checks": len(cases),
        "checked": checked,
        "failures": failures,
        "stderr": result.stderr,
    }
    (root / (label + "-validation.json")).write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(label, "checked", checked, "of", len(cases),
          "mismatches", len(failures), "exit", result.returncode)
    for failure in failures[:5]:
        print(json.dumps(failure))
    if result.returncode or checked != len(cases):
        raise SystemExit("validation did not complete")
