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
        "### 初回の接続設定\n"
        "\n"
        "1. [Aura Console](https://console.neo4j.io/) の **Instances** を開きます。DBがまだなければ、**Create instance** から **AuraDB Free** を選び、作成時に接続情報ファイルをダウンロードして手元の安全な場所に保存します。作成時に生成されたパスワードは後から再表示できません。既存のDBを使う場合は、そのDBの接続情報を用意します。\n"
        "2. Colabで02または03を開き、左側の **鍵アイコン（シークレット）→ 新しいシークレットを追加（Add new secret）** を選びます。下の表どおり、名前と値を1件ずつ、計3件登録します。\n"
        "\n"
        "| Colabの名前（Name） | 登録する値（Value） |\n"
        "|---|---|\n"
        "| `NEO4J_URI` | 対象DBの **Connection URI**。作成時のファイルか、Auraの **Instances → 対象DBの … → Inspect** で確認できます。Auraでは `neo4j+s://` から始まります。 |\n"
        "| `NEO4J_USERNAME` | DB作成時に表示された **Username**。初期ユーザーは通常 `neo4j` です。 |\n"
        "| `NEO4J_PASSWORD` | DB作成時に表示された **Password**。AuraのWebサイトにログインするときのパスワードとは別です。 |\n"
        "\n"
        "3. 3件すべての **ノートブックへのアクセス（Notebook access）** をオンにします。02と03を両方使う場合は、もう一方でも同じ3件へのアクセスを許可します。\n"
        "4. DBが `RUNNING` になったら、Colabの **「Neo4jに接続する」** セルまで順番に実行します。`Neo4j connected` が表示されたら接続できています。\n"
        "\n"
        "接続情報はColabのシークレット欄に貼り付け、コードや出力には書きません。接続情報ファイルもGitHubにアップロードしないでください。\n"
        "\n"
        "[AuraのDB作成手順](https://neo4j.com/docs/aura/getting-started/create-instance/) · [接続情報の確認方法](https://neo4j.com/docs/aura/connecting-applications/overview/)\n"
        "\n"
        "登録がない場合は非表示入力を使えます。\n\n"
        "接続失敗時は `[AUTH]`（認証）、`[UNREACHABLE]`（到達不能）、"
        "`[SECRET_ACCESS]`（シークレットのアクセス許可）などの案内に従ってください。"
        "DB名は `DATABASE = None` として接続ユーザーの既定DBを使います。\n\n"
        "### 2回目以降に開くとき\n"
        "AuraDB Freeは72時間使わないと自動停止します。02・03を再実行する前に、"
        "[Aura Console](https://console.neo4j.io/)の **Instances** で対象DBの状態を確認してください。\n\n"
        "1. `PAUSED` の場合は、DBカード右上の **… → Resume Instance** を選び、確認画面が出たら確定します。\n"
        "2. `RUNNING` になったら、Colabで「Neo4jに接続する」コードセルを実行します。"
        "すでに `RUNNING` なら、そのまま接続できます。\n"
        "3. `Neo4j connected` が表示されたら、「データを取り込む」から続けます。\n\n"
        "[Aura公式の再開手順](https://neo4j.com/docs/aura/managing-instances/instance-actions/#_resume_a_paused_instance)\n\n"
        "接続先は学習用DBにしてください。次の取り込みセルはノード・制約を追加します。"
        "既存データの削除は行いません。"),
        code('''from getpass import getpass
from urllib.parse import urlsplit
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired, ConfigurationError
import logging
logging.getLogger("neo4j").setLevel(logging.CRITICAL)

def hidden_setting(name):
    try:
        from google.colab import userdata
    except ImportError:
        value = getpass(f"{name} (hidden): ")
    else:
        try:
            value = userdata.get(name)
        except userdata.SecretNotFoundError:
            value = getpass(f"{name} (hidden): ")
        except userdata.NotebookAccessError:
            raise RuntimeError(f"[SECRET_ACCESS] Colab左の鍵アイコンで {name} のノートブックアクセスを許可してください。") from None
        except Exception:
            raise RuntimeError("[SECRET_READ] Colabシークレットを取得できません。鍵アイコンの設定を確認して再実行してください。") from None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"[EMPTY_SETTING] {name} が空です。Colabシークレットに登録してください。") from None
    return value if name == "NEO4J_PASSWORD" else value.strip()

def safe_neo4j_error(error):
    # Exception text, URI and credential values are never included in output.
    code = getattr(error, "code", None)
    if isinstance(error, AuthError) or code == "Neo.ClientError.Security.Unauthorized":
        return "[AUTH] 認証に失敗しました。同じAuraインスタンスのURI・ユーザー名・DBパスワードを登録してください。Auraログイン用パスワードとは別です。"
    if code == "Neo.ClientError.Database.DatabaseNotFound":
        return "[DATABASE] 対象DBが見つかりません。DATABASE = None に戻すか、管理画面で実際のDB名を確認してください。"
    if code == "Neo.ClientError.Security.Forbidden":
        return "[PERMISSION] この操作の権限がありません。接続ユーザーの読み書き権限を確認してください。"
    if isinstance(error, (ServiceUnavailable, SessionExpired)):
        return "[UNREACHABLE] DBに到達できません。Auraでインスタンスの稼働状態を確認し、PAUSEDならDBカードの「… → Resume Instance」を選び、RUNNINGになってから接続セルを再実行してください。稼働中ならConnection URIとネットワークを確認し、再実行してください。"
    if isinstance(error, (ConfigurationError, ValueError)):
        return "[CONFIG] 接続設定を確認してください。NEO4J_URIには管理画面のConnection URIを使用します。Auraコンソールのhttps URLは使えません。"
    return "[NEO4J_OTHER] Neo4jの処理に失敗しました。DBの状態・接続設定・権限・容量を確認してください。生の例外はシークレット保護のため表示しません。"

# Use the user's default database; do not assume its name is 'neo4j'.
DATABASE = None

def connect_hidden():
    uri = hidden_setting("NEO4J_URI")
    username = hidden_setting("NEO4J_USERNAME")
    password = hidden_setting("NEO4J_PASSWORD")
    driver = None
    try:
        parsed = urlsplit(uri)
        if parsed.scheme not in {"neo4j", "neo4j+s", "neo4j+ssc", "bolt", "bolt+s", "bolt+ssc"} or not parsed.hostname:
            raise ValueError()
        if parsed.username is not None or parsed.password is not None:
            raise ValueError()
        driver = GraphDatabase.driver(uri, auth=(username, password), connection_timeout=15)
        driver.verify_connectivity()
        with driver.session(database=DATABASE) as session:
            session.run("RETURN 1 AS ok").consume()
        return driver
    except Exception as error:
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass
        raise RuntimeError(safe_neo4j_error(error)) from None

driver = connect_hidden()
print("Neo4j connected（DBの読み取り確認済み）")''', "needs_neo4j"),
        md("## データを取り込む\n"
           "`Player → TeamSeason` の二部グラフ。年度・リーグ・球団を一緒にキーにします。"
           "同じデータの再実行では `MERGE` により重複しません。"
           "対象年度を変えると別のデータセットになり、以前のデータとは混ざりません。"),
        code('''# パスワード等が例外の詳細に出ないよう、生の接続例外は表示しません。
try:
    counts = import_graph(driver, data, database=DATABASE)
except Exception as error:
    raise RuntimeError(safe_neo4j_error(error)) from None
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
        md("図はトラウト・ベッツ・フリーマンを優先し、残りを選手ID順に最大20人まで表示します。"
           "対象年度に起点と同じ球団で出場した選手だけが対象です。人気順のランキングではありません。"),
        code("fig = draw_neighborhood(data, PLAYER_ID, preferred_player_ids=FEATURED_PLAYER_IDS)\n"
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
        md("図はトラウト・ベッツ・フリーマンを優先し、残りを選手ID順に最大20人まで表示します。"
           "対象年度に起点と同じ球団で出場した選手だけが対象です。人気順のランキングではありません。"),
        code('''db = sqlite_database(data)
assert peer_ids == sql_query(db, PLAYER_ID)
assert second_ids == sql_query(db, PLAYER_ID, hops=2)
db.close()
fig = draw_neighborhood(data, PLAYER_ID, preferred_player_ids=FEATURED_PLAYER_IDS)
display(fig)
import matplotlib.pyplot as plt
plt.close(fig)
print("SQLiteとNeo4jの結果が一致しました。図は直接のつながりを最大20選手に絞っています。")''', "needs_neo4j"),
        code("driver.close()", "needs_neo4j"),
        md("## 学習メモ\n- なぜTeamSeasonノードを挟むのか：\n"
           "- Cypherで読みやすかった点・難しかった点：\n- 好きな選手で発見したつながり：\n"
           "- Neo4jが適していると考えた処理と、その理由：")])
    save("03_sql_comparison.ipynb", common("03 — SQLとCypherの書き方・検索結果を比較") + connection() + [
        md("## 1段階：同じ球団・年度の選手を探す\n"
           "SQLでは `memberships` を球団・年度IDで自己結合します。"
           "Cypherでは、起点の選手から球団・年度ノードを挟んで別の選手へたどるパターンを `MATCH` で書きます。"
           "どちらも本人を除き、`DISTINCT` で選手の重複を取り除きます。"),
        code('print("SQLite（SQL）:", SQL_DIRECT)\nprint("Neo4j（Cypher）:", CYPHER_DIRECT)'),
        md("## 2段階：チームメートを1人介してつながる選手を探す\n"
           "SQLでは `WITH direct AS (...)` で直接つながる選手を求め、その選手の出場記録をさらに `JOIN` します。"
           "Cypherでは、選手と球団・年度のパターンをもう1組つなげます。"
           "どちらも本人と直接つながる選手を除き、最短で2段階の選手を返します。"),
        code('print("SQLite（SQL）:", SQL_TWO_HOP)\nprint("Neo4j（Cypher）:", CYPHER_TWO_HOP)'),
        md("## 選手IDの一覧が一致するか確認する\n"
           "同じ前処理済みデータと起点の選手を使い、1段階・2段階それぞれで、"
           "並べ替え済みの選手ID一覧を全件比較します。件数と一致判定を表にします。"),
        code('''from contextlib import closing

results = []
try:
    with closing(sqlite_database(data)) as db:
        for hops in (1, 2):
            sql_ids = sql_query(db, PLAYER_ID, hops=hops)
            cypher_ids = graph_query(driver, data, PLAYER_ID, hops=hops, database=DATABASE)
            results.append({
                "段階": hops,
                "SQLiteの件数": len(sql_ids),
                "Neo4jの件数": len(cypher_ids),
                "選手ID一覧が一致": sql_ids == cypher_ids,
            })
except Exception as error:
    raise RuntimeError(safe_neo4j_error(error)) from None
finally:
    driver.close()

report = pd.DataFrame(results)
display(report)
if not report["選手ID一覧が一致"].all():
    raise RuntimeError("選手ID一覧が一致しません。表で該当する段階を確認してください。")''', "needs_neo4j"),
        md("## 考察\n"
           "- SQLの結合条件とCypherのパターンはどう対応するか。\n"
           "- 2段階の検索で、直接つながる選手をどう除いているか。")])



if __name__ == "__main__":
    main()
