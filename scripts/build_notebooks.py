"""Generate self-contained Colab notebooks from the tested shared module."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)}


def code(text, *tags):
    return {"cell_type": "code", "metadata": {"tags": list(tags)},
            "source": text.strip().splitlines(True), "execution_count": None, "outputs": []}


def save(name, cells):
    for n, cell in enumerate(cells):
        cell["id"] = f"cell-{n:02}"
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"}, "colab": {"name": name, "provenance": []}}, "cells": cells}
    (ROOT / "notebooks").mkdir(exist_ok=True)
    (ROOT / "notebooks" / name).write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n")


def common(title):
    requirements = [line.strip() for line in (ROOT / "requirements.txt").read_text().splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    module = (ROOT / "baseball_graph.py").read_text()
    lock = json.loads((ROOT / "sources.json").read_text())
    return [md(f"# {title}\n\n[GitHub: exkkt/neo4j](https://github.com/exkkt/neo4j)\n\n"
        "MLBの選手を、同じ年度・同じ球団での出場記録からつなぐ学習プロジェクト。"
        "このノートブックは単独で実行できます。ColabではCPUランタイムで十分です。\n\n"
        "共通関数はテスト済みの `baseball_graph.py` から生成しています。"
        "まだ実行していないセルの結果を成果として記載しないでください。"),
        md("## 1. ライブラリの準備\n最初にこのセルを実行します。"),
        code("import subprocess, sys\nsubprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *" + repr(requirements) + "])", "install"),
        md("## 2. 共通関数\n長いセルですが、ダウンロード・検証・検索を行う関数の定義です。"
           "一度実行してから下へ進んでください。公開コードと同じ内容です。"),
        code(module, "shared_module"),
        code("from IPython.display import display\n"
             "SOURCE_LOCK = " + repr(lock) + "\n"
             "Path('sources.json').write_text(json.dumps(SOURCE_LOCK, indent=2), encoding='utf-8');"),
        md("## 3. 分析条件とデータ取得\n"
           "初期値は2015〜2025年、AL/NLです。`PLAYER_ID` はLahmanの選手ID。"
           "大谷翔平は `ohtansh01`。年度を変更したら以降のセルを再実行してください。\n\n"
           "公式出典: https://sabr.org/lahman-database/ 。元データは再配布せず、公式Boxから取得します。"
           "チェックサムが変わった場合は停止します。`sources.json` を無確認で更新しないでください。"),
        code("START_YEAR = 2015 #@param {type:\"integer\"}\n"
             "END_YEAR = 2025 #@param {type:\"integer\"}\n"
             "PLAYER_ID = 'ohtansh01' #@param {type:\"string\"}\n"
             "tables, manifest = download_tables()\n"
             "data = prepare(tables, START_YEAR, END_YEAR)\n"
             "display(pd.DataFrame(manifest['files']))\n"
             "display(pd.DataFrame([{'players':len(data.players), 'team_seasons':len(data.seasons), 'memberships':len(data.memberships)}]))\n"
             "if PLAYER_ID not in set(data.players.playerID):\n"
             "    raise ValueError('指定選手は対象年度にいません。PLAYER_IDか年度を変更してください。')\n"
             "print('Dataset:', data.dataset_id)"),
    ]


def connection():
    return [md("## Neo4jに接続する\n"
        "[Neo4j Aura](https://console.neo4j.io/)などで、この学習用のDBを用意してください。"
        "ColabはPythonの実行場所、Neo4jは別のDBサーバーです。\n\n"
        "Colab左側の鍵アイコン（シークレット）に `NEO4J_URI`・`NEO4J_USERNAME`・"
        "`NEO4J_PASSWORD` を登録し、このノートブックからのアクセスを許可します。"
        "登録がない場合は非表示入力を使います。値をコードや出力に書きません。\n\n"
        "接続先は学習用DBにしてください。次の取り込みセルはノード・制約を追加します。"
        "既存データの削除は行いません。"),
        code('''from getpass import getpass
from neo4j import GraphDatabase
import logging
logging.getLogger("neo4j").setLevel(logging.CRITICAL)

def hidden_setting(name):
    try:
        from google.colab import userdata
        return userdata.get(name)
    except Exception:
        return getpass(f"{name} (hidden): ")

DATABASE = "neo4j"
def connect_hidden():
    driver = None
    try:
        uri = hidden_setting("NEO4J_URI")
        username = hidden_setting("NEO4J_USERNAME")
        password = hidden_setting("NEO4J_PASSWORD")
        driver = GraphDatabase.driver(uri, auth=(username, password))
        driver.verify_connectivity()
        return driver
    except Exception:
        if driver is not None:
            driver.close()
        raise RuntimeError("接続できません。DBの稼働状態とColabシークレットを確認してください。") from None

driver = connect_hidden()
print("Neo4j connected")''', "needs_neo4j"),
        md("## データを取り込む\n"
           "`Player → TeamSeason` の二部グラフ。年度・リーグ・球団を一緒にキーにします。"
           "同じデータの再実行では `MERGE` により重複しません。"
           "対象年度を変えると別のデータセットになり、以前のデータとは混ざりません。"),
        code('''# パスワード等が例外の詳細に出ないよう、生の接続例外は表示しません。
try:
    counts = import_graph(driver, data, database=DATABASE)
except Exception:
    raise RuntimeError("取り込みに失敗しました。接続・権限・DB容量を確認して再実行してください。") from None
display(pd.DataFrame([counts]))''', "needs_neo4j")]


def main():
    save("01_data_preparation.ipynb", common("01 — MLBデータの取得と前処理") + [
        md("## 4. 元データを観察する\n列、欠損、重複、年度範囲を先に確認します。"
           "欠損を機械的に全部削除せず、今回必要な列を決めます。"),
        code('''for name, frame in tables.items():
    print(name, "shape:", frame.shape)
    display(frame.head(3))
    display(frame[list(sorted(REQUIRED[name]))].isna().sum().rename("missing").to_frame())
    print("exact duplicate rows:", int(frame.duplicated().sum()))
print("Appearances years:", pd.to_numeric(tables["Appearances"].yearID).agg(["min", "max"]).to_dict())'''),
        md("## 5. 好きな選手の所属履歴\n"
           "選手名の表記ゆれを避け、`playerID` で結合します。"
           "移籍した年は複数球団の行が残ります。"),
        code("display(roster_history(data, PLAYER_ID))\n"
             "# 別の選手を探す例\n"
             "display(data.players.loc[data.players.name.str.contains('Ohtani|Ichiro', case=False, regex=True)])"),
        md("## 6. SQLでチームメート候補を確認する\n"
           "ここでいうチームメートは「同じ年度・同じ球団に出場記録がある選手」です。"
           "在籍期間や同じ試合への出場は保証しません。"),
        code("db = sqlite_database(data)\n"
             "peer_ids = sql_query(db, PLAYER_ID)\n"
             "print('Peers:', len(peer_ids))\n"
             "display(data.players.loc[data.players.playerID.isin(peer_ids)].head(30))\n"
             "db.close()"),
        code("fig = draw_neighborhood(data, PLAYER_ID)\n"
             "Path('outputs').mkdir(exist_ok=True)\n"
             "fig.savefig('outputs/neighborhood.png', dpi=150)\n"
             "display(fig)\n"
             "import matplotlib.pyplot as plt\nplt.close(fig)"),
        md("## 学習メモ（自分の言葉で記入）\n"
           "- この分析で答えたい問い：\n- IDで結合する理由：\n"
           "- 年度を区別しない場合に起きる誤り：\n- 実行して初めて分かったこと：\n"
           "- 年度単位のデータからは言えないこと：\n\n"
           "次は `02_neo4j_analysis.ipynb`。GitHubへは「ファイル → GitHubにコピーを保存」。"
           "この操作で保存されるのはノートブックで、ランタイム内のCSV・画像ファイルは別です。")])
    save("02_neo4j_analysis.ipynb", common("02 — Neo4jで選手のつながりを検索") + connection() + [
        md("## 同じ球団・年度の選手を検索\n"
           "Cypherは `(選手)-[:PLAYED_IN]->(球団・年度)` という形で関係を書きます。"
           "検索する名前やIDは文字列連結せずパラメータで渡します。"),
        code('''print(CYPHER_DIRECT)
try:
    peer_ids = graph_query(driver, data, PLAYER_ID, database=DATABASE)
    second_ids = graph_query(driver, data, PLAYER_ID, hops=2, database=DATABASE)
except Exception:
    raise RuntimeError("検索に失敗しました。Neo4jの接続と取り込み完了を確認してください。") from None
print("1段階:", len(peer_ids), "2段階（1段階の選手を除く）:", len(second_ids))
display(data.players.loc[data.players.playerID.isin(peer_ids)].head(30))
display(data.players.loc[data.players.playerID.isin(second_ids)].head(30))''', "needs_neo4j"),
        md("2段階は「最短で2人分のつながり」。起点本人と直接つながる選手を除きます。"
           "関係は時間の順番を制約せずたどるので、情報伝達・因果関係は表しません。"),
        code('''db = sqlite_database(data)
assert peer_ids == sql_query(db, PLAYER_ID)
assert second_ids == sql_query(db, PLAYER_ID, hops=2)
db.close()
fig = draw_neighborhood(data, PLAYER_ID)
display(fig)
import matplotlib.pyplot as plt
plt.close(fig)
print("SQLiteとNeo4jの結果が一致しました。図は直接のつながりを最大20選手に絞っています。")''', "needs_neo4j"),
        code("driver.close()", "needs_neo4j"),
        md("## 学習メモ\n- なぜTeamSeasonノードを挟むのか：\n"
           "- Cypherで読みやすかった点・難しかった点：\n- 好きな選手で発見したつながり：\n"
           "- Neo4jが適していると考えた処理と、その理由：")])
    save("03_sql_comparison.ipynb", common("03 — Neo4jとSQLiteの結果・実行時間を比較") + connection() + [
        md("## 比較の条件\n"
           "同じ入力・年度・定義・重複除去・ソートを使います。まず結果の一致を確認します。"
           "その後、ウォームアップ1回を除き5回測定。全件取得までの壁時計時間です。\n\n"
           "**Colab内のインメモリSQLiteとリモートNeo4jの比較には通信時間・マシン差が含まれます。**"
           "DBエンジン単体の優劣を示すベンチマークではありません。"
           "キャッシュは初期化せず、読み取りの繰り返しを測ります。"),
        code('''import platform
import importlib.metadata
db = sqlite_database(data)
results = []
try:
    for hops in (1, 2):
        sql_call = lambda: sql_query(db, PLAYER_ID, hops)
        neo_call = lambda: graph_query(driver, data, PLAYER_ID, hops, DATABASE)
        if sql_call() != neo_call():
            raise ValueError("Result mismatch")
        for engine, call in [("SQLite (local memory)", sql_call), ("Neo4j (remote)", neo_call)]:
            results.append({"engine": engine, "hops": hops, **measure(call)})
    records, _, _ = driver.execute_query("CALL dbms.components() YIELD name, versions RETURN name, versions", database_=DATABASE)
    server_versions = [dict(r) for r in records]
except Exception:
    raise RuntimeError("比較を中止しました。検索結果の一致、接続、DBの稼働状態を確認してください。") from None
finally:
    db.close()
    driver.close()
report = pd.DataFrame(results)
display(report)
Path("outputs").mkdir(exist_ok=True)
report.to_csv("outputs/comparison.csv", index=False)
environment = {
    "python": platform.python_version(), "platform": platform.platform(),
    "sqlite": sqlite3.sqlite_version,
    "packages": {p: importlib.metadata.version(p) for p in ["pandas", "neo4j", "requests"]},
    "neo4j_server": server_versions, "dataset_id": data.dataset_id,
    "years": [START_YEAR, END_YEAR], "player_id": PLAYER_ID,
    "source_manifest": manifest,
    "measurement": "warm-up 1, repeats 5, wall-clock including network and materialization; caches not cleared",
}
Path("outputs/environment.json").write_text(json.dumps(environment, indent=2))''', "needs_neo4j"),
        md("## クエリを並べて読む"),
        code("print(SQL_DIRECT)\nprint(CYPHER_DIRECT)\nprint(SQL_TWO_HOP)\nprint(CYPHER_TWO_HOP)"),
        md("## 考察（測定してから記入）\n"
           "- 結果が一致したか：\n- 1段階と2段階で何が変わったか：\n"
           "- 書き方の理解しやすさ：\n- 通信やキャッシュの影響：\n"
           "- この条件からは結論できないこと：\n- 次に比較したい条件：\n\n"
           "次の実験は年度範囲を縮める、選手を変更する、同じホスト上のDB同士で測る、など。"
           "実行環境の情報は `outputs/environment.json` に残ります。")])


if __name__ == "__main__":
    main()
