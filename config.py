import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ===============================================================
# ▼▼▼ あなたが設定する項目 ▼▼▼
# ===============================================================

# 管理者としてBotを操作できる人のDiscordユーザーIDをここに入れる
ADMIN_USER_IDS = [352106470470582272] # あなたのDiscordユーザーIDに書き換えてください

# 因子画像を保存しておくための、ログ用チャンネルのID
FACTOR_LOG_CHANNEL_ID = 1405563100635070564 # あなたのチャンネルIDに書き換えてください

# ランキング更新通知を投稿するためのチャンネルID
RANKING_NOTIFICATION_CHANNEL_ID = 1407189675646521364 # あなたのチャンネルIDに書き換えてください


# ===============================================================
# ▼▼▼ Botの挙動に関する設定 (通常は変更不要) ▼▼▼
# ===============================================================

# --- 画像認識の調整パラメータ ---
VERTICAL_TOLERANCE_RATIO = 0.015
VERTICAL_OFFSET_RATIO = 0.010
COLUMN_DIVIDER_RATIO = 0.5
LEFT_COLUMN_SEARCH_START_RATIO = 0.15
LEFT_COLUMN_SEARCH_WIDTH_RATIO = 0.20
RIGHT_COLUMN_SEARCH_START_RATIO = 0.65
RIGHT_COLUMN_SEARCH_WIDTH_RATIO = 0.20

# --- Botが投稿するEmbedの画像URL ---
AUTHOR_ICON_URL = "https://cdn.discordapp.com/attachments/1407605158161940480/1407617349355442197/2-removebg-preview.png"
SEARCH_THUMBNAIL_URL = "https://cdn.discordapp.com/attachments/1407605158161940480/1407605207222718574/-removebg-preview.png"
RANKING_THUMBNAIL_URL = "https://cdn.discordapp.com/attachments/1407605158161940480/1407626444397482086/IMG_3186-removebg-preview.png"
MYBOX_THUMBNAIL_URL = "https://cdn.discordapp.com/attachments/1407605158161940480/1407627785463136301/IMG_3187-removebg-preview.png"
REGISTER_THUMBNAIL_URL = "https://cdn.discordapp.com/attachments/1407605158161940480/1407625108683755620/-removebg-preview.png"

# --- Googleスプレッドシートのキー ---
SPREADSHEET_KEY = "1NxsYfkptjaFGeVMQh9-5WtcaXpgf0qcvsLyRMvo5anw"


# ===============================================================
# ▼▼▼ Google認証情報の読み込み処理（Render最終版） ▼▼▼
# ===============================================================
gc = None
credentials_json_str = os.getenv('GOOGLE_CREDENTIALS_JSON')

if credentials_json_str:
    try:
        # 1. Secretの中身を一時的なファイルに書き出す
        creds_filename = "temp_google_creds.json"
        with open(creds_filename, "w") as f:
            f.write(credentials_json_str)

        # 2. 古いgspreadが唯一理解できる「ファイル名で読み込む」方法で認証する
        scope = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_filename, scope)
        gc = gspread.authorize(creds)
        
        print("✅ Google認証情報、正常に読み込み完了。")

    except Exception as e:
        print(f"❌ Google認証情報の処理中にエラー: {e}")
else:
    print("❌ エラー: Google認証情報が環境変数に設定されていません。")