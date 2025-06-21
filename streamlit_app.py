import streamlit as st
import requests

st.title("🎬 Annict → Notion 自動登録ツール")

# 📌 Notion用入力欄
season = st.selectbox("📅 登録するクールを選んでください", [
    "2025-spring", "2025-summer", "2025-fall", "2025-winter"
])

notion_token = st.text_input("🔑 Notionの統合トークン", type="password")
database_id = st.text_input("🗂️ NotionのデータベースID")

# 🎯 Annictの seasonName を Notion用の形式に変換（例：2025-spring → 2025春）
def convert_season(season_name):
    season_map = {"winter": "冬", "spring": "春", "summer": "夏", "fall": "秋"}
    try:
        year, season_en = season_name.split("-")
        return f"{year}{season_map[season_en]}"
    except:
        return season_name

# 📥 Annict APIからアニメ情報を取得
def get_annict_data(season):
    ACCESS_TOKEN = "pW-Jm_6-RBhzrvCUpRaBd90kwtCM_3KL3Kjp1U1cCRo"  # ← Annictの自分のトークンに置き換えてください
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    query = f"""
    {{
    searchWorks(seasons: ["{season}"], orderBy: {{field: WATCHERS_COUNT, direction: DESC}}) {{
        nodes {{
        title
        seasonName
        episodesCount
        officialSiteUrl
        staffs {{
            nodes {{
            name
            roleText
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

    return result.get("data", {}).get("searchWorks", {}).get("nodes", [])

# 📝 Notion に1作品を登録
def create_page(row, token, db_id):
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    title = row["title"]
    season = convert_season(row["seasonName"])
    episodes = row.get("episodesCount") or 0
    website = row.get("officialSiteUrl", "")

    staff_list = row.get("staffs", {}).get("nodes", [])
    director = ", ".join([s["name"] for s in staff_list if "監督" in s["roleText"]])
    company = ", ".join([s["name"] for s in staff_list if "アニメーション制作" in s["roleText"]])
    staff_all = ", ".join([f'{s["name"]}：{s["roleText"]}' for s in staff_list])

    cast_list = row.get("casts", {}).get("nodes", [])
    voice_casts = ", ".join([f'{c["name"]}（{c["character"]["name"]}）' for c in cast_list])

    data = {
        "parent": {"database_id": db_id},
        "properties": {
            "タイトル": {"title": [{"text": {"content": title}}]},
            "放送時期(2025春)": {"select": {"name": season}},
            "制作会社": {"rich_text": [{"text": {"content": company}}]},
            "公式サイト": {"url": website},
            "監督": {"rich_text": [{"text": {"content": director}}]},
            "声優": {"rich_text": [{"text": {"content": voice_casts}}]},
            "スタッフ": {"rich_text": [{"text": {"content": staff_all}}]},
        }
    }

    res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=data)
    return res.status_code == 200

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
                    success = create_page(row, notion_token, database_id)
                    if success:
                        st.success(f'✅ {row["title"]} を登録しました')
                    else:
                        st.error(f'❌ {row["title"]} の登録に失敗しました')