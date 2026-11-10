"""Explicit opt-in integration test against a disposable local Neo4j instance.

No credentials: launch a test DB with auth disabled and bound to 127.0.0.1 only.
Does not delete data; imported graph is namespaced by immutable dataset ID.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from neo4j import GraphDatabase
from baseball_graph import download_tables, prepare, import_graph, graph_query, sqlite_database, sql_query


def main():
    tables, _ = download_tables()
    data = prepare(tables)
    with GraphDatabase.driver("bolt://127.0.0.1:17687", auth=None) as driver:
        driver.verify_connectivity()
        first = import_graph(driver, data)
        second = import_graph(driver, data)
        assert first == second
        with sqlite_database(data) as db:
            for player in ["ohtansh01", "troutmi01", "suzukic01", "missing"]:
                for hops in (1, 2):
                    actual = graph_query(driver, data, player, hops)
                    assert actual == sql_query(db, player, hops), (player, hops)
        # A second dataset must neither overwrite nor leak into the first.
        small = prepare(tables, 2024, 2025)
        import_graph(driver, small)
        with sqlite_database(small) as db:
            assert graph_query(driver, small, "ohtansh01") == sql_query(db, "ohtansh01")
        with sqlite_database(data) as db:
            assert graph_query(driver, data, "ohtansh01") == sql_query(db, "ohtansh01")
        print("PASS: real-data import, rerun idempotency, 1/2-hop SQL parity, dataset isolation", first)


if __name__ == "__main__":
    main()
