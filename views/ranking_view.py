import discord
from discord import ui, Color, ButtonStyle, Embed
import pandas as pd
import config
from .ui_helpers import create_themed_embed
# ✨ RankingBuilderViewを循環参照しないようにインポート
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .ranking_builder_view import RankingBuilderView
    from bot import FactorBotClient

class RankingView(ui.View):
    # ✨ 引数にbot_clientとbuilder_viewを追加
    def __init__(self, bot_client: "FactorBotClient", author, ranking_df: pd.DataFrame, sheet_name: str, factor_dictionary: dict, builder_view: "RankingBuilderView"):
        super().__init__(timeout=600)
        self.bot_client = bot_client
        self.author = author
        self.ranking_df = ranking_df.reset_index(drop=True)
        self.sheet_name = sheet_name
        self.factor_dictionary = factor_dictionary
        # ✨ builder_viewを保存しておく
        self.builder_view = builder_view
        self.current_index = 0
        self.update_components()

    def update_components(self):
        self.clear_items()
        total = len(self.ranking_df)
        # (ページ送りボタンの作成部分は変更なし)
        is_first_page = self.current_index == 0
        is_last_page = self.current_index >= total - 1
        first_btn = ui.Button(label="<<", style=ButtonStyle.secondary, disabled=is_first_page, custom_id="go_first", row=0)
        prev_btn = ui.Button(label="<", style=ButtonStyle.primary, disabled=is_first_page, custom_id="go_prev", row=0)
        page_label = ui.Button(label=f"{self.current_index + 1} / {total}", style=ButtonStyle.secondary, disabled=True, row=0)
        next_btn = ui.Button(label=">", style=ButtonStyle.primary, disabled=is_last_page, custom_id="go_next", row=0)
        last_btn = ui.Button(label=">>", style=ButtonStyle.secondary, disabled=is_last_page, custom_id="go_last", row=0)
        first_btn.callback = self.navigate_results
        prev_btn.callback = self.navigate_results
        next_btn.callback = self.navigate_results
        last_btn.callback = self.navigate_results
        self.add_item(first_btn); self.add_item(prev_btn); self.add_item(page_label); self.add_item(next_btn); self.add_item(last_btn)

        # ✨✨✨ 「条件の再指定」ボタンを追加！ ✨✨✨
        back_button = ui.Button(label="🔄 条件を再指定する", style=ButtonStyle.secondary, row=1)
        back_button.callback = self.back_to_builder
        self.add_item(back_button)

    # (create_embed と navigate_results は変更なし)
    def create_embed(self) -> Embed:
        if self.ranking_df.empty:
            return Embed(...)
        # (中身が長いので省略... この関数の中は変更せんでええで)
        top_ranks_text = []
        rank_emojis = ["🥇", "🥈", "🥉"]
        for i, row in self.ranking_df.head(5).iterrows():
            emoji = rank_emojis[i] if i < 3 else f"`{i+1}`位"
            owner_name = row.get('所有者メモ', row.get('投稿者名', '不明')).replace('サーバーメンバー: ', '')
            score = row.get(f"合計({self.sheet_name})", 'N/A')
            char_name = row.get('キャラ名', '不明')
            top_ranks_text.append(f"{emoji}: `{score}点` - {owner_name} ({char_name})")

        embed = Embed(
            title=f"{self.sheet_name} ハイスコアランキング",
            description="\n".join(top_ranks_text),
            color=Color.gold()
        )
        current_row = self.ranking_df.iloc[self.current_index]
        owner_name = current_row.get('所有者メモ', current_row.get('投稿者名', '不明')).replace('サーバーメンバー: ', '')
        score = current_row.get(f"合計({self.sheet_name})", 'N/A')
        char_name = current_row.get('キャラ名', '不明')

        embed.add_field(
            name=f"👑 現在表示中: {self.current_index + 1}位 👑",
            value=f"**所有者**: {owner_name}\n**スコア**: `{score}点`\n**対象ウマ娘**: {char_name}",
            inline=False
        )
        if '画像URL' in current_row and pd.notna(current_row.get('画像URL')) and current_row.get('画像URL'):
            embed.set_image(url=current_row.get('画像URL'))
        embed.set_footer(text=f"Request by {self.author.display_name}")
        embed.set_thumbnail(url=config.RANKING_THUMBNAIL_URL)
        return embed

    async def navigate_results(self, interaction: discord.Interaction):
        await interaction.response.defer()
        btn_id = interaction.data['custom_id']
        if btn_id == "go_first": self.current_index = 0
        elif btn_id == "go_prev": self.current_index = max(0, self.current_index - 1)
        elif btn_id == "go_next": self.current_index = min(len(self.ranking_df) - 1, self.current_index + 1)
        elif btn_id == "go_last": self.current_index = len(self.ranking_df) - 1
        self.update_components()
        await interaction.edit_original_response(embed=self.create_embed(), view=self)
        
    # ✨✨✨ ボタンが押された時の関数を新しく追加！ ✨✨✨
    async def back_to_builder(self, interaction: discord.Interaction):
        # 循環参照を避けるため、ここでインポートする
        from .ranking_builder_view import RankingBuilderView
        # 保存しておいた初期の選択肢リストを使って、新しい選択画面を作り直す
        new_builder_view = RankingBuilderView(
            self.bot_client,
            self.author,
            self.builder_view.all_usages,
            self.builder_view.all_score_sheets,
            self.factor_dictionary
        )
        # 今のメッセージを、新しい選択画面に書き換える
        await interaction.response.edit_message(
            content="下のメニューから、ランキングの条件を指定してくださいまし♪",
            embed=None,
            view=new_builder_view
        )