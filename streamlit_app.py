import streamlit as st
import requests

st.title("🎬 Annict → Notion 自動登録ツール")

# 入力欄
season = st.selectbox("📅 登録するクールを選択してください", [
    "2025-spring", "2025-summer", "2025-fall", "2025-winter"
])

notion_token = st.text_input("🔑 Notionの統合トークン", type="password")
database_id = st.text_input("🗂️ NotionのデータベースID")

# Annict APIからデータ取得
def get_annict_data(season):
    ACCESS_TOKEN = "あなたのAnnictトークン（公開してよい範囲）"
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
          staffs {{
            name
            roleText
          }}
          productionCompanies {{
            name
          }}
        }}
      }}
    }}
    """

    res = requests.post("https://api.annict.com/graphql", headers=headers, json={"query": query})
    if res.status_code == 200:
        return res.json()["data"]["searchWorks"]["nodes"]
    else:
        st.error(f"Annict APIエラー: {res.text}")
        return []

# Notionへ1件ずつ登録
def create_page(row, token, db_id):
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    director = ", ".join([s["name"] for s in row["staffs"] if "監督" in s["roleText"]])
    company = ", ".join([p["name"] for p in row["productionCompanies"]])
    episodes = row["episodesCount"] or 0

    data = {
        "parent": {"database_id": db_id},
        "properties": {
            "タイトル": {"title": [{"text": {"content": row["title"]}}]},
            "監督": {"rich_text": [{"text": {"content": director}}]},
            "制作会社": {"rich_text": [{"text": {"content": company}}]},
            "クール": {"select": {"name": row["seasonName"]}},
            "話数": {"number": episodes}
        }
    }

    res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=data)
    return res.status_code == 200

# メイン処理
if st.button("🎯 Notionに登録する"):
    if not notion_token or not database_id:
        st.warning("Notion情報が未入力です。")
    else:
        data = get_annict_data(season)
        with st.spinner("Notionに登録中..."):
            for row in data:
                success = create_page(row, notion_token, database_id)
                if success:
                    st.success(f'✅ {row["title"]} を登録しました')
                else:
                    st.error(f'❌ {row["title"]} の登録に失敗しました')
