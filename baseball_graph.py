"""MLB team-season graph: download, validate, prepare and compare queries.

Credentials are deliberately not handled by this module. Notebooks obtain them
from Colab Secrets (or a hidden prompt), never from a committed file.
"""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SOURCE_PAGE = "https://sabr.org/lahman-database/"
BOX_SHARE = "y1prhc795jk8zvmelfd3jq7tl389y6cd"
REQUIRED = {
    "People": {"playerID", "nameFirst", "nameLast"},
    "Teams": {"teamID", "yearID", "lgID", "name"},
    "Appearances": {"playerID", "teamID", "yearID", "lgID", "G_all"},
}


def read_csv_bytes(payload: bytes, table: str) -> pd.DataFrame:
    """Reject HTML/error bodies and missing columns before accepting a download."""
    if payload.lstrip(b"\xef\xbb\xbf \r\n").startswith(b"<"):
        raise ValueError(f"{table}: CSVではなくHTMLが返されました。公式配布先を確認してください。")
    frame = pd.read_csv(io.BytesIO(payload), dtype="string", encoding="utf-8-sig")
    missing = REQUIRED[table] - set(frame.columns)
    if missing:
        raise ValueError(f"{table}: 必須列がありません: {sorted(missing)}")
    return frame


def download_tables(cache_dir="data/raw", lock_path="sources.json"):
    """Fetch the three public SABR CSVs. Cache only validated, pinned bytes.

    No login or access token is needed. A changed upstream file fails closed:
    review its version/schema before updating sources.json; never silently mix
    data versions or substitute an unofficial mirror.
    """
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    lock = json.loads(Path(lock_path).read_text())
    tables, entries = {}, []
    for table in REQUIRED:
        spec = lock["files"][table]
        path = cache / f"{table}.csv"
        if path.exists():
            payload = path.read_bytes()
        else:
            response = requests.get(
                "https://sabr.box.com/index.php",
                params={"rm": "box_download_shared_file", "shared_name": BOX_SHARE,
                        "file_id": f"f_{spec['file_id']}"},
                timeout=(15, 120),
            )
            response.raise_for_status()
            payload = response.content
        digest = hashlib.sha256(payload).hexdigest()
        if digest != spec["sha256"]:
            raise ValueError(f"{table}: 配布データが固定版と一致しません。sources.jsonの版を確認してください。")
        tables[table] = read_csv_bytes(payload, table)
        if not path.exists():
            pending = path.with_suffix(".tmp")
            pending.write_bytes(payload)
            pending.replace(path)
        entries.append({"table": table, "rows": len(tables[table]), "sha256": digest})
    manifest = {"source": SOURCE_PAGE, "version": lock["version"],
                "checked_at_utc": datetime.now(timezone.utc).isoformat(), "files": entries}
    (cache / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return tables, manifest


@dataclass
class Prepared:
    players: pd.DataFrame
    seasons: pd.DataFrame
    memberships: pd.DataFrame
    dataset_id: str
    start_year: int
    end_year: int


def _required_keys(frame, columns, name):
    if frame[columns].isna().any().any() or frame[columns].eq("").any().any():
        raise ValueError(f"{name}: キーに欠損があります。")


def prepare(tables, start_year=2015, end_year=2025) -> Prepared:
    """One membership per player/league/team/year with at least one appearance.

    AL/NL only. TeamSeason includes league to avoid historical team-ID collisions.
    This is season-level co-membership, not proof of overlapping roster dates.
    """
    if start_year > end_year:
        raise ValueError("開始年度は終了年度以下にしてください。")
    for name, cols in REQUIRED.items():
        if not cols.issubset(tables[name].columns):
            raise ValueError(f"{name}: 必須列が不足しています。")
    apps = tables["Appearances"].copy()
    apps["yearID"] = pd.to_numeric(apps["yearID"], errors="raise").astype(int)
    apps["G_all"] = pd.to_numeric(apps["G_all"], errors="raise")
    selected = apps["yearID"].between(start_year, end_year) & apps["lgID"].isin(["AL", "NL"])
    apps = apps.loc[selected & apps["G_all"].gt(0)].copy()
    if apps.empty:
        raise ValueError("指定年度・AL/NLに出場記録がありません。")
    keys = ["yearID", "lgID", "teamID"]
    _required_keys(apps, ["playerID", *keys], "Appearances")
    teams = tables["Teams"].copy()
    teams["yearID"] = pd.to_numeric(teams["yearID"], errors="raise").astype(int)
    teams = teams.loc[teams["yearID"].between(start_year, end_year) & teams["lgID"].isin(["AL", "NL"]), keys + ["name"]]
    _required_keys(teams, keys, "Teams")
    if teams.duplicated(keys).any():
        raise ValueError("Teams: 年度・リーグ・球団の重複があります。")
    joined = apps[["playerID", *keys]].drop_duplicates().merge(
        teams, on=keys, how="left", validate="many_to_one", indicator=True)
    if joined["_merge"].ne("both").any():
        raise ValueError("Appearancesに対応するTeamsの行がありません。")
    joined["season_id"] = joined["yearID"].astype(str) + ":" + joined["lgID"] + ":" + joined["teamID"]
    seasons = joined[["season_id", *keys, "name"]].drop_duplicates().sort_values("season_id").reset_index(drop=True)
    members = joined[["playerID", "season_id"]].drop_duplicates().sort_values(["playerID", "season_id"]).reset_index(drop=True)
    people = tables["People"][["playerID", "nameFirst", "nameLast"]].copy()
    _required_keys(people, ["playerID"], "People")
    if people.duplicated("playerID").any():
        raise ValueError("People: playerIDに重複があります。")
    players = members[["playerID"]].drop_duplicates().merge(people, on="playerID", how="left", validate="one_to_one", indicator=True)
    if players["_merge"].ne("both").any():
        raise ValueError("出場選手に対応するPeopleの行がありません。")
    players["name"] = (players["nameFirst"].fillna("") + " " + players["nameLast"].fillna("")).str.strip()
    players.loc[players["name"].eq(""), "name"] = players["playerID"]
    players = players[["playerID", "name"]].sort_values("playerID").reset_index(drop=True)
    signature = f"model-v1:{start_year}:{end_year}\n" + "\n".join(
        f.to_csv(index=False, lineterminator="\n") for f in [players, seasons, members])
    dataset_id = hashlib.sha256(signature.encode()).hexdigest()[:24]
    return Prepared(players, seasons, members, dataset_id, start_year, end_year)


def roster_history(data, player_id):
    return data.memberships.loc[data.memberships.playerID.eq(player_id)].merge(
        data.seasons, on="season_id").sort_values(["yearID", "teamID"])


def sqlite_database(data):
    db = sqlite3.connect(":memory:")
    data.players.to_sql("players", db, index=False)
    data.seasons.to_sql("seasons", db, index=False)
    data.memberships.to_sql("memberships", db, index=False)
    db.executescript("""
    CREATE UNIQUE INDEX player_pk ON players(playerID);
    CREATE UNIQUE INDEX season_pk ON seasons(season_id);
    CREATE UNIQUE INDEX membership_pk ON memberships(playerID, season_id);
    CREATE INDEX membership_season ON memberships(season_id, playerID);
    """)
    return db


SQL_DIRECT = """
SELECT DISTINCT b.playerID
FROM memberships a JOIN memberships b ON a.season_id = b.season_id
WHERE a.playerID = :player_id AND b.playerID <> :player_id
ORDER BY b.playerID
"""
SQL_TWO_HOP = """
WITH direct AS (
  SELECT DISTINCT b.playerID FROM memberships a
  JOIN memberships b ON a.season_id = b.season_id
  WHERE a.playerID = :player_id AND b.playerID <> :player_id
)
SELECT DISTINCT d.playerID
FROM direct n JOIN memberships c ON c.playerID = n.playerID
JOIN memberships d ON d.season_id = c.season_id
WHERE d.playerID <> :player_id
AND d.playerID NOT IN (SELECT playerID FROM direct)
ORDER BY d.playerID
"""
CYPHER_DIRECT = """
MATCH (:BaseballDataset {id: $dataset_id, complete: true})
MATCH (a:BaseballPlayer {dataset_id: $dataset_id, playerID: $player_id})
      -[:PLAYED_IN]->(:BaseballTeamSeason)<-[:PLAYED_IN]-(b:BaseballPlayer)
WHERE b.playerID <> $player_id
RETURN DISTINCT b.playerID AS playerID ORDER BY playerID
"""
CYPHER_TWO_HOP = """
MATCH (:BaseballDataset {id: $dataset_id, complete: true})
MATCH (a:BaseballPlayer {dataset_id: $dataset_id, playerID: $player_id})
      -[:PLAYED_IN]->(:BaseballTeamSeason)<-[:PLAYED_IN]-(b:BaseballPlayer)
      -[:PLAYED_IN]->(:BaseballTeamSeason)<-[:PLAYED_IN]-(c:BaseballPlayer)
WHERE c <> a AND NOT EXISTS {
  MATCH (a)-[:PLAYED_IN]->(:BaseballTeamSeason)<-[:PLAYED_IN]-(c)
}
RETURN DISTINCT c.playerID AS playerID ORDER BY playerID
"""


def sql_query(db, player_id, hops=1):
    if hops not in (1, 2):
        raise ValueError("hops must be 1 or 2")
    query = SQL_DIRECT if hops == 1 else SQL_TWO_HOP
    return [r[0] for r in db.execute(query, {"player_id": player_id}).fetchall()]


def graph_query(driver, data, player_id, hops=1, database="neo4j"):
    if hops not in (1, 2):
        raise ValueError("hops must be 1 or 2")
    query = CYPHER_DIRECT if hops == 1 else CYPHER_TWO_HOP
    records, _, _ = driver.execute_query(query, dataset_id=data.dataset_id,
        player_id=player_id, database_=database, routing_="r")
    return [r["playerID"] for r in records]


def import_graph(driver, data, database="neo4j", batch_size=500):
    """Idempotent batches scoped to immutable data; never deletes existing data."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    queries = [
        "CREATE CONSTRAINT baseball_player_key IF NOT EXISTS FOR (p:BaseballPlayer) REQUIRE p.key IS UNIQUE",
        "CREATE CONSTRAINT baseball_season_key IF NOT EXISTS FOR (s:BaseballTeamSeason) REQUIRE s.key IS UNIQUE",
        "CREATE CONSTRAINT baseball_dataset_id IF NOT EXISTS FOR (d:BaseballDataset) REQUIRE d.id IS UNIQUE",
        "CREATE INDEX baseball_player_lookup IF NOT EXISTS FOR (p:BaseballPlayer) ON (p.dataset_id, p.playerID)",
    ]
    for query in queries:
        driver.execute_query(query, database_=database)
    driver.execute_query("MERGE (d:BaseballDataset {id:$dataset_id}) SET d.complete=false",
                         dataset_id=data.dataset_id, database_=database)
    jobs = [
        (data.players, """UNWIND $rows AS row
          MERGE (p:BaseballPlayer {key:$dataset_id + ':' + row.playerID})
          SET p.dataset_id=$dataset_id, p.playerID=row.playerID, p.name=row.name"""),
        (data.seasons, """UNWIND $rows AS row
          MERGE (s:BaseballTeamSeason {key:$dataset_id + ':' + row.season_id})
          SET s.dataset_id=$dataset_id, s.season_id=row.season_id,
              s.yearID=row.yearID, s.teamID=row.teamID, s.lgID=row.lgID, s.name=row.name"""),
        (data.memberships, """UNWIND $rows AS row
          MATCH (p:BaseballPlayer {key:$dataset_id + ':' + row.playerID})
          MATCH (s:BaseballTeamSeason {key:$dataset_id + ':' + row.season_id})
          MERGE (p)-[:PLAYED_IN]->(s)"""),
    ]
    for frame, query in jobs:
        rows = json.loads(frame.to_json(orient="records"))
        for offset in range(0, len(rows), batch_size):
            driver.execute_query(query, rows=rows[offset:offset + batch_size],
                dataset_id=data.dataset_id, database_=database)
    actual = graph_counts(driver, data, database)
    expected = {"players": len(data.players), "seasons": len(data.seasons),
                "memberships": len(data.memberships)}
    if actual != expected:
        raise ValueError(f"Neo4jへの取り込み件数が一致しません: {actual} != {expected}")
    driver.execute_query("MATCH (d:BaseballDataset {id:$dataset_id}) SET d.complete=true",
                         dataset_id=data.dataset_id, database_=database)
    return actual


def graph_counts(driver, data, database="neo4j"):
    result = {}
    patterns = {"players": "(p:BaseballPlayer {dataset_id:$dataset_id})",
                "seasons": "(p:BaseballTeamSeason {dataset_id:$dataset_id})",
                "memberships": "(:BaseballPlayer {dataset_id:$dataset_id})-[p:PLAYED_IN]->(:BaseballTeamSeason)"}
    for name, pattern in patterns.items():
        records, _, _ = driver.execute_query(f"MATCH {pattern} RETURN count(p) AS n",
            dataset_id=data.dataset_id, database_=database, routing_="r")
        result[name] = records[0]["n"]
    return result


def measure(call, repeats=5):
    """Wall-clock time, including transfer and full materialization; warm-up excluded."""
    if repeats < 1:
        raise ValueError("repeats must be positive")
    expected = call()
    values = []
    for _ in range(repeats):
        start = time.perf_counter()
        result = call()
        values.append((time.perf_counter() - start) * 1000)
        if result != expected:
            raise ValueError("計測中に検索結果が変化しました。")
    return {"median_ms": statistics.median(values), "min_ms": min(values),
            "max_ms": max(values), "repeats": repeats, "result_count": len(expected)}


def draw_neighborhood(data, player_id, max_players=20):
    """A bounded, deterministic two-mode view; labels explain truncated display."""
    import matplotlib.pyplot as plt
    import networkx as nx
    if player_id not in set(data.players.playerID):
        raise ValueError("選択した選手は対象年度にいません。")
    db = sqlite_database(data)
    peers = sql_query(db, player_id)
    db.close()
    visible = {player_id, *peers[:max_players]}
    origin_seasons = set(data.memberships.loc[data.memberships.playerID.eq(player_id), "season_id"])
    rows = data.memberships.loc[data.memberships.playerID.isin(visible) & data.memberships.season_id.isin(origin_seasons)]
    graph = nx.Graph()
    names = dict(zip(data.players.playerID, data.players.name))
    seasons = data.seasons.set_index("season_id")
    labels = {}
    for row in rows.itertuples(index=False):
        p, s = "p:" + row.playerID, "s:" + row.season_id
        graph.add_edge(p, s)
        labels[p] = names[row.playerID]
        labels[s] = f"{seasons.loc[row.season_id, 'teamID']} / {seasons.loc[row.season_id, 'yearID']}"
    fig, ax = plt.subplots(figsize=(14, 8))
    nx.draw_networkx(graph, nx.spring_layout(graph, seed=42), ax=ax, labels=labels,
        node_color=["#e8ad42" if n == "p:" + player_id else "#9bbce3" if n.startswith("p:") else "#cadaca" for n in graph],
        font_size=8, node_size=600, edge_color="#b1b7c2")
    ax.set_title(f"{names[player_id]}: {min(max_players, len(peers))} of {len(peers)} peers shown (ID order)")
    ax.axis("off")
    fig.tight_layout()
    return fig
