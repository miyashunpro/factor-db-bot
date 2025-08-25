import discord
from discord import ui, Interaction, ButtonStyle, TextStyle

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .main_view import SearchView
    from .browser_view import ItemBrowserView
    from ..register_view import SetOwnerView

class ExternalOwnerModal(ui.Modal, title="サーバー外の所有者情報"):
    def __init__(self, owner_view: 'SetOwnerView'):
        super().__init__()
        self.owner_view = owner_view
    owner_memo = ui.TextInput(label="所有者の名前やトレーナーID", placeholder="例: フレンドの〇〇 (トレID: ...)", required=True, style=TextStyle.paragraph)
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        success = await self.owner_view.update_db_owner("EXTERNAL", self.owner_memo.value)
        if success:
            await interaction.client.check_rank_in(interaction, self.owner_view.gspread_client, self.owner_view.individual_id, self.owner_view.author)
            await self.owner_view.show_details_editor(interaction, "ふふっ、新しい出会いですわね♪")

class FilterModal(ui.Modal):
    def __init__(self, browser_view: "ItemBrowserView"):
        super().__init__(title=f"{browser_view.item_type}で絞り込みますの")
        self.browser_view = browser_view
        self.filter_text = ui.TextInput(label=f"{browser_view.item_type}の名前の一部をどうぞ♪", placeholder="例: コーナー", required=True)
        self.add_item(self.filter_text)
    
    async def on_submit(self, interaction: Interaction):
        await self.browser_view.apply_filter(interaction, self.filter_text.value)

class OptionalSkillCountModal(ui.Modal, title="選択スキルの最低個数"):
    def __init__(self, parent_view: "SearchView", condition_to_add: dict):
        super().__init__()
        self.parent_view = parent_view
        self.condition_to_add = condition_to_add
        item_count = len(condition_to_add['items'])
        self.count = ui.TextInput(label=f"選択した{item_count}個のうち、最低いくつ必要ですか？", placeholder=f"1〜{item_count}", required=True)
        self.add_item(self.count)
        
    async def on_submit(self, interaction: Interaction):
        try:
            req_count = int(self.count.value)
            assert 1 <= req_count <= len(self.condition_to_add['items'])
            self.condition_to_add['count'] = req_count
            self.parent_view.add_condition(self.condition_to_add)
            await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)
        except (ValueError, AssertionError):
            await interaction.response.send_message("入力値が正しくありません。", ephemeral=True)

class ScoreSheetSelectView(ui.View):
    def __init__(self, parent_view: "SearchView"):
        super().__init__(timeout=180)
        self.parent_view = parent_view
        options = [discord.SelectOption(label=name, value=name) for name in self.parent_view.score_sheets.keys()]
        if not options:
            self.add_item(ui.Button(label="採点簿が登録されていませんわ", disabled=True))
            return
        self.select = ui.Select(placeholder="採点簿を選んでくださいまし♪", options=options[:25])
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
    async def select_callback(self, interaction: Interaction):
        sheet_name = self.select.values[0]
        await interaction.response.send_modal(ScoreInputModal(self.parent_view, sheet_name))

class ScoreInputModal(ui.Modal, title="最低スコアを入力"):
    score = ui.TextInput(label="この採点簿での最低合計スコア", placeholder="例: 150", required=True)
    def __init__(self, parent_view: "SearchView", sheet_name: str):
        super().__init__()
        self.parent_view = parent_view
        self.sheet_name = sheet_name

    async def on_submit(self, interaction: Interaction):
        try:
            score_value = int(self.score.value)
            self.parent_view.conditions['score'] = [{'type': 'score', 'sheet': self.sheet_name, 'score': score_value}]
            await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)
        except ValueError:
             await interaction.response.send_message("スコアは半角数字で入力してください。", ephemeral=True)