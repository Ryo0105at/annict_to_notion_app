import streamlit as st
import requests
import textwrap
from datetime import datetime

ANNICT_TOKEN = st.secrets["ANNICT_TOKEN"]

st.title("Notion アニメ自動登録ツール")

with st.expander("🔑 Notionの統合トークン・データベースIDの取得手順"):
    st.markdown(textwrap.dedent("""
        #### 📌 Notionの統合トークンの取得手順
        1. [Notionのインテグレーションページ](https://www.notion.so/my-integrations) にアクセス。
        2. 「+ New integration」をクリック。
        3. 名前を設定し、「Internal Integration Token」を生成。
        5. ページへのアクセス権を設定してください。
        4. 生成されたトークン(内部インテグレーションシークレット)をこのアプリの「Notionの統合トークン」にコピペ。

        #### 📁 NotionのデータベースIDの取得手順
        1. 登録したいNotionデータベースをブラウザで開く。
        2. URLの形式：`https://www.notion.so/ユーザー名/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...`
        3. `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` の部分が **データベースID**。
        4. それをこのアプリの「NotionのデータベースID」にコピペ。

        💡 Notionのデータベースには「インテグレーションを共有」する設定も必要です！
    """), unsafe_allow_html=False)

# 📌 Notion用入力欄
def build_season_options(start_year: int = 2025) -> list[str]:
    """
    2025年から現在の年までのクールを生成。
    表示は「最新が先頭」になるよう降順で返す（例: 2025-autumn, 2025-summer, ...）。
    """
    current_year = datetime.now().year + 1
    season_order = ["winter", "spring", "summer", "autumn"]  # 年内の並び
    options = [f"{y}-{s}" for y in range(start_year, current_year + 1) for s in season_order]
    return list(reversed(options))  # 最新が先頭

def infer_current_season(dt: datetime | None = None) -> str:
    """
    実行時点の月から現在クールを推定して 'YYYY-season' 形式で返す。
    (1-3: winter, 4-6: spring, 7-9: summer, 10-12: autumn)
    """
    dt = dt or datetime.now()
    m = dt.month
    if m in (1, 2, 3):
        season = "winter"
    elif m in (4, 5, 6):
        season = "spring"
    elif m in (7, 8, 9):
        season = "summer"
    else:
        season = "autumn"
    return f"{dt.year}-{season}"

season_options = build_season_options(start_year=2025)
default_season = infer_current_season()
if default_season not in season_options:
    # 念のためのフォールバック（理論上ここには来ない想定）
    default_index = 0
else:
    default_index = season_options.index(default_season)

season = st.selectbox(
    "📅 登録するクールを選んでください",
    season_options,
    index=default_index
)

notion_token = st.text_input("🔑 Notionの統合トークン", type="password")
database_id = st.text_input("🗂️ NotionのデータベースID")

# 🎯 Annictの seasonName を Notion用の形式に変換（例：2025-spring → 2025春）
def convert_season(season_en, year):
    season_map = {
        "WINTER": "冬", "SPRING": "春", "SUMMER": "夏", "AUTUMN": "秋"
    }
    return f"{year}{season_map.get(season_en.upper(), season_en)}"


# 📥 Annict APIからアニメ情報を取得
def get_annict_data(season):
    headers = {
        "Authorization": f"Bearer {ANNICT_TOKEN}",
        "Content-Type": "application/json"
    }

    query = f"""
    {{
    searchWorks(seasons: ["{season}"], orderBy: {{field: WATCHERS_COUNT, direction: DESC}}) {{
        nodes {{
        title
        seasonName
        seasonYear
        episodesCount
        officialSiteUrl
        media
        staffs {{
            nodes {{
            roleText
            name
            }}
        }}
        casts {{
            nodes {{
            name
            character {{
                name
            }}
            }}
        }}
        }}
    }}
    }}
    """

    res = requests.post("https://api.annict.com/graphql", headers=headers, json={"query": query})

    try:
        result = res.json()
    except Exception as e:
        st.error(f"❌ Annict APIレスポンスの解析に失敗: {e}")
        return []

    if "errors" in result:
        st.error("❌ Annict API エラー: " + result["errors"][0].get("message", "不明なエラー"))
        return []

    all_works = result.get("data", {}).get("searchWorks", {}).get("nodes", [])

    # ✅ media = "web" を除外
    filtered_works = [work for work in all_works if work.get("media") != "WEB"]

    return filtered_works


# 📋 Notionデータベースの既存タイトル → ページIDのマップを取得
def get_existing_title_map(token, db_id):
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    title_map = {}
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {"page_size": 100}

    while True:
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code != 200:
            st.error(f"❌ Notionデータベースの取得に失敗しました (Status {res.status_code})")
            return None

        data = res.json()
        for page in data.get("results", []):
            title_prop = page.get("properties", {}).get("作品名", {})
            title_list = title_prop.get("title", [])
            if title_list:
                title = title_list[0].get("text", {}).get("content", "")
                title_map[title] = page["id"]

        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]

    return title_map


# 📝 Notion に1作品を登録
def create_page(row, token, db_id):
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    title = row["title"]
    season = convert_season(row["seasonName"], row["seasonYear"])
    episodes = row.get("episodesCount") or 0
    website = row.get("officialSiteUrl", "") or ""

    staff_list = row.get("staffs", {}).get("nodes", [])
    director = ", ".join([s.get("name", "") for s in staff_list if s.get("roleText", "").strip() == "監督"])
    company = ", ".join([s.get("name", "") for s in staff_list if "アニメーション制作" in s.get("roleText", "")])
    staff_all = ", ".join([f'{s.get("roleText", "")}:{s.get("name", "")}' for s in staff_list])[:2000]

    cast_list = row.get("casts", {}).get("nodes", [])
    voice_casts = ", ".join([
        f'{c.get("name", "不明")}（{c.get("character", {}).get("name", "？")}）'
        for c in cast_list
    ])[:2000]

    data = {
        "parent": {"database_id": db_id},
        "properties": {
            "作品名": {"title": [{"text": {"content": title or "タイトル不明"}}]},
            "放送時期": {"select": {"name": season or "未設定"}},
            "制作会社": {"rich_text": [{"text": {"content": company or "不明"}}]},
            "公式サイト": {"url": website if website else None},
            "監督": {"rich_text": [{"text": {"content": director or "不明"}}]},
            "声優": {"rich_text": [{"text": {"content": voice_casts or "不明"}}]},
            "スタッフ": {"rich_text": [{"text": {"content": staff_all or "不明"}}]},
        }
    }

    res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=data)

    return {
        "ok": res.status_code == 200,
        "title": title,
        "status": res.status_code,
        "text": res.text
    }


# 🔄 Notion の既存ページを更新
def update_page(row, token, page_id):
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    title = row["title"]
    season = convert_season(row["seasonName"], row["seasonYear"])
    episodes = row.get("episodesCount") or 0
    website = row.get("officialSiteUrl", "") or ""

    staff_list = row.get("staffs", {}).get("nodes", [])
    director = ", ".join([s.get("name", "") for s in staff_list if s.get("roleText", "").strip() == "監督"])
    company = ", ".join([s.get("name", "") for s in staff_list if "アニメーション制作" in s.get("roleText", "")])
    staff_all = ", ".join([f'{s.get("roleText", "")}:{s.get("name", "")}' for s in staff_list])[:2000]

    cast_list = row.get("casts", {}).get("nodes", [])
    voice_casts = ", ".join([
        f'{c.get("name", "不明")}（{c.get("character", {}).get("name", "？")}）'
        for c in cast_list
    ])[:2000]

    data = {
        "properties": {
            "作品名": {"title": [{"text": {"content": title or "タイトル不明"}}]},
            "放送時期": {"select": {"name": season or "未設定"}},
            "制作会社": {"rich_text": [{"text": {"content": company or "不明"}}]},
            "公式サイト": {"url": website if website else None},
            "監督": {"rich_text": [{"text": {"content": director or "不明"}}]},
            "声優": {"rich_text": [{"text": {"content": voice_casts or "不明"}}]},
            "スタッフ": {"rich_text": [{"text": {"content": staff_all or "不明"}}]},
        }
    }

    res = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=headers, json=data)

    return {
        "ok": res.status_code == 200,
        "title": title,
        "status": res.status_code,
        "text": res.text
    }


# 🚀 登録実行
if st.button("Notionに登録する"):
    if not notion_token or not database_id:
        st.warning("NotionのトークンとデータベースIDを入力してください。")
    else:
        works = get_annict_data(season)
        if not works:
            st.warning("Annictからデータを取得できませんでした。")
        else:
            with st.spinner("既存データを確認中..."):
                title_map = get_existing_title_map(notion_token, database_id)
                if title_map is None:
                    st.stop()

            created, updated, failed = [], [], []
            with st.spinner("Notionに登録中..."):
                for row in works:
                    title = row.get("title", "")
                    if title in title_map:
                        result = update_page(row, notion_token, title_map[title])
                        if result["ok"]:
                            updated.append(title)
                        else:
                            failed.append(result)
                            st.error(f'❌ {result["title"]} の更新に失敗 (Status {result["status"]})')
                            st.code(result["text"])
                    else:
                        result = create_page(row, notion_token, database_id)
                        if result["ok"]:
                            created.append(title)
                        else:
                            failed.append(result)
                            st.error(f'❌ {result["title"]} の登録に失敗 (Status {result["status"]})')
                            st.code(result["text"])

            st.success(f"✅ 新規登録: {len(created)}件　🔄 更新: {len(updated)}件")
