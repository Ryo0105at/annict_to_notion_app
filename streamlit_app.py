import streamlit as st
import requests

ANNICT_TOKEN = st.secrets["ANNICT_TOKEN"]

st.title("🎬 Annict → Notion 自動登録ツール")
with st.expander("🔑 Notionの統合トークン・データベースIDの取得手順"):
    st.markdown("""
#### 📌 Notionの統合トークンの取得手順
1. [Notionのインテグレーションページ](https://www.notion.so/my-integrations) にアクセス。
2. 「+ New integration」をクリック。
3. 名前を設定し、「Internal Integration Token」を生成。
4. 生成されたトークンをこのアプリの「Notionの統合トークン」にコピペ。

#### 📁 NotionのデータベースIDの取得手順
1. 登録したいNotionデータベースをブラウザで開く。
2. URLの形式：`https://www.notion.so/ユーザー名/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...`
3. `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` の部分が **データベースID**。
4. それをこのアプリの「NotionのデータベースID」にコピペ。

💡 Notionのデータベースには「インテグレーションを共有」する設定も必要です！
""")

# 📌 Notion用入力欄
season = st.selectbox("📅 登録するクールを選んでください", [
    "2025-spring", "2025-summer", "2025-fall", "2025-winter"
])

notion_token = st.text_input("🔑 Notionの統合トークン", type="password")
database_id = st.text_input("🗂️ NotionのデータベースID")

# 🎯 Annictの seasonName を Notion用の形式に変換（例：2025-spring → 2025春）
def convert_season(season_en, year):
    season_map = {
        "WINTER": "冬", "SPRING": "春", "SUMMER": "夏", "FALL": "秋"
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

    # 成功・失敗に関係なく結果を返す（ステータスとレスポンス）
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
            with st.spinner("Notionに登録中..."):
                for row in works:
                    result = create_page(row, notion_token, database_id)
                    if not result["ok"]:
                        st.error(f'❌ {result["title"]} の登録に失敗 (Status {result["status"]})')
                        st.code(result["text"])
