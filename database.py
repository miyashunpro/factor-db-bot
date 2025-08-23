import gspread
import traceback
from collections import defaultdict
from datetime import datetime
import pandas as pd
import config
import discord

def load_factor_dictionaries(gspread_client):
    global factor_dictionary, factor_name_to_id, character_data, char_name_to_id, character_list_sorted
    try:
        spreadsheet = gspread_client.open("因子評価データベース")
        temp_factor_dict = {}
        temp_factor_name_to_id = {}
        temp_character_data = {}
        temp_char_name_to_id = {}
        print("1. [辞書]キャラ名 シートを読み込み中...")
        try:
            ws = spreadsheet.worksheet('[辞書]キャラ名')
            records = ws.get_all_records()
            for record in records:
                if record.get('キャラID') and record.get('キャラ名'):
                    char_id = str(record['キャラID']).strip()
                    char_name = str(record['キャラ名']).strip()
                    thumbnail_url = record.get('サムネイルURL', '').strip()
                    temp_character_data[char_id] = {'name': char_name, 'green_factor_ids': [], 'thumbnail_url': thumbnail_url}
                    temp_char_name_to_id[char_name] = char_id
            print(f"-> {len(temp_character_data)}件のキャラ名をロードしました。")
        except gspread.exceptions.WorksheetNotFound:
            print("致命的エラー: '[辞書]キャラ名'シートが見つかりません。")
            return
        except Exception as e:
            print(f"キャラ名辞書の読み込み中にエラー: {e}")
            return
        print("2. スキル・ステータス等の因子辞書を読み込み中...")
        for ws in spreadsheet.worksheets():
            if ws.title.startswith('[辞書]') and ws.title not in ['[辞書]キャラ名', '[辞書]キャラ緑因子紐付け']:
                factor_type = ws.title.replace('[辞書]', '').strip()
                records = ws.get_all_records()
                for record in records:
                    if record.get('因子ID') and record.get('因子名'):
                        factor_id = str(record['因子ID']).strip()
                        factor_name = str(record['因子名']).strip()
                        temp_factor_dict[factor_id] = {'name': factor_name, 'type': factor_type}
                        temp_factor_name_to_id[factor_name] = factor_id
        print(f"-> {len(temp_factor_dict)}件のスキル・ステータス因子をロードしました。")
        print("3. [辞書]キャラ緑因子紐付け シートを読み込み中...")
        try:
            ws = spreadsheet.worksheet('[辞書]キャラ緑因子紐付け')
            records = ws.get_all_records()
            for record in records:
                if record.get('キャラID') and record.get('緑因子ID'):
                    char_id = str(record['キャラID']).strip()
                    green_id = str(record['緑因子ID']).strip()
                    if char_id in temp_character_data:
                        if green_id in temp_factor_dict:
                            temp_character_data[char_id]['green_factor_ids'].append(green_id)
                        else:
                            print(f"警告: 紐付けシートの緑因子ID '{green_id}' は因子辞書に存在しません。")
                    else:
                        print(f"警告: 紐付けシートのキャラID '{char_id}' はキャラ名辞書に存在しません。")
            print(f"-> キャラと緑因子の紐付け完了。")
        except gspread.exceptions.WorksheetNotFound:
            print("警告: '[辞書]キャラ緑因子紐付け'シートが見つかりません。")
        except Exception as e:
            print(f"キャラ緑因子紐付け辞書の読み込み中にエラー: {e}")
        factor_dictionary = temp_factor_dict
        factor_name_to_id = temp_factor_name_to_id
        character_data = temp_character_data
        char_name_to_id = temp_char_name_to_id
        for cid, cdata in character_data.items():
            factor_dictionary[cid] = {'name': cdata['name'], 'type': 'キャラ名'}
            factor_name_to_id[cdata['name']] = cid
        
        character_list_sorted = sorted(character_data.items(), key=lambda item: item[1]['name'])
        print(f"-> {len(character_list_sorted)}件のキャラをソートし、キャラブラウザの準備完了。")
        return temp_factor_dict, temp_factor_name_to_id, temp_character_data, temp_char_name_to_id, character_list_sorted

    except Exception as e:
        print(f"因子辞書読み込み中に致命的なエラー: {e}")
        traceback.print_exc()


def load_score_sheets_by_id(gspread_client, factor_name_to_id):
    if not factor_name_to_id:
        print("エラー: 採点簿を読み込むには、先に因子辞書を読み込む必要があります。処理をスキップします。")
        return
    try:
        spreadsheet = gspread_client.open("因子評価データベース")
        temp_sheets = {}
        for ws in spreadsheet.worksheets():
            if ws.title.startswith('[採点簿]'):
                sheet_name = ws.title.replace('[採点簿]', '', 1).strip()
                all_values = ws.get_all_values()
                if not all_values: continue
                sheet_dict = {}
                for i, row in enumerate(all_values):
                    if len(row) >= 3 and row[0] and row[2]:
                        factor_name = str(row[0]).strip()
                        score_str = str(row[2]).strip()
                        if score_str.lstrip('-').isdigit():
                            score = int(score_str)
                            factor_id = factor_name_to_id.get(factor_name)
                            if factor_id: sheet_dict[factor_id] = score
                            else:
                                if i > 0: print(f"警告: 採点簿'{sheet_name}'の'{factor_name}'は因子辞書にないため無視されます。")
                        elif i == 0: print(f"情報: 採点簿'{sheet_name}'の1行目はヘッダーとしてスキップします。")
                if sheet_dict: temp_sheets[sheet_name] = sheet_dict
        score_sheets = temp_sheets
        print(f"-> 因子ID採点簿の読み込み完了。{len(score_sheets)}個の採点簿をロードしました。")
        return temp_sheets
    except Exception as e:
        print(f"採点簿の読み込み中にエラー: {e}")
        traceback.print_exc()


def record_evaluation_to_db(gspread_client, interaction, character_name, factor_details, image_url, purpose, race_route, memo, factor_dictionary, score_sheets, char_name_to_id):
    try:
        spreadsheet = gspread_client.open("因子評価データベース")
        individual_id = str(int(interaction.created_at.timestamp()))
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        summary_sheet = spreadsheet.worksheet("評価サマリー")
        summary_headers = summary_sheet.row_values(1)
        if not summary_headers:
            summary_headers = ['個体ID', '投稿日時', '投稿者名', '投稿者ID', 'キャラ名', '画像URL']
            summary_sheet.update(range_name='A1', values=[summary_headers])
        all_total_scores = {
            s_name: sum(s_sheet.get(f['id'], 0) * f['stars'] for f in factor_details)
            for s_name, s_sheet in score_sheets.items()
        }
        summary_row_data = {'個体ID': individual_id, '投稿日時': now, '投稿者名': interaction.user.display_name, '投稿者ID': str(interaction.user.id), 'キャラ名': character_name, '画像URL': image_url,
                            '用途': purpose,
                            'レースローテ': race_route,
                            'メモ': memo
                           }
        for sheet_name, total_score in all_total_scores.items():
            col_name = f"合計({sheet_name})"
            if col_name not in summary_headers:
                summary_sheet.update_cell(1, len(summary_headers) + 1, col_name)
                summary_headers.append(col_name)
            summary_row_data[col_name] = total_score
        final_summary_row = [summary_row_data.get(h, "") for h in summary_headers]
        summary_sheet.append_row(final_summary_row)
        factors_sheet = spreadsheet.worksheet("因子データ")
        if not factors_sheet.row_values(1):
            factors_sheet.update(range_name='A1', values=[['個体ID', '因子ID', '因子名', '因子の種類', '星の数']])
        rows_to_append = []
        char_id = char_name_to_id.get(character_name)
        if char_id:
             char_factor_info = factor_dictionary.get(char_id, {'name': character_name, 'type': 'キャラ名'})
             rows_to_append.append([individual_id, char_id, char_factor_info['name'], char_factor_info['type'], 0])
        for factor in factor_details:
            factor_id = factor['id']
            factor_info = factor_dictionary.get(factor_id, {'name': '不明な因子', 'type': '不明'})
            rows_to_append.append([individual_id, factor_id, factor_info['name'], factor_info['type'], factor['stars']])
        if rows_to_append:
            factors_sheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
        print(f"ID:{individual_id} の評価結果をデータベースに記録しました。")
        return individual_id
    except Exception as e:
        print(f"データベース記録中にエラーが発生: {e}")
        traceback.print_exc()
        return None

def get_full_database(gspread_client):
    """データベースから全データを読み込み、2つのDataFrameを返す"""
    spreadsheet = gspread_client.open("因子評価データベース")
    summary_sheet = spreadsheet.worksheet("評価サマリー")
    factors_sheet = spreadsheet.worksheet("因子データ")

    summary_df = pd.DataFrame(summary_sheet.get_all_records(numericise_ignore=['all']))
    factors_df = pd.DataFrame(factors_sheet.get_all_records(numericise_ignore=['all']))
    
    return summary_df, factors_df

def save_parent_factors(gspread_client, individual_id, p1_factor_id, p1_stars, p2_factor_id, p2_stars):
    """親因子の情報をスプレッドシートに保存する"""
    try:
        spreadsheet = gspread_client.open("因子評価データベース")
        summary_sheet = spreadsheet.worksheet("評価サマリー")
        
        # 文字列に変換して、確実に検索できるようにする
        cell = summary_sheet.find(str(individual_id), in_column=1)
        if not cell:
            print(f"エラー: 更新対象の因子 ID {individual_id} が見つかりませんでした。")
            return False

        updates = {
            '親赤因子1_ID': p1_factor_id, '親赤因子1_星数': p1_stars,
            '親赤因子2_ID': p2_factor_id, '親赤因子2_星数': p2_stars,
        }
        headers = summary_sheet.row_values(1)
        
        for header, value in updates.items():
            if value is not None:
                col_index = -1
                try:
                    col_index = headers.index(header) + 1
                except ValueError:
                    # ヘッダーが存在しない場合は、末尾に追加
                    summary_sheet.update_cell(1, len(headers) + 1, header)
                    headers.append(header)
                    col_index = len(headers)
                
                summary_sheet.update_cell(cell.row, col_index, str(value))
        
        return True
    except Exception as e:
        print(f"DB保存中にエラーが発生: {e}")
        traceback.print_exc()
        return False


# database.py に追加

def delete_factor_by_id(gspread_client, individual_id: str, user_id: int, is_admin: bool):
    """
    指定された個体IDの因子をデータベースから削除する。
    所有者本人か管理者のみ削除可能。
    """
    try:
        spreadsheet = gspread_client.open_by_key(config.SPREADSHEET_KEY)
        summary_sheet = spreadsheet.worksheet("評価サマリー")
        factors_sheet = spreadsheet.worksheet("因子データ")

        # サマリーシートから該当行を検索
        summary_records = summary_sheet.get_all_records(numericise_ignore=['all'])
        summary_df = pd.DataFrame(summary_records)
        
        target_row = summary_df[summary_df['個体ID'] == individual_id]

        if target_row.empty:
            return False, "指定されたIDの因子が見つかりませんでしたわ。"

        owner_id = str(target_row.iloc[0].get('所有者ID', ''))

        # 権限チェック
        if not is_admin and owner_id != str(user_id):
            return False, "ご自身の因子以外は削除できませんことよ。"

        # --- 削除処理 ---
        # 1. サマリーシートから削除
        # gspreadは行番号でしか削除できないため、該当行のインデックスを探す
        cell = summary_sheet.find(individual_id)
        if cell:
            summary_sheet.delete_rows(cell.row)
            print(f"サマリーシートから個体ID '{individual_id}' を削除しました。")
        else:
            # 見つからなくても因子データは消しに行く
            print(f"警告: サマリーシートで個体ID '{individual_id}' が見つかりませんでした。")


        # 2. 因子データシートから関連データをすべて削除
        factor_records = factors_sheet.get_all_records(numericise_ignore=['all'])
        factor_df = pd.DataFrame(factor_records)
        
        # 削除対象の行インデックスをリストアップ（逆順にしておくのが安全）
        rows_to_delete = factor_df[factor_df['個体ID'] == individual_id].index.tolist()
        # gspreadの行番号は1から始まり、ヘッダー行があるので+2する
        # 削除対象の行インデックスをリストアップ（gspreadの行番号は1から、ヘッダー行があるので+2）
        rows_to_delete = factor_df[factor_df['個体ID'] == individual_id].index.tolist()
        gspread_rows_to_delete = sorted([i + 2 for i in rows_to_delete], reverse=True)

        if not gspread_rows_to_delete:
            print(f"警告: 因子データシートで個体ID '{individual_id}' のデータが見つかりませんでした。")
            return True, f"個体ID `{individual_id}` の因子を削除いたしましたわ。"

        # ▼▼▼ こっから下が修正箇所や！ ▼▼▼

        # バッチ処理で一括削除する
        batch_delete_requests = []
        sheet_id = factors_sheet._properties['sheetId'] # シートの固有IDを取得

        for row_num in gspread_rows_to_delete:
            batch_delete_requests.append({
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": row_num - 1,  # APIは0から始まるので-1する
                        "endIndex": row_num
                    }
                }
            })
        
        # 1回のリクエストでまとめて削除依頼を出す
        if batch_delete_requests:
            spreadsheet.batch_update({'requests': batch_delete_requests})

        print(f"因子データシートから個体ID '{individual_id}' の関連データを {len(gspread_rows_to_delete)} 件削除しました。")

        return True, f"個体ID `{individual_id}` の因子を削除いたしましたわ。"
    except Exception as e:
        print(f"因子削除中にエラーが発生: {e}"); traceback.print_exc()
        return False, f"削除中にエラーが発生いたしました: {e}"        


def update_owner(gspread_client, individual_id: str, user: discord.Member):
    try:
        spreadsheet = gspread_client.open("因子評価データベース")
        summary_sheet = spreadsheet.worksheet("評価サマリー")
        cell = summary_sheet.find(individual_id, in_column=1)
        if not cell:
            return False # 因子が見つからなかった

        headers = summary_sheet.row_values(1)
        owner_id_col = headers.index('所有者ID') + 1
        owner_memo_col = headers.index('所有者メモ') + 1
        
        cells_to_update = [
            gspread.Cell(row=cell.row, col=owner_id_col, value=str(user.id)),
            gspread.Cell(row=cell.row, col=owner_memo_col, value=f"サーバーメンバー: {user.display_name}")
        ]
        summary_sheet.update_cells(cells_to_update)
        return True # 成功
    except Exception as e:
        print(f"DBオーナー更新中にエラー: {e}")
        traceback.print_exc()
        return False


def recalculate_all_scores(gspread_client, score_sheets: dict):
    try:
        spreadsheet = gspread_client.open("因子評価データベース")
        summary_sheet = spreadsheet.worksheet("評価サマリー")
        factors_sheet = spreadsheet.worksheet("因子データ")
        
        summary_data = summary_sheet.get_all_records(numericise_ignore=['all'])
        factors_data = factors_sheet.get_all_records(numericise_ignore=['all'])
        
        if not summary_data or not factors_data:
            return 0

        factors_by_id = defaultdict(list)
        for factor in factors_data:
            factors_by_id[factor['個体ID']].append(factor)

        updated_data = []
        summary_headers = summary_sheet.row_values(1)
        
        # 不要なスコアシート列をヘッダーから削除
        score_sheet_cols = [h for h in summary_headers if h.startswith('合計(')]
        for h in score_sheet_cols:
            if h.replace('合計(', '')[:-1] not in score_sheets:
                summary_headers.remove(h)
        
        # 必要なスコアシート列をヘッダーに追加
        for sheet_name in score_sheets.keys():
            if f"合計({sheet_name})" not in summary_headers:
                summary_headers.append(f"合計({sheet_name})")

        for summary_row in summary_data:
            individual_id = summary_row['個体ID']
            current_factors = factors_by_id.get(individual_id, [])
            for sheet_name, score_sheet in score_sheets.items():
                total_score = sum(score_sheet.get(str(f['因子ID']), 0) * int(f['星の数']) for f in current_factors if str(f['因子ID']) in score_sheet and str(f['星の数']).isdigit())
                summary_row[f"合計({sheet_name})"] = total_score
            
            # ヘッダーの順序に合わせて行データを作成
            updated_data.append([summary_row.get(h, "") for h in summary_headers])

        summary_sheet.clear()
        summary_sheet.update(range_name='A1', values=[summary_headers])
        if updated_data:
            summary_sheet.update(range_name='A2', values=updated_data)
            
        return len(summary_data)
    except Exception as e:
        print(f"スコア再計算中にエラーが発生: {e}")
        traceback.print_exc()
        raise e # エラーを呼び出し元に伝える                