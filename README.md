# factor-db-bot

ウマ娘のスクリーンショットから因子データを自動で読み取り、データベースに記録するDiscord Botです。

## 概要

手動で因子を記録する手間を解消するために開発しました。
画像をBotに送るだけで、因子名・星数・キャラ名を自動で認識してGoogle Spreadsheetに保存します。

## 使用技術

- Python
- Google Cloud Vision API（OCR・テキスト検出）
- OpenCV（画像処理・星マーク検出）
- Discord.py（Bot実装）
- gspread（Google Spreadsheet連携）
- Flask（ヘルスチェック用サーバー）

## 主な機能

- スクリーンショットから因子名・星数を自動認識
- キャラクター名の自動判定
- 因子データのデータベース登録・検索・ランキング表示
- スコアシートによる因子評価・再計算

