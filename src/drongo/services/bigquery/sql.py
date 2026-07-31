"""Execute BigQuery SQL against the in-memory tables using DuckDB.

BigQuery's own SQL engine is not something drongo can reproduce, so query
execution is opt-in: ``pip install "drongo[bigquery]"`` pulls in DuckDB (the
execution engine), sqlglot (a SQL transpiler), and pytz (for timestamp
handling).

sqlglot is used for everything dialect-shaped, so nothing is hand-guessed:

* the query is parsed in the BigQuery dialect and rewritten for DuckDB, which
  covers backtick identifiers, ``SELECT * EXCEPT(...)``, ``SAFE_DIVIDE``,
  ``FORMAT_TIMESTAMP`` and friends, and BigQuery's ``NULLS FIRST`` ordering;
* table references are repointed at the loaded tables structurally, on the AST,
  rather than by string replacement;
* each table's schema is turned into a BigQuery ``CREATE TABLE`` and transpiled
  to DuckDB, so column types (including ``REPEATED`` arrays and ``RECORD``
  structs) come from the same transpiler as the query;
* result column types are mapped back to BigQuery types via sqlglot's type
  system.

DuckDB then runs a large subset of GoogleSQL (joins, aggregates, window
functions, most scalar functions) over the tables you have seeded. This is a
large common subset, not a perfect reproduction: a BigQuery-only function with
no DuckDB equivalent may still differ. Values come back typed, which is what
lets a test catch a real SQL bug instead of just a Python one.
"""

from __future__ import annotations

import json
from typing import Any

from drongo.core import exceptions

# BigQuery legacy type names -> their standard-SQL equivalents, so a bare
# INTEGER/FLOAT keeps BigQuery's 64-bit width when transpiled (sqlglot would
# otherwise read them as 32-bit INT/REAL). GEOGRAPHY has no DuckDB type, so it
# is stored as text.
_BQ_STANDARD = {
    "INTEGER": "INT64",
    "FLOAT": "FLOAT64",
    "BOOLEAN": "BOOL",
    "GEOGRAPHY": "STRING",
}


def run_query(
    backend: Any, sql: str
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Run ``sql`` against ``backend``'s tables; return (schema fields, rows)."""
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - exercised without the extra
        raise exceptions.bad_request(
            "BigQuery SQL execution needs the optional extra. Install it with: "
            "pip install 'drongo[bigquery]'"
        ) from exc

    con = duckdb.connect(":memory:")
    con.execute("SET TimeZone='UTC'")  # deterministic, UTC-aware timestamps
    try:
        references = _load_tables(con, backend)
        cursor = con.execute(_rewrite(sql, references))
        columns = [d[0] for d in cursor.description]
        types = [str(d[1]) for d in cursor.description]
        data = cursor.fetchall()
    except exceptions.DrongoHttpError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface engine errors as a 400
        raise exceptions.bad_request(f"Query failed: {exc}")
    finally:
        con.close()

    schema = [
        {"name": c, "type": _result_type(t)}
        for c, t in zip(columns, types, strict=True)
    ]
    rows = [dict(zip(columns, row, strict=True)) for row in data]
    return schema, rows


# -- loading tables --------------------------------------------------------


def _load_tables(con: Any, backend: Any) -> dict[tuple[str, str], str]:
    """Create a DuckDB table per in-memory table; return (dataset, table) -> name.

    Backends are per-project, so ``(dataset_id, table_id)`` uniquely identifies a
    table and we can ignore the project part of a reference when repointing.
    """
    references: dict[tuple[str, str], str] = {}
    counter = 0
    for dataset in backend.datasets.values():
        for table in dataset.tables.values():
            counter += 1
            name = f"_drongo_t{counter}"
            schema = table.schema or [
                {"name": key, "type": "STRING"}
                for key in (table.rows[0] if table.rows else {})
            ]
            _load_one(con, name, schema, table.rows)
            references[(table.dataset_id, table.table_id)] = name
    return references


def _load_one(con: Any, name: str, schema: list[dict], rows: list[dict]) -> None:
    """Load one table with real column types. If DuckDB can't build the schema
    or a value won't fit its column, rebuild the whole table as all-VARCHAR
    rather than failing the query."""
    if not schema:
        con.execute(f'CREATE TABLE "{name}" ("_" VARCHAR)')
        return
    try:
        con.execute(_create_ddl(name, schema))
        _fill(con, name, schema, rows, typed=True)
    except Exception:  # noqa: BLE001 - degrade to text instead of crashing
        con.execute(f'DROP TABLE IF EXISTS "{name}"')
        cols = ", ".join(f'"{f["name"]}" VARCHAR' for f in schema)
        con.execute(f'CREATE TABLE "{name}" ({cols})')
        _fill(con, name, schema, rows, typed=False)


def _create_ddl(name: str, schema: list[dict]) -> str:
    """DuckDB ``CREATE TABLE``, transpiled from a BigQuery one via sqlglot."""
    import sqlglot

    cols = ", ".join(f"`{f['name']}` {_bq_column_type(f)}" for f in schema)
    return sqlglot.transpile(
        f"CREATE TABLE `{name}` ({cols})", read="bigquery", write="duckdb"
    )[0]


def _bq_column_type(field: dict) -> str:
    """The GoogleSQL type for a schema field (recursing into structs/arrays)."""
    bq_type = (field.get("type") or "STRING").upper()
    if bq_type in ("RECORD", "STRUCT"):
        inner = ", ".join(
            f"`{f['name']}` {_bq_column_type(f)}" for f in field.get("fields", [])
        )
        base = f"STRUCT<{inner}>"
    else:
        base = _BQ_STANDARD.get(bq_type, bq_type)
    if (field.get("mode") or "").upper() == "REPEATED":
        return f"ARRAY<{base}>"
    return base


def _fill(
    con: Any, name: str, schema: list[dict], rows: list[dict], *, typed: bool
) -> None:
    if not rows:
        return
    field_names = [f["name"] for f in schema]
    placeholders = ", ".join(["?"] * len(field_names))
    con.executemany(
        f'INSERT INTO "{name}" VALUES ({placeholders})',
        [[_coerce(row.get(f), typed) for f in field_names] for row in rows],
    )


def _coerce(value: Any, typed: bool) -> Any:
    if typed:
        return value  # DuckDB maps native Python (incl. list/dict) to the column
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)  # all-VARCHAR fallback: everything becomes text


# -- rewriting the query ---------------------------------------------------


def _rewrite(sql: str, references: dict[tuple[str, str], str]) -> str:
    """Transpile BigQuery SQL to DuckDB and repoint tables at the loaded ones."""
    import sqlglot
    from sqlglot import expressions as exp

    try:
        tree = sqlglot.parse_one(sql, read="bigquery")
    except Exception:  # noqa: BLE001 - unparseable: fall back to raw string swap
        return _rewrite_by_string(sql, references)

    for tbl in tree.find_all(exp.Table):
        name = references.get((tbl.db, tbl.name)) or references.get(("", tbl.name))
        if name:
            tbl.set("catalog", None)
            tbl.set("db", None)
            tbl.set("this", exp.to_identifier(name))
    return tree.sql(dialect="duckdb")


def _rewrite_by_string(sql: str, references: dict[tuple[str, str], str]) -> str:
    """Last-resort table repointing when the query will not parse."""
    forms: dict[str, str] = {}
    for (dataset, table), name in references.items():
        ref = f"{dataset}.{table}"
        forms[f"`{ref}`"] = name
        forms[ref] = name
    for form in sorted(forms, key=len, reverse=True):
        sql = sql.replace(form, forms[form])
    return sql


# -- result types ----------------------------------------------------------


def _result_type(duckdb_type: str) -> str:
    """Map a DuckDB result column type back to a BigQuery type via sqlglot."""
    from sqlglot import expressions as exp

    try:
        enum = exp.DataType.build(duckdb_type, dialect="duckdb").this
    except Exception:  # noqa: BLE001 - unknown type: treat as a string column
        return "STRING"
    return _ENUM_TO_BQ.get(enum, "STRING")


def _build_enum_map() -> dict:
    """sqlglot ``DataType.Type`` member -> BigQuery type, skipping members that
    a given sqlglot version may not define."""
    from sqlglot import expressions as exp

    kind = exp.DataType.Type
    groups = {
        "INTEGER": (
            "BIGINT",
            "INT",
            "SMALLINT",
            "TINYINT",
            "HUGEINT",
            "UBIGINT",
            "INT128",
            "INT256",
        ),
        "FLOAT": ("DOUBLE", "FLOAT", "REAL"),
        "NUMERIC": ("DECIMAL",),
        "BIGNUMERIC": ("BIGDECIMAL",),
        "BOOLEAN": ("BOOLEAN",),
        "STRING": ("VARCHAR", "TEXT", "CHAR", "NVARCHAR", "NCHAR"),
        "BYTES": ("BINARY", "VARBINARY", "BLOB", "BYTEA"),
        "TIMESTAMP": ("TIMESTAMPTZ", "TIMESTAMPLTZ"),
        "DATETIME": ("TIMESTAMP", "DATETIME"),
        "DATE": ("DATE",),
        "TIME": ("TIME",),
        "JSON": ("JSON",),
    }
    mapping = {}
    for bq_type, members in groups.items():
        for member in members:
            enum = getattr(kind, member, None)
            if enum is not None:
                mapping[enum] = bq_type
    return mapping


try:
    _ENUM_TO_BQ = _build_enum_map()
except Exception:  # noqa: BLE001 - sqlglot missing; run_query raises first anyway
    _ENUM_TO_BQ = {}
