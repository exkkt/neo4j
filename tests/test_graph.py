import json
from pathlib import Path

import pandas as pd
import pytest

from baseball_graph import (
    prepare, read_csv_bytes, roster_history, sqlite_database, sql_query,
    download_tables, measure,
)


@pytest.fixture
def tables():
    return {
        "People": pd.DataFrame([
            [p, p, "Player"] for p in "ABCDEZ"
        ], columns=["playerID", "nameFirst", "nameLast"]),
        "Teams": pd.DataFrame([
            [2022, "AL", "T", "Tokyo"], [2023, "AL", "T", "Tokyo"],
            [2023, "NL", "O", "Osaka"], [2022, "NL", "T", "Different league"],
        ], columns=["yearID", "lgID", "teamID", "name"]),
        "Appearances": pd.DataFrame([
            [2022, "T", "AL", "A", 10], [2022, "T", "AL", "B", 10],
            [2022, "T", "AL", "B", 10],  # duplicate row must not duplicate an edge
            [2023, "O", "NL", "B", 10], [2023, "O", "NL", "C", 10],
            [2023, "T", "AL", "D", 10],  # same team, different year
            [2022, "T", "NL", "E", 10],  # same team code/year, different league
            [2022, "T", "AL", "Z", 0],   # no appearance
        ], columns=["yearID", "teamID", "lgID", "playerID", "G_all"]),
    }


def test_temporal_league_separation_and_shortest_two_hop(tables):
    data = prepare(tables, 2022, 2023)
    assert len(data.memberships) == 6
    assert len(data.seasons) == 4
    assert "Z" not in set(data.players.playerID)
    with sqlite_database(data) as db:
        assert sql_query(db, "A") == ["B"]
        assert sql_query(db, "A", 2) == ["C"]
        assert sql_query(db, "B", 2) == []
        assert sql_query(db, "D") == []
        assert sql_query(db, "missing") == []
        with pytest.raises(ValueError):
            sql_query(db, "A", 3)


def test_transfer_keeps_both_memberships(tables):
    data = prepare(tables, 2022, 2023)
    assert set(roster_history(data, "B").teamID) == {"T", "O"}


def test_scope_identity_is_stable_and_changes_with_input(tables):
    data = prepare(tables, 2022, 2023)
    shuffled = {k: v.sample(frac=1, random_state=7) for k, v in tables.items()}
    assert prepare(shuffled, 2022, 2023).dataset_id == data.dataset_id
    assert prepare(tables, 2022, 2022).dataset_id != data.dataset_id
    tables["People"].loc[0, "nameFirst"] = "Changed"
    assert prepare(tables, 2022, 2023).dataset_id != data.dataset_id


@pytest.mark.parametrize("start,end", [(2023, 2022), (2000, 2001)])
def test_invalid_year_range(tables, start, end):
    with pytest.raises(ValueError):
        prepare(tables, start, end)


@pytest.mark.parametrize("target", ["People", "Teams"])
def test_missing_references_are_errors(tables, target):
    tables[target] = tables[target].iloc[1:]
    with pytest.raises(ValueError):
        prepare(tables, 2022, 2023)


@pytest.mark.parametrize("target", ["People", "Teams"])
def test_ambiguous_reference_keys_are_errors(tables, target):
    tables[target] = pd.concat([tables[target], tables[target].iloc[:1]])
    with pytest.raises(ValueError):
        prepare(tables, 2022, 2023)


def test_null_player_key_is_error(tables):
    tables["Appearances"].loc[0, "playerID"] = None
    with pytest.raises(ValueError):
        prepare(tables, 2022, 2023)


def test_download_rejects_html_and_wrong_schema():
    with pytest.raises(ValueError):
        read_csv_bytes(b"<html>Sign in</html>", "People")
    with pytest.raises(ValueError):
        read_csv_bytes(b"name\nA\n", "People")
    frame = read_csv_bytes(b"\xef\xbb\xbfplayerID,nameFirst,nameLast\na,A,One\n", "People")
    assert frame.playerID.tolist() == ["a"]


def test_corrupted_cache_is_not_silently_used(tmp_path):
    (tmp_path / "People.csv").write_text("not the pinned bytes")
    lock = tmp_path / "sources.json"
    lock.write_text(json.dumps({"files": {"People": {"file_id": "1", "sha256": "wrong"}}}))
    with pytest.raises(ValueError, match="一致"):
        download_tables(tmp_path, lock)


def test_measure_consumes_results_and_detects_changes():
    assert measure(lambda: ["A"], repeats=2)["result_count"] == 1
    calls = iter([["A"], ["B"]])
    with pytest.raises(ValueError):
        measure(lambda: next(calls), repeats=1)


def test_notebooks_valid_and_match_tested_module():
    import nbformat
    root = Path(__file__).resolve().parents[1]
    source = (root / "baseball_graph.py").read_text().strip()
    for path in (root / "notebooks").glob("*.ipynb"):
        nb = nbformat.read(path, as_version=4)
        nbformat.validate(nb)
        shared = [c for c in nb.cells if "shared_module" in c.metadata.get("tags", [])]
        assert len(shared) == 1
        assert shared[0].source.strip() == source
        for cell in nb.cells:
            if cell.cell_type == "code":
                compile(cell.source, str(path), "exec")
                assert cell.outputs == []
