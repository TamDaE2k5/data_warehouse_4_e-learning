"""Targeted regression: subtotal NULL semantics must match across engines."""

from benchmark.queries import QUERIES
from benchmark.run_benchmark import canonical
from etl.common import ch_connect, pg_connect

ch = ch_connect()
with pg_connect() as pg, pg.cursor() as cur:
    sql = QUERIES["Q5_cube"]
    cur.execute(sql.format(db="benchmark"))
    pg_rows = cur.fetchall()
    ch_rows = ch.query(sql.format(db="gold"), settings={"group_by_use_nulls": 1}).result_rows
    assert canonical(pg_rows) == canonical(ch_rows), (canonical(pg_rows), canonical(ch_rows))
    assert sum(r[0] is None and r[1] is None for r in ch_rows) == 1
    print(f"CUBE parity passed: {len(ch_rows)} rows including NULL subtotals")
ch.close()
