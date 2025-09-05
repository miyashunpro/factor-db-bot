import discord
from discord import ui
import pandas as pd
import traceback
from .ranking_view import RankingView
import database

# 循環参照を避けるための書き方
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from bot import FactorBotClient

class RankingBuilderView(ui.View):
    def __init__(self, bot_client: "FactorBotClient", author: discord.User, all_usages: list, all_score_sheets: list, factor_dictionary: dict, selected_usage: str = None, selected_sheet: str = None):
        super().__init__(timeout=600)
        self.bot_client = bot_client
        self.author = author
        self.all_usages = all_usages
        self.all_score_sheets = all_score_sheets
        self.factor_dictionary = factor_dictionary
        self.selected_usage = selected_usage
        self.selected_sheet = selected_sheet

        # --- ドロップダウンの作成部分 ---
        # 用途の選択肢を作成
        usage_options = [discord.SelectOption(label="すべての用途", value="*all", default=(self.selected_usage == "*all"))]
        for usage in self.all_usages[:24]:
            usage_options.append(discord.SelectOption(label=usage, default=(self.selected_usage == usage)))
        
        self.usage_select = ui.Select(placeholder="1. 絞り込みたい用途を選択", options=usage_options)
        self.usage_select.callback = self.on_select
        self.add_item(self.usage_select)

        # 採点簿の選択肢を作成
        sheet_options = []
        for sheet in self.all_score_sheets[:25]:
            sheet_options.append(discord.SelectOption(label=sheet, default=(self.selected_sheet == sheet)))

        self.sheet_select = ui.Select(placeholder="2. ランキングの基準になる採点簿を選択", options=sheet_options)
        self.sheet_select.callback = self.on_select
        self.add_item(self.sheet_select)

        # --- 実行ボタン ---
        self.confirm_button = ui.Button(label="🍀 ランキングを表示", style=discord.ButtonStyle.success, disabled=not (self.selected_usage and self.selected_sheet))
        self.confirm_button.callback = self.on_confirm
        self.add_item(self.confirm_button)

    async def on_select(self, interaction: discord.Interaction):
        # どのドロップダウンが操作されたか特定し、値を取得
        select_id = interaction.data['custom_id']
        selected_value = interaction.data['values'][0]

        if select_id == self.usage_select.custom_id:
            new_selected_usage = selected_value
            new_selected_sheet = self.selected_sheet
        else: # sheet_select.custom_id
            new_selected_usage = self.selected_usage
            new_selected_sheet = selected_value

        # ✨✨✨ 新しい選択状態を持ったViewを、作り直す！ ✨✨✨
        new_view = RankingBuilderView(
            self.bot_client,
            self.author,
            self.all_usages,
            self.all_score_sheets,
            self.factor_dictionary,
            selected_usage=new_selected_usage,
            selected_sheet=new_selected_sheet
        )
        # メッセージを、新しく作ったViewに差し替える
        await interaction.response.edit_message(view=new_view)

    # on_confirm関数は変更なし
    async def on_confirm(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            summary_df, _ = database.get_full_database(self.bot_client.gspread_client)
            target_df = summary_df.copy()
            if self.selected_usage != "*all":
                target_df = target_df[target_df['用途'] == self.selected_usage]
            if target_df.empty:
                return await interaction.followup.send(f"「{self.selected_usage}」の用途が設定された因子は見つかりませんでしたわ。", ephemeral=True)
            score_col = f"合計({self.selected_sheet})"
            if score_col not in target_df.columns:
                return await interaction.followup.send(f"「{self.selected_sheet}」のスコアデータが存在しないようですわ。", ephemeral=True)
            target_df[score_col] = pd.to_numeric(target_df[score_col], errors='coerce')
            target_df.dropna(subset=[score_col], inplace=True)
            ranking_df = target_df.sort_values(by=score_col, ascending=False)
            server_ids = {str(m.id) for m in interaction.guild.members}
            ranking_df = ranking_df[ranking_df['所有者ID'].isin(server_ids)]
            ranking_df.drop_duplicates(subset=['所有者ID'], keep='first', inplace=True)
            if ranking_df.empty:
                return await interaction.followup.send("条件に一致するランキングデータが見つかりませんでしたわ。", ephemeral=True)

            view = RankingView(self.bot_client, self.author, ranking_df.head(20), self.selected_sheet, self.factor_dictionary, self)
            await interaction.edit_original_response(content=None, embed=view.create_embed(), view=view)
        except Exception as e:
            await interaction.edit_original_response(content=f"ランキングの表示中にエラーが発生しました: {e}", view=None, embed=None)
            traceback.print_exc()