#!/usr/bin/env python3
"""Compare dbpage equality selection with real INTEGER PRIMARY KEY tables."""
import json
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parent
values = json.loads((root / 'matrix-values.json').read_text())
values += ["'0.1e1'", "'30e-1'", "'3e1'", "'3.0e+1'", "'3.1e1'",
           "'1e100'", "'1e-100'", "'1e+'", "'1e'", "'NaN'", "'Inf'",
           "x'31'", "x'312e30'", "x''", "'1\\n'", "'1'||char(10)",
           '1e100', '-1e100', '1e-100', '1.9999999999999998',
           '2.0000000000000004', '3.0000000000000004',
           '9223372036854775808', '-9223372036854775808',
           "'4294967297'", "'1.0000000000000001'", "'2.000000000000001'"]
for n in (1, 2, 3, 9, 20, 40, 100):
    values.extend([str(n), f"'{n}'", f"'{n}.0'", f"'{n * 10}e-1'",
                   f"'0.{n}e{len(str(n))}'", f"'{n}x'", str(n + 0.5)])
values = list(dict.fromkeys(values))

sql = ['.bail on', '.headers off', '.mode list', '.dbconfig defensive off',
       'PRAGMA page_size=512;', 'CREATE TABLE t1(x);',
       'WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<40) '
       'INSERT INTO t1 SELECT zeroblob(700) FROM n;',
       "ATTACH ':memory:' AS aux;", 'CREATE TABLE aux.t2(x);',
       'CREATE TEMP TABLE p(pgno INTEGER PRIMARY KEY);',
       'INSERT INTO p SELECT pgno FROM sqlite_dbpage;',
       'CREATE TEMP TABLE paux(pgno INTEGER PRIMARY KEY);',
       "INSERT INTO paux SELECT pgno FROM sqlite_dbpage('aux');"]
cases = []

def add(actual, expected, description):
    ident = len(cases)
    cases.append(description)
    sql.append(f"SELECT {ident},({actual}),({expected});")

def rows(table, predicate):
    return f'SELECT json_group_array(pgno) FROM (SELECT pgno FROM {table} WHERE {predicate} ORDER BY pgno)'

for value in values:
    for column in ('pgno', 'rowid'):
        for predicate in (f'{column}={value}', f'{value}={column}',
                          f'{column} IN ({value},NULL)',
                          f'{column}={value} AND {column}>=1',
                          f'{column}>={value}', f'{column} IS {value}'):
            add(rows('sqlite_dbpage', predicate), rows('p', predicate), predicate)
        predicate = f'{column}={value}'
        add(rows("sqlite_dbpage('aux')", predicate), rows('paux', predicate), 'aux '+predicate)
        add(rows('sqlite_dbpage', "schema='main' AND "+predicate), rows('p', predicate), 'schema '+predicate)
        sql.append('BEGIN;')
        sql.append(f'UPDATE sqlite_dbpage SET data=data WHERE {predicate};')
        add('SELECT changes()', f'SELECT count(*) FROM p WHERE {predicate}', 'UPDATE '+predicate)
        sql.append('ROLLBACK;')
    predicate = f'pgno IN ({value},1.5,2,2,NULL)'
    add(rows('sqlite_dbpage', predicate), rows('p', predicate), predicate)

for affinity in ('TEXT', 'NUMERIC', 'BLOB'):
    sql.append(f'CREATE TEMP TABLE rhs_{affinity}(id INTEGER PRIMARY KEY,v {affinity});')
    for i, value in enumerate(values):
        sql.append(f'INSERT INTO rhs_{affinity} VALUES({i},{value});')
    for column in ('pgno', 'rowid'):
        for join in ('CROSS JOIN', 'LEFT JOIN'):
            def joined(table):
                return (f'SELECT json_group_array(json_array(id,pgno)) FROM '
                        f'(SELECT r.id,d.pgno FROM rhs_{affinity} r {join} {table} d '
                        f'ON d.{column}=r.v ORDER BY r.id,d.pgno)')
            add(joined('sqlite_dbpage'), joined('p'), f'{affinity} {join} {column}')

add('SELECT count(*) FROM sqlite_dbpage', 'SELECT count(*) FROM p', 'page count')
add('SELECT integrity_check FROM pragma_integrity_check', "SELECT 'ok'", 'integrity')
script = '\n'.join(sql)+'\n'
(root / 'validation.sql').write_text(script)
(root / 'validation-cases.json').write_text(json.dumps(cases, indent=2)+'\n')
for label in sys.argv[1:]:
    binary = root / f'{label}-build' / 'sqlite3'
    result = subprocess.run([str(binary), '--unsafe-testing', '-batch', ':memory:'],
                            input=script, text=True, capture_output=True)
    (root / f'{label}-validation.txt').write_text(result.stdout+result.stderr)
    failures = []
    checked = 0
    for line in result.stdout.splitlines():
        fields = line.split('|')
        if len(fields) == 3 and fields[0].isdigit():
            checked += 1
            ident, actual, expected = fields
            if actual != expected:
                failures.append({'case': cases[int(ident)], 'actual': actual, 'expected': expected})
    receipt = {'binary': str(binary), 'exit': result.returncode, 'expected_checks':len(cases),
               'checked':checked, 'failures':failures, 'stderr':result.stderr}
    (root / f'{label}-validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(label, 'checked',checked,'of',len(cases),'mismatches',len(failures),'exit',result.returncode)
    for failure in failures[:8]:
        print(json.dumps(failure))
    if result.returncode or checked != len(cases):
        raise SystemExit('Validation did not complete')
