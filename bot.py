# DB開発中.py (メインファイル)

import discord
from discord import ui, Interaction, Embed, Color, ButtonStyle, TextStyle, app_commands
import pandas as pd
import traceback
from collections import defaultdict
import gspread
import os
import cv2 # debug_evaluateで必要

# 自作ファイルをimport
import config
import database
import image_processor
from ui_views import (
    create_themed_embed, SetOwnerView, SearchView, SearchResultView, RankingView
)
import os


# --- グローバル変数 (Bot全体で共有するデータ) ---
factor_dictionary = {}
factor_name_to_id = {}
score_sheets = {}
character_data = {}
char_name_to_id = {}
character_list_sorted = []

# --- ヘルパー関数 ---
async def score_sheet_autocompleter(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    sheet_names = list(score_sheets.keys())
    filtered_choices = [name for name in sheet_names if current.lower() in name.lower()]
    return [app_commands.Choice(name=name, value=name) for name in filtered_choices[:25]]

# --- スラッシュコマンド定義 ---
@app_commands.command(name="因子登録", description="因子をデータベースに登録いたしますわ。")
@app_commands.describe(image="登録遊ばせたい因子の画像ですわ", score_sheet_name="使用するスコアシートの名前ですの。指定がない場合はデータベースへの登録のみ行いますわ。")
@app_commands.autocomplete(score_sheet_name=score_sheet_autocompleter)
async def evaluate(interaction: Interaction, image: discord.Attachment, score_sheet_name: str = None):
    client: FactorBotClient = interaction.client
    if not image.filename.lower().endswith(('png', 'jpg', 'jpeg')):
        return await interaction.response.send_message("画像ファイル（png, jpg, jpeg）を添付してくださいな。", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    temp_image_path = f"temp_{image.id}.png"
    try:
        await image.save(temp_image_path)
        if not factor_dictionary: return await interaction.followup.send("エラーですわ: 因子辞書が読み込まれていないようですの。", ephemeral=True)
        
        all_texts = image_processor.load_texts_from_google_api(temp_image_path)
        image_height, image_width = image_processor.get_image_dimensions(temp_image_path)
        
        dynamic_min_area = image_processor.calculate_dynamic_min_star_area(all_texts, image_height)
        all_stars = image_processor.get_all_stars(temp_image_path, min_star_area=dynamic_min_area)
        
        character_name = image_processor.classify_character_name_by_id(all_texts, image_height, char_name_to_id)
        factor_details = image_processor.extract_factor_details(all_texts, all_stars, (image_height, image_width), factor_name_to_id)

        if character_name == "不明" and character_data:
            for factor in factor_details:
                for cid, cdata in character_data.items():
                    if factor['id'] in cdata.get('green_factor_ids', []):
                        character_name = cdata['name']
                        print(f"緑因子 '{factor_dictionary.get(factor['id'], {}).get('name', '不明')}' からキャラ名 '{character_name}' を特定しました。")
                        break
                if character_name != "不明": break

        if not factor_details: return await interaction.followup.send("エラーですわ：評価対象の因子が見つかりませんでしたの。", ephemeral=True)
        
        permanent_image_url = await client.upload_image_to_log_channel(interaction, temp_image_path, character_name, image.url)
        
        individual_id = database.record_evaluation_to_db(
            gspread_client=client.gspread_client,
            interaction=interaction,
            character_name=character_name,
            factor_details=factor_details,
            image_url=permanent_image_url,
            purpose=None,
            race_route=None,
            memo=None,
            # ▼▼▼ 不足していた3つの引数を追加！ ▼▼▼
            factor_dictionary=factor_dictionary,
            score_sheets=score_sheets,
            char_name_to_id=char_name_to_id
        )
        
        if score_sheet_name:
            score_sheet = score_sheets.get(score_sheet_name)
            if not score_sheet:
                return await interaction.followup.send(f"指定されたスコアシート `{score_sheet_name}` は見つかりませんでしたわ。", ephemeral=True)
            total_score = sum(score_sheet.get(factor['id'], 0) * factor['stars'] for factor in factor_details)
            desc = f"まあ、`{score_sheet_name}`で**{total_score}点**ですのね！ふふっ、素晴らしい評価ですわ！\n（個体ID: {individual_id}）"
        else:
            desc = f"この出会いが、あなたの素敵な思い出のひとつになりますように♪\n（個体ID: {individual_id}）"

        title = f"「{character_name}」の因子を記録いたしました♪"
        embed = create_themed_embed(title=title, description=desc, footer_text=f"Request by {interaction.user.display_name}")

        char_id = char_name_to_id.get(character_name)
        if char_id and character_data.get(char_id, {}).get('thumbnail_url'):
            embed.set_image(url=character_data[char_id]['thumbnail_url'])
        else:
            embed.set_thumbnail(url=config.REGISTER_THUMBNAIL_URL)

        owner_view = SetOwnerView(client.gspread_client, individual_id, interaction.user, factor_dictionary)
        await interaction.followup.send(
            content="それで、この素敵な因子のトレーナーは、どなたになりますの？", 
            embed=embed, view=owner_view, ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"エラーですわ：処理中に問題が発生したようですの ❌\n`{e}`", ephemeral=True); traceback.print_exc()
    finally:
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)

@app_commands.command(name="debug_evaluate", description="【デバッグ用】探索エリアを調整しながら因子を評価いたしますわ。")
@app_commands.describe(image="評価したい因子のスクリーンショット画像ですわ", left_start="左列の探索開始位置", left_width="左列の探索エリアの幅", right_start="右列の探索開始位置", right_width="右列の探索エリアの幅")
async def debug_evaluate(interaction: Interaction, image: discord.Attachment, left_start: float = config.LEFT_COLUMN_SEARCH_START_RATIO, left_width: float = config.LEFT_COLUMN_SEARCH_WIDTH_RATIO, right_start: float = config.RIGHT_COLUMN_SEARCH_START_RATIO, right_width: float = config.RIGHT_COLUMN_SEARCH_WIDTH_RATIO):
    if not image.filename.lower().endswith(('png', 'jpg', 'jpeg')): return await interaction.response.send_message("画像ファイル（png, jpg, jpeg）を添付してくださいな。", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    temp_image_path = f"temp_{image.id}.png"; debug_image_path = f"debug_{image.id}.png"
    try:
        await image.save(temp_image_path)
        if not factor_dictionary: return await interaction.followup.send("エラーですわ: 因子辞書が読み込まれていないようですの。")
        all_texts = image_processor.load_texts_from_google_api(temp_image_path); all_stars = image_processor.get_all_stars(temp_image_path)
        debug_img = cv2.imread(temp_image_path); img_height, img_width, _ = debug_img.shape
        params = {'vt_px': img_height * config.VERTICAL_TOLERANCE_RATIO, 'l_start_px': int(img_width * left_start), 'l_end_px': int(img_width * (left_start + left_width)), 'r_start_px': int(img_width * right_start), 'r_end_px': int(img_width * (right_start + right_width))}
        cv2.rectangle(debug_img, (params['l_start_px'], 0), (params['l_end_px'], img_height), (0, 255, 0), 2); cv2.rectangle(debug_img, (params['r_start_px'], 0), (params['r_end_px'], img_height), (0, 255, 0), 2)
        for star in all_stars: x, y, w, h = star['bbox']; cv2.rectangle(debug_img, (x, y), (x + w, y + h), (0, 255, 255), 2)
        found_factors_text = ""
        for text_info in all_texts:
            factor_id = image_processor.classify_factor_by_id(text_info['text'], factor_name_to_id)
            if factor_id:
                factor_info = factor_dictionary.get(factor_id); clean_name = factor_info['name'] if factor_info else "不明"; text_x_center = (text_info['bbox'][0][0] + text_info['bbox'][1][0]) / 2
                star_check_y = text_info['y_center'] + (img_height * config.VERTICAL_OFFSET_RATIO); star_count = 0
                if text_x_center < (img_width * config.COLUMN_DIVIDER_RATIO): star_count = sum(1 for star in all_stars if params['l_start_px'] < (star['bbox'][0] + star['bbox'][2] / 2) < params['l_end_px'] and abs(star_check_y - (star['bbox'][1] + star['bbox'][3] / 2)) < params['vt_px'])
                else: star_count = sum(1 for star in all_stars if params['r_start_px'] < (star['bbox'][0] + star['bbox'][2] / 2) < params['r_end_px'] and abs(star_check_y - (star['bbox'][1] + star['bbox'][3] / 2)) < params['vt_px'])
                if star_count > 0: found_factors_text += f"✓ {clean_name} (★{star_count})\n"
                else: found_factors_text += f"✗ {clean_name}\n"
        cv2.imwrite(debug_image_path, debug_img)
        embed = Embed(title="デバッグ評価結果ですわ", description="指定されたパラメータで因子を検出いたしました。\nデータベースには記録されませんのよ。"); embed.add_field(name="検出された因子一覧ですの", value=found_factors_text or "因子は見つかりませんでしたわ。", inline=False); embed.set_image(url=f"attachment://{debug_image_path}")
        await interaction.followup.send(embed=embed, file=discord.File(debug_image_path))
    except Exception as e: await interaction.followup.send(f"エラーですわ：処理中に問題が発生したようですの ❌\n`{e}`"); traceback.print_exc()
    finally:
        if os.path.exists(temp_image_path): os.remove(temp_image_path)
        if os.path.exists(debug_image_path): os.remove(debug_image_path)

@app_commands.command(name="因子検索", description="データベースに登録された因子を検索いたしますわ。")
async def search_factors_command(interaction: Interaction):
    client: FactorBotClient = interaction.client
    try:
        if not client.gspread_client: 
            return await interaction.response.send_message("データベースが読み込まれておりませんので、検索できませんでしたわ。", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        message = await interaction.followup.send("検索画面を準備しておりますので、少々お待ちくださいな♪")
        
        view = SearchView(
            gspread_client=client.gspread_client, 
            author=interaction.user, 
            message=message,
            factor_dictionary=factor_dictionary,
            character_data=character_data,
            score_sheets=score_sheets,
            character_list_sorted=character_list_sorted
        )
        await message.edit(content=None, embed=view.create_embed(), view=view)
        client.active_search_views[interaction.user.id] = message
            
    except Exception as e:
        print(f"検索機能の起動中にエラーが発生しました: {e}"); traceback.print_exc()

@app_commands.command(name="mybox", description="あなたが所有している因子を一覧で表示いたしますわ。")
async def mybox(interaction: Interaction):
    client: FactorBotClient = interaction.client
    await interaction.response.defer(ephemeral=True)
    try:
        summary_df, _ = database.get_full_database(client.gspread_client)
        if summary_df.empty or '所有者ID' not in summary_df.columns:
            return await interaction.followup.send("まだどなたも因子を所有しておりませんわ。", ephemeral=True)

        my_factors = summary_df[summary_df['所有者ID'] == str(interaction.user.id)]
        if my_factors.empty:
            embed = create_themed_embed(title="🍀 マイ倉庫", description="これからどんな因子と出会うのか、楽しみですわね♪", footer_text=f"Request by {interaction.user.display_name}", thumbnail_url=config.MYBOX_THUMBNAIL_URL)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        message = await interaction.followup.send("あなたの倉庫を読み込んでおりますので、少々お待ちくださいな...", ephemeral=True)
        view = SearchResultView(
    gspread_client=client.gspread_client,
    author=interaction.user,
    message=message,
    summary_df=my_factors,
    conditions={},
    factor_dictionary=factor_dictionary,
    character_data=character_data,
    score_sheets=score_sheets,
    character_list_sorted=character_list_sorted
)
        await message.edit(content=f"**{len(my_factors)}件**の因子が見つかりましたわ。", embed=view.create_embed(), view=view)
    except Exception as e:
        print(f"マイ倉庫の表示中にエラーが発生: {e}"); traceback.print_exc()
        await interaction.followup.send(f"エラーが発生いたしましたわ。\n`{e}`", ephemeral=True)

@app_commands.command(name="recalculate", description="【管理者用】全ての因子のスコアを、最新の採点簿で再計算いたしますわ。")
async def recalculate(interaction: Interaction):
    if interaction.user.id not in config.ADMIN_USER_IDS: return await interaction.response.send_message("エラーですわ: このコマンドは管理者の方しかお使いになれませんの。", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    client: FactorBotClient = interaction.client
    try:
        count = database.recalculate_all_scores(client.gspread_client, score_sheets)
        await interaction.followup.send(f"{count}件の因子のスコアを再計算いたしましたわ。", ephemeral=True)
    except Exception as e:
        print(f"スコア再計算中にエラーが発生: {e}"); traceback.print_exc()
        await interaction.followup.send(f"エラーが発生いたしましたわ。\n`{e}`", ephemeral=True)

@app_commands.command(name="ranking", description="指定された採点簿の、サーバー内ハイスコアランキングを表示いたしますわ。")
@app_commands.describe(score_sheet_name="ランキングをご覧になりたいスコアシートの名前ですの")
@app_commands.autocomplete(score_sheet_name=score_sheet_autocompleter)
async def ranking(interaction: Interaction, score_sheet_name: str):
    await interaction.response.defer(ephemeral=True)
    client: FactorBotClient = interaction.client
    try:
        summary_df, _ = database.get_full_database(client.gspread_client)
        score_col = f"合計({score_sheet_name})"
        if summary_df.empty or score_col not in summary_df.columns:
            return await interaction.followup.send(f"`{score_sheet_name}`のランキングデータは、まだ存在しないようですわ。", ephemeral=True)

        server_ids = {str(m.id) for m in interaction.guild.members}
        
        if '所有者ID' in summary_df.columns:
            summary_df['所有者ID'] = summary_df['所有者ID'].astype(str).str.strip()
            ranking_df = summary_df[summary_df['所有者ID'].isin(server_ids)].copy()
        else:
            ranking_df = pd.DataFrame() 

        if ranking_df.empty: return await interaction.followup.send(f"`{score_sheet_name}`のランキングデータは、まだ存在しないようですわ。", ephemeral=True)

        ranking_df[score_col] = pd.to_numeric(ranking_df[score_col], errors='coerce')
        ranking_df.dropna(subset=[score_col], inplace=True)
        ranking_df = ranking_df.sort_values(by=score_col, ascending=False).drop_duplicates(subset=['所有者ID'], keep='first')
        
        if ranking_df.empty: return await interaction.followup.send(f"`{score_sheet_name}`のランキングデータは、まだ存在しないようですわ。", ephemeral=True)

        view = RankingView(interaction.user, ranking_df.head(10), score_sheet_name, factor_dictionary)
        await interaction.followup.send(embed=view.create_embed(), view=view, ephemeral=True)
    except Exception as e:
        print(f"ランキング表示エラー: {e}"); traceback.print_exc()
        await interaction.followup.send(f"エラーですわ: {e}", ephemeral=True)

@app_commands.command(name="whoami", description="【デバッグ用】あなたご自身のDiscord情報を表示いたしますわ。")
async def whoami(interaction: Interaction):
    user = interaction.user
    await interaction.response.send_message(f"あらあら、コマンドを実行したのはあなたですのね。\n**お名前:** {user.name}\n**表示名:** {user.display_name}\n**ID:** `{user.id}`", ephemeral=True)

@app_commands.command(name="setowner", description="【修正用】因子の所有者を強制的に設定いたしますわ。")
@app_commands.describe(individual_id="所有者を設定したい因子の個体IDですの", user="新しい所有者になさりたいサーバーメンバーの方ですわ")
async def setowner(interaction: Interaction, individual_id: str, user: discord.Member):
    client: FactorBotClient = interaction.client
    await interaction.response.defer(ephemeral=True)
    try:
        success = database.update_owner(client.gspread_client, individual_id, user)
        if success:
            await interaction.followup.send(f"ふふっ、個体ID `{individual_id}` の新しいトレーナーは **{user.display_name}** さんですのね♪ 承知いたしましたわ。", ephemeral=True)
        else:
            await interaction.followup.send("その個体IDの因子は見つかりませんでしたわ。", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"エラーが発生いたしましたわ: {e}", ephemeral=True)

# --- Bot本体の定義 ---
class FactorBotClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.gspread_client = None
        self.active_search_views = {}

    async def upload_image_to_log_channel(self, interaction: Interaction, image_path: str, character_name: str, original_url: str):
        if config.FACTOR_LOG_CHANNEL_ID:
            log_channel = self.get_channel(config.FACTOR_LOG_CHANNEL_ID)
            if log_channel:
                try:
                    log_message = await log_channel.send(f"因子登録: {interaction.user.display_name} / {character_name}", file=discord.File(image_path))
                    print(f"画像をログチャンネルに保存しといたで: {log_message.attachments[0].url}")
                    return log_message.attachments[0].url
                except Exception as e:
                    print(f"ログチャンネルへの画像投稿に失敗したわ: {e}")
            else:
                print(f"エラーや: ログチャンネル(ID: {config.FACTOR_LOG_CHANNEL_ID})が見つからへんわ。")
        return original_url

    async def check_rank_in(self, interaction: Interaction, gspread_client, individual_id: str, author: discord.User):
        try:
            summary_df, factors_df = database.get_full_database(gspread_client)
            if summary_df.empty or factors_df.empty: return

            target_row = summary_df[summary_df['個体ID'] == individual_id]
            if target_row.empty: return
            character_name = target_row.iloc[0]['キャラ名']
            
            target_factors = factors_df[factors_df['個体ID'] == individual_id]
            if target_factors.empty: return
            factor_details = [{'id': str(row['因子ID']), 'stars': int(row['星の数'])} for _, row in target_factors.iterrows()]

            new_factor_scores = { s_name: sum(s_sheet.get(f['id'], 0) * f['stars'] for f in factor_details) for s_name, s_sheet in score_sheets.items() }

            notification_messages = []
            for sheet_name, new_score in new_factor_scores.items():
                if new_score <= 0: continue
                score_col = f"合計({sheet_name})"
                if score_col not in summary_df.columns: continue

                summary_df[score_col] = pd.to_numeric(summary_df[score_col], errors='coerce').fillna(0)
                
                my_other_scores = summary_df[(summary_df['所有者ID'] == str(author.id)) & (summary_df['個体ID'] != individual_id)][score_col]
                my_current_best = 0
                if not my_other_scores.empty: my_current_best = my_other_scores.max()

                other_scores = summary_df[summary_df['所有者ID'] != str(author.id)][score_col].tolist()
                
                all_scores_sorted = sorted(other_scores + [new_score], reverse=True)
                my_rank = all_scores_sorted.index(new_score) + 1

                if new_score > my_current_best and my_rank <= 3:
                    rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}
                    message = f"{rank_emojis.get(my_rank, '')} **{sheet_name}** でサーバー内**{my_rank}位**にランクインですわ！おめでとうございます♪ (スコア: `{new_score}点`)"
                    notification_messages.append(message)

            if notification_messages:
                embed = Embed(
                    title="🏆 ランキング更新通知 🏆",
                    description=f"**{author.display_name}**さんの**{character_name}**がハイスコアを記録なさいました！\n\n" + "\n".join(notification_messages),
                    color=Color.gold()
                )
                if config.RANKING_NOTIFICATION_CHANNEL_ID:
                    notification_channel = self.get_channel(config.RANKING_NOTIFICATION_CHANNEL_ID)
                    if notification_channel: await notification_channel.send(embed=embed)
                else:
                    await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"ランキング通知のチェック中にエラー: {e}")
            traceback.print_exc()

    async def save_parent_factors_to_db(self, individual_id: str, p1_factor_id: str, p1_stars: str, p2_factor_id: str, p2_stars: str):
        try:
            return database.save_parent_factors(self.gspread_client, individual_id, p1_factor_id, p1_stars, p2_factor_id, p2_stars)
        except Exception as e:
            print(f"DB保存中にエラーが発生: {e}")
            traceback.print_exc()
            return False 

    async def delete_factor_by_id(self, gspread_client, individual_id: str, user_id: int, is_admin: bool):
        """UIからの呼び出しを受け、データベースの削除関数を実行する"""
        try:
            # database.pyに追加した関数を呼び出す
            return database.delete_factor_by_id(gspread_client, individual_id, user_id, is_admin)
        except Exception as e:
            print(f"delete_factor_by_idの呼び出し中にエラー: {e}")
            traceback.print_exc()
            return False, "削除処理の呼び出し中に予期せぬエラーが発生しました。"           

    async def setup_hook(self):
        self.tree.add_command(evaluate)
        self.tree.add_command(debug_evaluate)
        self.tree.add_command(search_factors_command)
        self.tree.add_command(mybox)
        self.tree.add_command(recalculate)
        self.tree.add_command(ranking)
        self.tree.add_command(whoami)
        self.tree.add_command(setowner)
        
        await self.tree.sync()
        print(f"全 {len(self.tree.get_commands())} 個のコマンドを同期しといたで。")

    async def on_ready(self):
        global factor_dictionary, factor_name_to_id, score_sheets, character_data, char_name_to_id, character_list_sorted

        print(f'{self.user} としてログインしたで')
        try:
            print("Google SpreadSheetに接続しにいくで...");
            
            import json
            gspread_credentials_json = os.environ.get('GSPREAD_CREDENTIALS')

            if not gspread_credentials_json:
                print("エラーや: Google認証情報が環境変数に設定されとらへんわ。")
                return

            gspread_credentials = json.loads(gspread_credentials_json)
            self.gspread_client = gspread.service_account_from_dict(gspread_credentials)

            print("データベースの読み込み、始めるで..."); 
            
            factor_dictionary, factor_name_to_id, character_data, char_name_to_id, character_list_sorted = database.load_factor_dictionaries(self.gspread_client)
            score_sheets = database.load_score_sheets_by_id(self.gspread_client, factor_name_to_id)

            print("データベースの読み込み完了や。いつでもいけるで。")
        
        except Exception as e:
            print(f"起動んときにヤバいエラーが出てもうた: {e}\n主要機能は動かへんかもしれんわ。"); 
            traceback.print_exc()



async def check_rank_in(interaction: discord.Interaction, gspread_client, individual_id: str, author: discord.User, score_sheets: dict, character_data: dict):
    try:
        spreadsheet = gspread_client.open("因子評価データベース")
        summary_sheet = spreadsheet.worksheet("評価サマリー")
        factors_sheet = spreadsheet.worksheet("因子データ")

        summary_df = pd.DataFrame(summary_sheet.get_all_records(numericise_ignore=['all']))
        target_row = summary_df[summary_df['個体ID'] == individual_id]
        if target_row.empty: return
        character_name = target_row.iloc[0]['キャラ名']
        
        factor_rows = pd.DataFrame(factors_sheet.get_all_records(numericise_ignore=['all']))
        target_factors = factor_rows[factor_rows['個体ID'] == individual_id]
        if target_factors.empty: return
        
        factor_details = [{'id': str(row['因子ID']), 'stars': int(row['星の数'])} for _, row in target_factors.iterrows()]

        new_factor_scores = {
            s_name: sum(s_sheet.get(f['id'], 0) * f['stars'] for f in factor_details)
            for s_name, s_sheet in score_sheets.items()
        }

        notification_messages = []

        for sheet_name, new_score in new_factor_scores.items():
            if new_score <= 0: continue
            score_col = f"合計({sheet_name})"
            if score_col not in summary_df.columns: continue

            summary_df[score_col] = pd.to_numeric(summary_df[score_col], errors='coerce').fillna(0)
            
            # サーバー内メンバーのIDリストを取得
            server_ids = {str(m.id) for m in interaction.guild.members}
            server_summary = summary_df[summary_df['所有者ID'].isin(server_ids)]

            my_other_scores = server_summary[(server_summary['所有者ID'] == str(author.id)) & (server_summary['個体ID'] != individual_id)][score_col]
            my_current_best = 0
            if not my_other_scores.empty:
                my_current_best = my_other_scores.max()
            
            # ランキングは、各ユーザーの最高得点の因子のみを対象にする
            ranking_df = server_summary.sort_values(score_col, ascending=False).drop_duplicates(subset=['所有者ID'], keep='first')
            
            all_scores_sorted = sorted(ranking_df[score_col].tolist(), reverse=True)
            
            # 新スコアが既存のランキングに含まれているか
            if new_score in all_scores_sorted:
                my_rank = all_scores_sorted.index(new_score) + 1
            else: # 含まれていない場合、暫定のランキングを作成
                temp_ranking = sorted(all_scores_sorted + [new_score], reverse=True)
                my_rank = temp_ranking.index(new_score) + 1

            if new_score > my_current_best and my_rank <= 3:
                rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉"}
                message = f"{rank_emojis[my_rank]} **{sheet_name}** でサーバー内**{my_rank}位**にランクインですわ！ (スコア: `{new_score}点`)"
                notification_messages.append(message)

        if notification_messages:
            char_name_for_thumb = character_data.get(char_name_to_id.get(character_name, ''), {}).get('name', character_name)
            char_id = char_name_to_id.get(char_name_for_thumb)
            thumbnail = character_data.get(char_id, {}).get('thumbnail_url')

            embed = discord.Embed(
                title="🏆 ランキング更新通知 🏆",
                description=f"**{author.display_name}**さんの**{character_name}**がハイスコアを記録なさいました！\n\n" + "\n".join(notification_messages),
                color=discord.Color.gold()
            )
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)

            if config.RANKING_NOTIFICATION_CHANNEL_ID:
                notification_channel = interaction.client.get_channel(config.RANKING_NOTIFICATION_CHANNEL_ID)
                if notification_channel:
                    await notification_channel.send(embed=embed)
                else:
                    print(f"エラーや: ランキング通知チャンネル(ID: {config.RANKING_NOTIFICATION_CHANNEL_ID})が見つからへんわ。")
            else:
                # フォローアップは一時的なメッセージなので、チャンネルがない場合は元のチャンネルに投稿する
                await interaction.channel.send(embed=embed)

    except Exception as e:
        print(f"ランキング通知のチェック中にエラー: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    TOKEN = os.environ.get('DISCORD_BOT_TOKEN') # Renderからトークンを読み込む
    if not TOKEN:
        print("エラーや: Discordボットのトークンが環境変数に設定されとらへんわ。")
    else:
        intents = discord.Intents.default()
        intents.members = True
        client = FactorBotClient(intents=intents)
        client.run(TOKEN) # 読み込んだTOKENで起動
