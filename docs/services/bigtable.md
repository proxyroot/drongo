# Bigtable

- **Client:** `google-cloud-bigtable` (`bigtable.Client`)
- **Transport:** gRPC. The client connects insecurely when
  `BIGTABLE_EMULATOR_HOST` is set, so drongo runs an in-process gRPC emulator and
  points the client at it via that env var.
- **Backend:** per-project.

Use the normal client with `admin=True`. One emulator serves both the table-admin
API and the data API.

## Tables and column families

```python
from drongo import mock_gcp


@mock_gcp
def test_tables():
    from google.cloud import bigtable
    from google.cloud.bigtable import column_family

    client = bigtable.Client(project="p", admin=True)
    table = client.instance("inst").table("users")
    table.create(column_families={"cf": column_family.MaxVersionsGCRule(3)})

    assert table.exists()
    assert [t.table_id for t in client.instance("inst").list_tables()] == ["users"]
```

## Rows: write and read

```python
@mock_gcp
def test_rows():
    from google.cloud import bigtable
    from google.cloud.bigtable import column_family

    client = bigtable.Client(project="p", admin=True)
    table = client.instance("inst").table("users")
    table.create(column_families={"cf": column_family.MaxVersionsGCRule(3)})

    row = table.direct_row(b"user#1")
    row.set_cell("cf", b"name", b"Alice")
    row.commit()

    read = table.read_row(b"user#1")
    assert read.cells["cf"][b"name"][0].value == b"Alice"
    assert table.read_row(b"user#404") is None
```

Cells are versioned (newest first). Deletes work at cell, column-family, and row
level (`delete_cell`, `delete_cells`, `row.delete()`).

## Scans

`read_rows` supports key ranges and limits:

```python
@mock_gcp
def test_scan():
    from google.cloud import bigtable
    from google.cloud.bigtable import column_family

    client = bigtable.Client(project="p", admin=True)
    table = client.instance("inst").table("t")
    table.create(column_families={"cf": column_family.MaxVersionsGCRule(1)})
    for key in [b"a", b"b", b"c", b"d"]:
        r = table.direct_row(key)
        r.set_cell("cf", b"v", key)
        r.commit()

    rows = table.read_rows(start_key=b"b", end_key=b"d")  # end exclusive
    assert [r.row_key for r in rows] == [b"b", b"c"]
```

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list / delete table | Supported |
| Modify column families | Supported |
| `set_cell`, versioned cells | Supported |
| Delete cell / family / row | Supported |
| `read_row`, `read_rows` (ranges, limit) | Supported |
| Batch `mutate_rows`, `sample_row_keys` | Supported |
| Read filters (column/cell filters) | Planned |
| `check_and_mutate_row`, `read_modify_write_row` | Planned |
| Instance admin, change streams, aggregations | Planned |
