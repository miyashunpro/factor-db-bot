import discord
from discord import ui, Interaction, Embed, Color, ButtonStyle
import pandas as pd

import config
from ..ui_helpers import create_themed_embed

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .main_view import SearchView

class DeleteConfirmView(ui.View):
    def __init__(self, gspread_client, individual_id, original_view: 'SearchResultView', message: discord.WebhookMessage, factor_dictionary: dict):
        super().__init__(timeout=180)
        self.gspread_client = gspread_client
        self.individual_id = individual_id
        self.original_view = original_view
        self.message = message
        self.factor_dictionary = factor_dictionary
        
    @ui.button(label="はい、削除します", style=ButtonStyle.danger)
    async def confirm_delete(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer()
        is_admin = interaction.user.id in config.ADMIN_USER_IDS
        try:
            success, message = await interaction.client.delete_factor_by_id(self.gspread_client, self.individual_id, interaction.user.id, is_admin)
            if success:
                self.original_view.summary_df = self.original_view.summary_df[self.original_view.summary_df['個体ID'] != self.individual_id].reset_index(drop=True)
                if self.original_view.summary_df.empty:
                     await interaction.edit_original_response(content="因子を削除しました。検索結果は0件になりました。", embed=None, view=None)
                     return

                self.original_view.current_index = min(self.original_view.current_index, len(self.original_view.summary_df) - 1)
                self.original_view.update_components()
                await interaction.edit_original_response(content=f"個体ID `{self.individual_id}` の因子を削除しました。", embed=self.original_view.create_embed(), view=self.original_view)
            else:
                back_view = BackToResultsView(self.original_view)
                await interaction.edit_original_response(content=f"エラー: {message}", view=back_view, embed=None)

        except Exception as e:
            print(f"因子削除中にエラーが発生: {e}"); traceback.print_exc()
            await interaction.edit_original_response(content=f"エラーが発生しました: `{e}`", view=None, embed=None)
            
    @ui.button(label="いいえ、やめておきます", style=ButtonStyle.secondary)
    async def cancel_delete(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content=f"**{len(self.original_view.summary_df)}件**の因子が見つかりました。", 
            embed=self.original_view.create_embed(), 
            view=self.original_view
        )

class BackToResultsView(ui.View):
    def __init__(self, original_view: 'SearchResultView'):
        super().__init__(timeout=180)
        self.original_view = original_view

    @ui.button(label="検索結果に戻る", style=ButtonStyle.secondary)
    async def go_back(self, interaction: Interaction, button: ui.Button):
        # 元の検索結果画面を再表示する
        await interaction.response.edit_message(
            content=f"**{len(self.original_view.summary_df)}件**の因子が見つかりました。", 
            embed=self.original_view.create_embed(), 
            view=self.original_view
        )        

class SearchResultView(ui.View):
    def __init__(self, gspread_client, author, message: discord.WebhookMessage, summary_df: pd.DataFrame, conditions: dict, factor_dictionary: dict, character_data: dict, score_sheets: dict, character_list_sorted: list):
        super().__init__(timeout=600)
        self.gspread_client = gspread_client
        self.author = author
        self.message = message
        self.summary_df = summary_df.reset_index(drop=True)
        self.conditions = conditions
        self.factor_dictionary = factor_dictionary
        self.character_data = character_data
        self.score_sheets = score_sheets
        self.character_list_sorted = character_list_sorted
        self.current_index = 0
        self.update_components()

    def update_components(self):
        self.clear_items()
        if self.summary_df.empty:
            return

        total = len(self.summary_df)
        self.current_index = min(self.current_index, total - 1)
        is_first_page = self.current_index == 0
        is_last_page = self.current_index >= total - 1
        first_btn = ui.Button(label="<<", style=ButtonStyle.secondary, disabled=is_first_page, custom_id="go_first", row=0)
        prev_btn = ui.Button(label="<", style=ButtonStyle.primary, disabled=is_first_page, custom_id="go_prev", row=0)
        page_label = ui.Button(label=f"{self.current_index + 1} / {total}", style=ButtonStyle.secondary, disabled=True, row=0)
        next_btn = ui.Button(label=">", style=ButtonStyle.primary, disabled=is_last_page, custom_id="go_next", row=0)
        last_btn = ui.Button(label=">>", style=ButtonStyle.secondary, disabled=is_last_page, custom_id="go_last", row=0)
        first_btn.callback = self.navigate_results; prev_btn.callback = self.navigate_results; next_btn.callback = self.navigate_results; last_btn.callback = self.navigate_results
        self.add_item(first_btn); self.add_item(prev_btn); self.add_item(page_label); self.add_item(next_btn); self.add_item(last_btn)
        back_to_builder_btn = ui.Button(label="🔄 条件を編集する", style=ButtonStyle.secondary, row=1)
        back_to_builder_btn.callback = self.back_to_builder
        self.add_item(back_to_builder_btn)
        delete_btn = ui.Button(label="🗑️ この因子を削除", style=ButtonStyle.danger, row=1)
        delete_btn.callback = self.delete_callback
        self.add_item(delete_btn)

    def create_embed(self):
        if self.summary_df.empty:
            return create_themed_embed(
                title="検索結果なし",
                description="条件に一致する因子は見つかりませんでした。",
                footer_text=f"Request by {self.author.display_name}"
            )

        current_row = self.summary_df.iloc[self.current_index]
        char_name = current_row.get("キャラ名", "不明")
        owner_name = current_row.get('所有者メモ', current_row.get('投稿者名', '不明'))
        image_url = current_row.get("画像URL")
        individual_id = current_row.get("個体ID", "不明")

        owner_id = current_row.get("所有者ID", "")
        display_owner = owner_name.replace('サーバーメンバー: ', '')
        
        description = f"**{display_owner}** の **{char_name}**"

        embed = create_themed_embed(
            title=f"🍀 検索結果 ({self.current_index + 1}/{len(self.summary_df)})",
            description=description,
            footer_text=f"個体ID: {individual_id}"
        )

        if pd.notna(image_url) and image_url:
            embed.set_image(url=image_url)

        if owner_id == 'EXTERNAL':
            embed.add_field(name="🤝 提供者情報", value=f"```{owner_name}```", inline=False)

        score_info = []
        for sheet_name in self.score_sheets.keys():
            score_col = f"合計({sheet_name})"
            if score_col in current_row and pd.notna(current_row[score_col]):
                score = pd.to_numeric(current_row[score_col], errors='coerce')
                if pd.notna(score) and score > 0:
                    score_info.append(f"**{sheet_name}**: `{int(score)}`点")
        
        if score_info:
            embed.add_field(name="📊 スコア", value="\n".join(score_info), inline=False)

        # ★★★ ここが修正点 ★★★
        # 親因子の「ID」を取得し、辞書を使って「名前」に変換する
        p1_factor_id = current_row.get("親赤因子1_ID")
        p2_factor_id = current_row.get("親赤因子2_ID")
        
        p1_factor_name = self.factor_dictionary.get(str(p1_factor_id), {}).get('name', '')
        p2_factor_name = self.factor_dictionary.get(str(p2_factor_id), {}).get('name', '')

        p1_stars = current_row.get("親赤因子1_星数")
        p2_stars = current_row.get("親赤因子2_星数")

        if p1_factor_name and p2_factor_name:
            p1_stars_int = int(p1_stars or 0)
            p2_stars_int = int(p2_stars or 0)
            parent_info = (
                f"**親1**: `{p1_factor_name}` (★{p1_stars_int})\n"
                f"**親2**: `{p2_factor_name}` (★{p2_stars_int})"
            )
            embed.add_field(name="👨‍👩‍👧 親の赤因子", value=parent_info, inline=False)
        # ★★★ 修正はここまで ★★★

        # 用途とレースローテも追加
        usage = current_row.get("用途")
        if pd.notna(usage) and usage:
            embed.add_field(name="🎯 用途", value=usage, inline=True)
        
        race_route = current_row.get("レースローテ")
        if pd.notna(race_route) and race_route:
            embed.add_field(name="🏃‍♀️ ローテ", value=race_route, inline=True)

        memo = current_row.get("メモ")
        if pd.notna(memo) and memo:
            embed.add_field(name="📝 メモ", value=f"```{memo}```", inline=False)    
        
        return embed
    
    async def navigate_results(self, interaction: discord.Interaction):
        await interaction.response.defer()
        btn_id = interaction.data['custom_id']
        if btn_id == "go_first": self.current_index = 0
        elif btn_id == "go_prev": self.current_index = max(0, self.current_index - 1)
        elif btn_id == "go_next": self.current_index = min(len(self.summary_df) - 1, self.current_index + 1)
        elif btn_id == "go_last": self.current_index = len(self.summary_df) - 1
        
        self.update_components()
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

    async def delete_callback(self, interaction: Interaction):
        current_row = self.summary_df.iloc[self.current_index]
        individual_id = current_row['個体ID']
        image_url = current_row.get('画像URL')
        embed = Embed(title="削除の最終確認", description="本当にお別れしますの…？ この出会いも、きっと何かの縁ですのに…\nこの操作は元に戻せませんのよ…？", color=Color.red())
        if pd.notna(image_url) and image_url: embed.set_image(url=image_url)
        embed.set_footer(text=f"対象ID: {individual_id}")
        
        confirm_view = DeleteConfirmView(self.gspread_client, individual_id, self, self.message, self.factor_dictionary)
        await interaction.response.edit_message(embed=embed, view=confirm_view)

    async def back_to_builder(self, interaction: discord.Interaction):
        from .main_view import SearchView
        await interaction.response.defer()
        builder_view = SearchView(self.gspread_client, self.author, self.message, self.factor_dictionary, self.character_data, self.score_sheets, self.character_list_sorted, self.conditions)
        await interaction.edit_original_response(content=None, embed=builder_view.create_embed(), view=builder_view)        