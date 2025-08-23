import discord
from discord import ui, Interaction, Embed, Color, ButtonStyle, TextStyle
import pandas as pd
import math
from collections import defaultdict
import traceback
import gspread

# 他の自作ファイルをimport
import config
import image_processor

# --- ヘルパー関数 ---
def create_themed_embed(title: str, description: str, footer_text: str = None, thumbnail_url: str = None):
    THEME_COLOR = discord.Color(0x57F287) 
    AUTHOR_NAME = "因子DB"
    embed = discord.Embed(title=title, description=description, color=THEME_COLOR)
    embed.set_author(name=AUTHOR_NAME, icon_url=config.AUTHOR_ICON_URL)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if footer_text:
        embed.set_footer(text=footer_text)
    return embed

# --- UIクラス定義 ---

class ParentFactorEditView(ui.View):
    def __init__(self, gspread_client, individual_id: str, author: discord.User, original_embed: Embed, factor_dictionary: dict):
        super().__init__(timeout=600)
        self.gspread_client = gspread_client
        self.individual_id = individual_id
        self.author = author
        self.original_embed = original_embed
        self.factor_dictionary = factor_dictionary
        self.selections = {"p1_factor": None, "p1_stars": None, "p2_factor": None, "p2_stars": None}

        red_factor_options = [discord.SelectOption(label=finfo['name'], value=fid) for fid, finfo in self.factor_dictionary.items() if finfo['type'] == '赤因子']
        if len(red_factor_options) > 25: red_factor_options = red_factor_options[:25]
        star_options = [discord.SelectOption(label=f"★{i}", value=str(i)) for i in range(1, 4)]
        
        p1_factor_select = ui.Select(placeholder="親1の赤因子を選択", options=red_factor_options, row=0)
        p1_factor_select.callback = self.p1_factor_callback
        self.add_item(p1_factor_select)

        p1_stars_select = ui.Select(placeholder="親1の星数を選択", options=star_options, row=1)
        p1_stars_select.callback = self.p1_stars_callback
        self.add_item(p1_stars_select)

        p2_factor_select = ui.Select(placeholder="親2の赤因子を選択", options=red_factor_options, row=2)
        p2_factor_select.callback = self.p2_factor_callback
        self.add_item(p2_factor_select)

        p2_stars_select = ui.Select(placeholder="親2の星数を選択", options=star_options, row=3)
        p2_stars_select.callback = self.p2_stars_callback
        self.add_item(p2_stars_select)

    async def p1_factor_callback(self, interaction: Interaction):
        self.selections["p1_factor"] = interaction.data['values'][0]
        await interaction.response.defer()
    async def p1_stars_callback(self, interaction: Interaction):
        self.selections["p1_stars"] = interaction.data['values'][0]
        await interaction.response.defer()
    async def p2_factor_callback(self, interaction: Interaction):
        self.selections["p2_factor"] = interaction.data['values'][0]
        await interaction.response.defer()
    async def p2_stars_callback(self, interaction: Interaction):
        self.selections["p2_stars"] = interaction.data['values'][0]
        await interaction.response.defer()

    @ui.button(label="✅ 保存する", style=ButtonStyle.success, row=4)
    async def execute_save_button(self, interaction: Interaction, button: ui.Button):
        if not all(self.selections.values()):
            await interaction.response.send_message("エラー: 親1と親2、両方の情報を設定してください。", ephemeral=True, delete_after=10)
            return

        button.disabled = True
        await interaction.response.edit_message(content="データベースに保存中です…", view=self)
        
        client = interaction.client
        success = await client.save_parent_factors_to_db(
            individual_id=self.individual_id,
            p1_factor_id=self.selections["p1_factor"],
            p1_stars=self.selections["p1_stars"],
            p2_factor_id=self.selections["p2_factor"],
            p2_stars=self.selections["p2_stars"]
        )

        if success:
            details_view = DetailsEditView(self.gspread_client, self.individual_id)
            await interaction.edit_original_response(
                content="✅ **親因子、確かにお預かりしましたわ！\n続けて、この子の詳細を教えてくださいますか？（任意）", 
                view=details_view, embeds=[self.original_embed]
            )
        else:
            await interaction.edit_original_response(content="エラー: データベースへの保存に失敗しました。", view=None, embeds=[])

class DetailsEditView(ui.View):
    def __init__(self, gspread_client, individual_id: str):
        super().__init__(timeout=600)
        self.gspread_client = gspread_client
        self.individual_id = individual_id
        self.purpose = None
        self.race_route = None
        self.memo = None

    @ui.select(placeholder="この因子の使い道を教えてくださいまし♪", row=1, options=[
        discord.SelectOption(label="レンタル/本育成用", value="レンタル/本育成用"),
        discord.SelectOption(label="親用", value="親用"),
        discord.SelectOption(label="祖父母用", value="祖父母用"),
        discord.SelectOption(label="祖親用(レンタル用など)", value="祖親用"),
        discord.SelectOption(label="その他", value="その他"),
    ])
    async def purpose_select_callback(self, interaction: Interaction, select: ui.Select):
        self.purpose = select.values[0]
        await interaction.response.defer()

    @ui.select(placeholder="この因子のローテを教えてくださいまし♪", row=2, options=[
        discord.SelectOption(label="クラシック三冠(芝)", value="クラシック三冠(芝)"),
        discord.SelectOption(label="クラシック三冠(ダート)", value="クラシック三冠(ダート)"),
        discord.SelectOption(label="ティアラ路線(牝馬三冠)", value="ティアラ路線"),
        discord.SelectOption(label="ダート牝馬路線", value="ダート牝馬路線"),
        discord.SelectOption(label="その他", value="その他"),
    ])
    async def race_route_select_callback(self, interaction: Interaction, select: ui.Select):
        self.race_route = select.values[0]
        await interaction.response.defer()

    @ui.button(label="📝 メモを編集", style=ButtonStyle.secondary, row=3)
    async def memo_button_callback(self, interaction: Interaction, button: ui.Button):
        class MemoModal(ui.Modal, title="メモの入力"):
            memo_input = ui.TextInput(
                label="トレーナーIDなど、ご自由にどうぞ♪", style=TextStyle.paragraph, placeholder="トレーナーIDなどを記入できます",
                required=False, max_length=500
            )
            def __init__(self, view: 'DetailsEditView'):
                super().__init__()
                self.view = view
                self.memo_input.default = self.view.memo
            async def on_submit(self, modal_interaction: Interaction):
                self.view.memo = self.memo_input.value
                await modal_interaction.response.send_message("ふふっ、素敵なメモですわね。確かにお預かりいたしました♪", ephemeral=True, delete_after=5)
        await interaction.response.send_modal(MemoModal(self))

    @ui.button(label="✅ 詳細を保存する", style=ButtonStyle.success, row=4)
    async def confirm_button_callback(self, interaction: Interaction, button: ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            spreadsheet = self.gspread_client.open("因子評価データベース")
            summary_sheet = spreadsheet.worksheet("評価サマリー")
            cell = summary_sheet.find(str(self.individual_id), in_column=1)
            
            if not cell:
                return await interaction.followup.send("エラー: 更新対象の因子が見つかりませんでした。", ephemeral=True)

            updates = {'用途': self.purpose, 'レースローテ': self.race_route, 'メモ': self.memo}
            headers = summary_sheet.row_values(1)
            cells_to_update = []
            
            for header, value in updates.items():
                if value is not None and header in headers:
                    col_index = headers.index(header) + 1
                    cells_to_update.append(gspread.Cell(row=cell.row, col=col_index, value=value))
            
            if cells_to_update:
                summary_sheet.update_cells(cells_to_update)

            await interaction.edit_original_response(content="✅ **詳細情報、確かに記録いたしました！**", view=None)

        except Exception as e:
            await interaction.followup.send(content=f"エラーが発生しました: {e}", ephemeral=True)
            traceback.print_exc()

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

class SetOwnerView(ui.View):
    def __init__(self, gspread_client, individual_id: str, author: discord.User, factor_dictionary: dict):
        super().__init__(timeout=600)
        self.gspread_client = gspread_client
        self.individual_id = individual_id
        self.author = author
        self.factor_dictionary = factor_dictionary

    async def update_db_owner(self, user_id: str, memo: str):
        try:
            spreadsheet = self.gspread_client.open("因子評価データベース")
            summary_sheet = spreadsheet.worksheet("評価サマリー")
            cell = summary_sheet.find(str(self.individual_id), in_column=1)
            if not cell: return False
            headers = summary_sheet.row_values(1)
            cells_to_update = []
            updates = {'所有者ID': user_id, '所有者メモ': memo}
            for header, value in updates.items():
                if header in headers:
                    col_index = headers.index(header) + 1
                    cells_to_update.append(gspread.Cell(row=cell.row, col=col_index, value=str(value)))
            if cells_to_update:
                summary_sheet.update_cells(cells_to_update)
            return True
        except Exception as e:
            print(f"DBオーナー更新中にエラー: {e}")
            traceback.print_exc()
            return False

    async def show_details_editor(self, interaction: Interaction, confirmation_message: str):
        original_embed = interaction.message.embeds[0]
        parent_factor_view = ParentFactorEditView(self.gspread_client, self.individual_id, self.author, original_embed, self.factor_dictionary)
        
        await interaction.edit_original_response(
            content=f"✅ **{confirmation_message}**\n続けて、**親の赤因子**を入力してください。これは必須ですの。", 
            embed=original_embed,
            view=parent_factor_view
        )
        
    @ui.button(label="所有者を自分に設定する", style=ButtonStyle.primary, row=0)
    async def set_self_callback(self, interaction: Interaction, button: ui.Button):
        author_user = self.author
        await interaction.response.defer()
        success = await self.update_db_owner(str(author_user.id), f"サーバーメンバー: {author_user.display_name}")
        if success:
            await interaction.client.check_rank_in(interaction, self.gspread_client, self.individual_id, author_user)
            await self.show_details_editor(interaction, "まあ！この子のトレーナーは、あなたですのね♪")
        else:
            await interaction.edit_original_response(content="エラー: 所有者の設定に失敗しました。", view=None)

    @ui.select(cls=ui.UserSelect, placeholder="サーバー内の他メンバーを所有者に設定", row=1)
    async def user_select_callback(self, interaction: Interaction, select: ui.UserSelect):
        await interaction.response.defer()
        selected_user = select.values[0]
        success = await self.update_db_owner(str(selected_user.id), f"サーバーメンバー: {selected_user.display_name}")
        if success:
            await interaction.client.check_rank_in(interaction, self.gspread_client, self.individual_id, selected_user)
            await self.show_details_editor(interaction, f"まあ！「{selected_user.display_name}」さんがトレーナーですのね♪")

    @ui.button(label="サーバー外の所有者情報を入力", style=ButtonStyle.secondary, row=2)
    async def set_external_callback(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(ExternalOwnerModal(self))

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

class ConditionEditorView(ui.View):
    def __init__(self, parent_view: "SearchView", condition: dict, factor_dictionary: dict):
        super().__init__(timeout=600)
        self.parent_view = parent_view
        self.factor_dictionary = factor_dictionary
        self.condition_type = condition['type']
        self.skill_cart = {item['id']: item.get('stars', 0) for item in condition['items']}
        self.pending_skill_id: str | None = None
        self.pending_stars: int | None = None
        self.embed = self.create_embed()
        self.build_view()

    def create_embed(self) -> Embed:
        title_prefix = '必須(AND)' if self.condition_type not in ['optional_skills', 'optional_genes'] else '選択(OR)'
        embed = Embed(title=f"スキル条件の設定 ({title_prefix})", color=Color.purple())
        description_lines = []
        if not self.skill_cart:
            description_lines.append("スキルが選択されていません。")
        else:
            description_lines.append("各スキルの最低星数を設定してください。")
            for i, (skill_id, stars) in enumerate(self.skill_cart.items()):
                skill_name = self.factor_dictionary.get(skill_id, {}).get('name', '不明なスキル')
                status = f"🟢 ★{stars} 以上" if stars > 0 else "**🔴 未設定**"
                description_lines.append(f"`{i+1}.` {skill_name} ({status})")
        embed.description = "\n".join(description_lines)
        return embed

    def build_view(self):
        self.clear_items()
        all_stars_set = all(s > 0 for s in self.skill_cart.values())
        if self.skill_cart:
            skill_options = [discord.SelectOption(label=f"{i+1}. {self.factor_dictionary.get(sid, {}).get('name', '不明')[:80]}", value=sid) for i, sid in enumerate(self.skill_cart.keys())]
            if len(skill_options) > 25: skill_options = skill_options[:25]
            skill_select = ui.Select(placeholder="1. 設定するスキルを選択", options=skill_options, row=0)
            skill_select.callback = self.on_skill_select
            self.add_item(skill_select)
            star_options = [discord.SelectOption(label=f"★{i} 以上", value=str(i)) for i in range(1, 4)]
            star_select = ui.Select(placeholder="2. 最低星数を選択", options=star_options, row=1)
            star_select.callback = self.on_star_select
            self.add_item(star_select)
            set_button = ui.Button(label="この内容で設定", style=ButtonStyle.primary, row=2)
            set_button.callback = self.apply_pending_settings
            self.add_item(set_button)
        confirm_button = ui.Button(label="✅ 設定を完了", style=ButtonStyle.success, row=3, disabled=not all_stars_set)
        confirm_button.callback = self.confirm_and_add_condition
        self.add_item(confirm_button)
        cancel_button = ui.Button(label="キャンセル", style=ButtonStyle.secondary, row=3)
        cancel_button.callback = self.cancel
        self.add_item(cancel_button)

    async def on_skill_select(self, interaction: Interaction):
        self.pending_skill_id = interaction.data['values'][0]
        await interaction.response.defer()

    async def on_star_select(self, interaction: Interaction):
        self.pending_stars = int(interaction.data['values'][0])
        await interaction.response.defer()

    async def apply_pending_settings(self, interaction: Interaction):
        if not self.pending_skill_id or not self.pending_stars:
            await interaction.response.send_message("スキルと星数の両方を選択してください。", ephemeral=True)
            return
        self.skill_cart[self.pending_skill_id] = self.pending_stars
        self.pending_skill_id = None
        self.pending_stars = None
        self.embed = self.create_embed()
        self.build_view()
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def confirm_and_add_condition(self, interaction: Interaction):
        items_with_stars = [{'id': sid, 'stars': s} for sid, s in self.skill_cart.items()]
        
        if self.condition_type not in ['optional_skills', 'optional_genes', 'characters', 'red_factors']:
            for item in items_with_stars:
                condition = {'type': self.condition_type, 'items': [item]}
                self.parent_view.add_condition(condition)
        else:
            condition = {'type': self.condition_type, 'items': items_with_stars}
            if self.condition_type in ['optional_skills', 'optional_genes']:
                await interaction.response.send_modal(OptionalSkillCountModal(self.parent_view, condition))
                return 
            else:
                self.parent_view.add_condition(condition)
        
        self.parent_view.skill_cart.clear()
        await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)
            
    async def cancel(self, interaction: Interaction):
        self.parent_view.skill_cart.clear()
        await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)

class ItemBrowserView(ui.View):
    def __init__(self, parent_view: "SearchView", item_type: str, condition_type: str, factor_dictionary: dict, character_data: dict, character_list_sorted: list):
        super().__init__(timeout=600)
        self.parent_view = parent_view
        self.item_type = item_type
        self.condition_type = condition_type
        self.factor_dictionary = factor_dictionary
        self.character_data = character_data
        self.character_list_sorted = character_list_sorted
        self.page = 0
        self.filtered_list = None
        
        if self.item_type == 'キャラ':
            self.full_item_list = self.character_list_sorted
            self.cart = self.parent_view.character_cart
        else:
            type_map = {
                '青因子': ['青因子'], '赤因子': ['赤因子'], '緑因子': ['緑因子'],
                '白因子': ['白因子'], 'シナリオ因子': ['シナリオ因子'],
                'レース因子': ['レース因子'], '遺伝子因子': ['遺伝子因子']
            }
            target_types = type_map.get(self.item_type, [])
            self.full_item_list = sorted(
                [(fid, finfo) for fid, finfo in self.factor_dictionary.items() if finfo['type'] in target_types],
                key=lambda item: item[1]['name']
            )
            self.cart = self.parent_view.skill_cart
        self.item_select: ui.Select 
        self.build_view()

    def get_current_list(self):
        return self.filtered_list if self.filtered_list is not None else self.full_item_list

    def create_browser_embed(self) -> Embed:
        embed = Embed(color=Color.blue())
        if self.item_type in ['白因子', '遺伝子因子', 'シナリオ因子', 'レース因子']:
            title_prefix = '必須(AND)' if 'required' in self.condition_type else '選択(OR)'
            embed.title = f"🍀 {self.item_type}の選択 ({title_prefix})"
        else:
            embed.title = f"🍀 {self.item_type}の選択"
        cart_ids = self.cart.keys()
        if cart_ids:
            cart_names = [self.factor_dictionary.get(fid, {}).get('name', '不明') for fid in cart_ids]
            embed.add_field(name=f"🍀 選択中の因子 ({len(cart_ids)}件)", value="```\n- " + "\n- ".join(cart_names) + "\n```", inline=False)
            embed.set_footer(text="リストから選ぶと、自動でカートに入ります。")
        else:
            embed.description = "下のリストから項目を選択してください。"
        return embed

    def build_view(self):
        self.clear_items()
        current_list = self.get_current_list()
        total_pages = max(1, math.ceil(len(current_list) / 25))
        self.page = max(0, min(self.page, total_pages - 1))
        
        is_first_page = self.page == 0
        is_last_page = self.page >= total_pages - 1

        first_btn = ui.Button(label="<<", style=ButtonStyle.secondary, disabled=is_first_page, custom_id="first", row=0)
        prev_btn = ui.Button(label="<", style=ButtonStyle.primary, disabled=is_first_page, custom_id="prev", row=0)
        page_label = ui.Button(label=f"{self.page + 1} / {total_pages}", style=ButtonStyle.secondary, disabled=True, row=0)
        next_btn = ui.Button(label=">", style=ButtonStyle.primary, disabled=is_last_page, custom_id="next", row=0)
        last_btn = ui.Button(label=">>", style=ButtonStyle.secondary, disabled=is_last_page, custom_id="last", row=0)
        
        first_btn.callback = self.navigate
        prev_btn.callback = self.navigate
        next_btn.callback = self.navigate
        last_btn.callback = self.navigate
        
        self.add_item(first_btn); self.add_item(prev_btn); self.add_item(page_label); self.add_item(next_btn); self.add_item(last_btn)

        start_index = self.page * 25
        options = [discord.SelectOption(label=item[1]['name'], value=item[0]) for item in current_list[start_index:(start_index + 25)]]
        
        if options:
            self.item_select = ui.Select(placeholder=f"ここから{self.item_type}を選択 (自動でカートに追加)", options=options, min_values=1, max_values=min(len(options), 25), row=1)
            self.item_select.callback = self.on_item_select
            self.add_item(self.item_select)
        else:
            self.add_item(ui.Button(label="一致する項目がありません", style=ButtonStyle.secondary, disabled=True, row=1))
        
        if self.cart:
            remove_options = [discord.SelectOption(label=self.factor_dictionary.get(fid,{}).get('name','不明'), value=fid) for fid in self.cart.keys()]
            if len(remove_options) > 25: remove_options = remove_options[:25]
            
            if remove_options:
                remove_select = ui.Select(placeholder="🍀 カートから外す因子を選択", options=remove_options, min_values=1, max_values=min(len(remove_options), 25), row=2)
                remove_select.callback = self.remove_from_cart
                self.add_item(remove_select)

        if self.item_type != 'キャラ':
            confirm_btn = ui.Button(label=f"➡️ 星数の設定に進む", style=ButtonStyle.primary, row=3, disabled=not self.cart)
            confirm_btn.callback = self.go_to_editor
            self.add_item(confirm_btn)
        else:
            confirm_btn = ui.Button(label=f"✅ この内容で確定", style=ButtonStyle.success, row=3, disabled=not self.cart)
            confirm_btn.callback = self.confirm_cart_selection
            self.add_item(confirm_btn)
        
        clear_cart_btn = ui.Button(label="🗑️ カートを空にする", style=ButtonStyle.danger, row=3, disabled=not self.cart)
        clear_cart_btn.callback = self.clear_cart
        self.add_item(clear_cart_btn)

        filter_btn = ui.Button(label="🔎 フィルタ", style=ButtonStyle.primary, row=4)
        filter_btn.callback = self.open_filter
        self.add_item(filter_btn)
        
        if self.filtered_list is not None:
            clear_filter_btn = ui.Button(label="フィルタ解除", style=ButtonStyle.secondary, row=4)
            clear_filter_btn.callback = self.clear_filter
            self.add_item(clear_filter_btn)
        
        back_btn = ui.Button(label="戻る", style=ButtonStyle.secondary, row=4)
        back_btn.callback = self.go_back
        self.add_item(back_btn)

    async def on_item_select(self, interaction: Interaction):
        for selected_id in interaction.data['values']:
            if selected_id not in self.cart:
                if self.item_type == 'キャラ': self.cart[selected_id] = None
                else: self.cart[selected_id] = 0
        self.build_view()
        await interaction.response.edit_message(embed=self.create_browser_embed(), view=self)

    async def remove_from_cart(self, interaction: Interaction):
        for selected_id in interaction.data['values']:
            if selected_id in self.cart: del self.cart[selected_id]
        self.build_view()
        await interaction.response.edit_message(embed=self.create_browser_embed(), view=self)

    async def clear_cart(self, interaction: Interaction):
        self.cart.clear()
        self.build_view()
        await interaction.response.edit_message(embed=self.create_browser_embed(), view=self)

    async def confirm_cart_selection(self, interaction: Interaction):
        if self.item_type == 'キャラ':
            selected_items = [{'id': char_id, 'name': self.character_data[char_id]['name']} for char_id in self.cart.keys()]
            self.parent_view.add_condition({'type': 'characters', 'items': selected_items})
        self.cart.clear()
        await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)

    async def go_to_editor(self, interaction: Interaction):
        if not self.cart: return await interaction.response.send_message("カートが空です。", ephemeral=True)
        condition = {
            'type': self.condition_type,
            'items': [{'id': sid, 'stars': s} for sid, s in self.cart.items()]
        }
        editor_view = ConditionEditorView(self.parent_view, condition, self.factor_dictionary)
        await interaction.response.edit_message(embed=editor_view.embed, view=editor_view)
    
    async def open_filter(self, interaction: Interaction): await interaction.response.send_modal(FilterModal(self))
    async def apply_filter(self, interaction: Interaction, text: str):
        self.filtered_list = [(item_id, item_info) for item_id, item_info in self.full_item_list if image_processor.normalize_text(text) in image_processor.normalize_text(item_info['name']) or text.lower() in item_id.lower()]
        self.page = 0
        self.build_view()
        await interaction.response.edit_message(view=self, embed=self.create_browser_embed())
    async def clear_filter(self, interaction: Interaction):
        self.filtered_list = None
        self.page = 0
        self.build_view()
        await interaction.response.edit_message(view=self, embed=self.create_browser_embed())
    async def navigate(self, interaction: Interaction):
        btn_id = interaction.data['custom_id']
        if btn_id == "first": self.page = 0
        elif btn_id == "prev": self.page -= 1
        elif btn_id == "next": self.page += 1
        elif btn_id == "last": self.page = max(0, math.ceil(len(self.get_current_list()) / 25) - 1)
        self.build_view()
        await interaction.response.edit_message(view=self)
    async def go_back(self, interaction: Interaction):
        self.cart.clear()
        await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)

class SingleFactorEditView(ui.View):
    def __init__(self, parent_view: "SearchView", condition_type: str, item_type: str):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.condition_type = condition_type
        self.item_type = item_type

        self.selected_factor_id = None
        self.selected_stars = None

        factor_options = [
            discord.SelectOption(label=finfo['name'], value=fid)
            for fid, finfo in self.parent_view.factor_dictionary.items() if finfo['type'] == self.item_type
        ]
        if len(factor_options) > 25: factor_options = factor_options[:25]
        star_options = [discord.SelectOption(label=f"★{i} 以上", value=str(i)) for i in range(1, 4)]

        factor_select = ui.Select(placeholder=f"1. {self.item_type}を選択", options=factor_options, row=0)
        factor_select.callback = self.on_factor_select
        self.add_item(factor_select)
        
        stars_select = ui.Select(placeholder="2. 最低星数を選択", options=star_options, row=1)
        stars_select.callback = self.on_stars_select
        self.add_item(stars_select)

    @ui.button(label="✅ この条件を追加", style=ButtonStyle.success, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_factor_id or not self.selected_stars:
            return await interaction.response.send_message("因子と星数、両方を選んでくださいまし♪", ephemeral=True, delete_after=5)

        new_condition = {
            'type': self.condition_type,
            'items': [{'id': self.selected_factor_id, 'stars': int(self.selected_stars)}]
        }
        
        self.parent_view.conditions[self.condition_type].append(new_condition)
        await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)

    @ui.button(label="❌ キャンセル", style=ButtonStyle.secondary, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)

    async def on_factor_select(self, interaction: discord.Interaction):
        self.selected_factor_id = interaction.data['values'][0]
        await interaction.response.defer()

    async def on_stars_select(self, interaction: discord.Interaction):
        self.selected_stars = interaction.data['values'][0]
        await interaction.response.defer()        

class SearchView(ui.View):
    def __init__(self, gspread_client, author, message: discord.WebhookMessage, factor_dictionary: dict, character_data: dict, score_sheets: dict, character_list_sorted: list, conditions=None):
        super().__init__(timeout=1200) 
        self.gspread_client = gspread_client
        self.author = author
        self.message = message
        self.factor_dictionary = factor_dictionary
        self.character_data = character_data
        self.score_sheets = score_sheets
        self.character_list_sorted = character_list_sorted
        self.conditions = conditions if conditions is not None else defaultdict(list)
        self.search_only_mine = False
        self.skill_cart = {} 
        self.character_cart = {}

    def create_embed(self):
        embed = create_themed_embed(
            title="🍀 因子検索ビルダー",
            description="下のボタンから、検索したい条件を追加してください♪",
            footer_text=f"Request by {self.author.display_name}",
            thumbnail_url=config.SEARCH_THUMBNAIL_URL
        )
        if self.conditions:
            conditions_blocks = []

            if self.conditions.get('characters'):
                names = "\n".join([f"- `{c['name']}`" for c in self.conditions['characters'][0]['items']])
                conditions_blocks.append(f"> **▼ 以下のキャラのいずれか**\n{names}")

            if self.conditions.get('red_factor_body'):
                body_conds = self.conditions['red_factor_body']
                body_names = [self.factor_dictionary.get(f['id'], {}).get('name', '不明') + f"(★{f['stars']})" for f in body_conds]
                conditions_blocks.append(f"**▼ 本体の赤因子 (OR)**\n- `{' / '.join(body_names)}`")
            if self.conditions.get('red_factor_parent'):
                parent_conds = self.conditions['red_factor_parent']
                parent_lines = [f"- `{self.factor_dictionary.get(f['id'], {}).get('name', '不明')} (合計★{f['stars']}以上)`" for f in parent_conds]
                conditions_blocks.append(f"**▼ 親の赤因子 (AND)**\n" + "\n".join(parent_lines))
            if self.conditions.get('red_factor_overall'):
                overall_conds = self.conditions['red_factor_overall']
                overall_lines = [f"- `{self.factor_dictionary.get(f['id'], {}).get('name', '不明')} (全体合計★{f['stars']}以上)`" for f in overall_conds]
                conditions_blocks.append(f"**▼ 全体の赤因子 (AND)**\n" + "\n".join(overall_lines))

            if self.conditions.get('blue_factors'):
                names_list = "\n".join([f"- `{self.factor_dictionary.get(c['items'][0]['id'], {}).get('name', '不明')}(★{c['items'][0]['stars']})`" for c in self.conditions['blue_factors']])
                conditions_blocks.append(f"> **▼ 以下の青因子のうち、どれか1つ以上**\n{names_list}")

            if self.conditions.get('green_factors'):
                all_green_factors = []
                for cond_group in self.conditions['green_factors']:
                    for item in cond_group['items']:
                         all_green_factors.append(f"- `{self.factor_dictionary.get(item['id'], {}).get('name', '不明')}(★{item['stars']})`")
                names_list = "\n".join(all_green_factors)
                conditions_blocks.append(f"> **▼ 以下の緑因子のうち、どれか1つ以上**\n{names_list}")

            if self.conditions.get('required_skills'):
                skill_list = "\n".join([f"- `{self.factor_dictionary.get(c['items'][0]['id'], {}).get('name', '不明')}(★{c['items'][0]['stars']})`" for c in self.conditions['required_skills']])
                conditions_blocks.append(f"> **▼ 以下の必須白スキルを、すべて満たす**\n{skill_list}")

            if self.conditions.get('optional_skills'):
                cond = self.conditions['optional_skills'][0]
                skill_list = "\n".join([f"- `{self.factor_dictionary.get(s['id'], {}).get('name', '不明')}(★{s['stars']})`" for s in cond['items']])
                count_text = f"**{cond.get('count', 1)}** 個以上"
                conditions_blocks.append(f"> **▼ 以下の選択白スキルのうち、{count_text}**\n{skill_list}")
            
            if self.conditions.get('required_genes'):
                skill_list = "\n".join([f"- `{self.factor_dictionary.get(c['items'][0]['id'], {}).get('name', '不明')}(★{c['items'][0]['stars']})`" for c in self.conditions['required_genes']])
                conditions_blocks.append(f"> **▼ 以下の必須遺伝子を、すべて満たす**\n{skill_list}")

            if self.conditions.get('optional_genes'):
                cond = self.conditions['optional_genes'][0]
                skill_list = "\n".join([f"- `{self.factor_dictionary.get(s['id'], {}).get('name', '不明')}(★{s['stars']})`" for s in cond['items']])
                count_text = f"**{cond.get('count', 1)}** 個以上"
                conditions_blocks.append(f"> **▼ 以下の選択遺伝子のうち、{count_text}**\n{skill_list}")

            if self.conditions.get('score'):
                score_texts = "\n".join([f"- `{s['sheet']}` シートで **{s['score']}** 点以上" for s in self.conditions['score']])
                conditions_blocks.append(f"> **▼ 以下のスコア条件を、すべて満たす**\n{score_texts}")
            
            if conditions_blocks:
                embed.add_field(name="🍀 現在の検索条件", value="\n\n".join(conditions_blocks), inline=False)

        return embed

    def add_condition(self, condition):
        if condition['type'] == 'characters':
            self.conditions[condition['type']] = [condition]
        else:
            self.conditions[condition['type']].append(condition)

    async def switch_to_browser(self, interaction: Interaction, item_type: str, condition_type: str):
        if item_type == 'キャラ':
            self.character_cart.clear()
        else:
            self.skill_cart.clear()
        browser_view = ItemBrowserView(self, item_type, condition_type, self.factor_dictionary, self.character_data, self.character_list_sorted)
        await interaction.response.edit_message(content=None, view=browser_view, embed=browser_view.create_browser_embed())

    @ui.button(label="キャラ名", style=ButtonStyle.secondary, row=0)
    async def add_character(self, interaction: Interaction, button: ui.Button):
        await self.switch_to_browser(interaction, 'キャラ', 'characters')
    
    @ui.button(label="スコア", style=ButtonStyle.secondary, row=0)
    async def add_score(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("採点簿を選択してください:", view=ScoreSheetSelectView(self), ephemeral=True)
    
    @ui.button(label="青因子", style=ButtonStyle.primary, row=1)
    async def add_blue_factor(self, interaction: Interaction, button: ui.Button):
        editor_view = SingleFactorEditView(self, 'blue_factors', '青因子')
        embed = discord.Embed(title="🍀 青因子を追加", description="条件に追加したい青因子と最低星数を選択してください。", color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=editor_view)

    @ui.button(label="赤因子", style=ButtonStyle.primary, row=1)
    async def add_red_factor(self, interaction: Interaction, button: ui.Button):
        editor_view = RedFactorEditorView(self, self.factor_dictionary)
        await interaction.response.edit_message(embed=editor_view.create_embed(), view=editor_view)

    @ui.button(label="緑因子", style=ButtonStyle.primary, row=1)
    async def add_green_factor(self, interaction: Interaction, button: ui.Button):
        await self.switch_to_browser(interaction, '緑因子', 'green_factors')

    @ui.button(label="必須白スキル", style=ButtonStyle.primary, row=2)
    async def add_required_white_factor(self, interaction: Interaction, button: ui.Button):
        await self.switch_to_browser(interaction, '白因子', 'required_skills')

    @ui.button(label="選択白スキル", style=ButtonStyle.primary, row=2)
    async def add_optional_white_factor(self, interaction: Interaction, button: ui.Button):
        await self.switch_to_browser(interaction, '白因子', 'optional_skills')
    
    @ui.button(label="必須遺伝子", style=ButtonStyle.secondary, row=3)
    async def add_required_gene_factor(self, interaction: discord.Interaction, button: discord.ui.Button):
        editor_view = SingleFactorEditView(self, 'required_genes', '遺伝子因子')
        embed = discord.Embed(title="🍀 必須遺伝子を追加", description="条件に追加したい遺伝子と最低星数を選択してください。", color=discord.Color.purple())
        await interaction.response.edit_message(embed=embed, view=editor_view)
    
    @ui.button(label="選択遺伝子", style=ButtonStyle.secondary, row=3)
    async def add_optional_gene_factor(self, interaction: Interaction, button: ui.Button):
        await self.switch_to_browser(interaction, '遺伝子因子', 'optional_genes')

    @ui.button(label="🗑️ 条件を削除", style=ButtonStyle.secondary, row=4)
    async def delete_condition_button(self, interaction: Interaction, button: ui.Button):
        if not self.conditions:
            return await interaction.response.send_message("あら、削除できる条件がありませんわ。", ephemeral=True, delete_after=5)
        delete_view = DeleteConditionView(self)
        embed = Embed(title="🗑️ 条件の削除", description="削除したい条件をリストから選択してください（複数選択できます）。", color=Color.orange())
        await interaction.response.edit_message(embed=embed, view=delete_view)
    
    @ui.button(label="自分の因子に絞り込む", style=ButtonStyle.secondary, row=4)
    async def toggle_search_scope(self, interaction: Interaction, button: ui.Button):
        self.search_only_mine = not self.search_only_mine
        if self.search_only_mine:
            button.label = "✅ 自分の因子のみ"
            button.style = ButtonStyle.success
        else:
            button.label = "自分の因子に絞り込む"
            button.style = ButtonStyle.secondary
        await interaction.response.edit_message(view=self)
    
    @ui.button(label="🍀 検索実行", style=ButtonStyle.success, row=4)
    async def execute_search(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.message.edit(content="データベースを検索中です…", view=None, embed=None)

        try:
            spreadsheet = self.gspread_client.open("因子評価データベース")
            summary_sheet = spreadsheet.worksheet("評価サマリー")
            factors_sheet = spreadsheet.worksheet("因子データ")
            summary_df = pd.DataFrame(summary_sheet.get_all_records(numericise_ignore=['all']))
            factors_df = pd.DataFrame(factors_sheet.get_all_records(numericise_ignore=['all']))
            if summary_df.empty:
                return await self.message.edit(content="あらあら、データベースにまだ因子が登録されていないようですわ。", view=None, embed=None)
            summary_df['個体ID'] = summary_df['個体ID'].astype(str)
            factors_df['個体ID'] = factors_df['個体ID'].astype(str)
            
            non_red_conditions = {k: v for k, v in self.conditions.items() if not k.startswith('red_factor')}
            valid_ids = set(summary_df['個体ID'])

            for cond_type, conditions in non_red_conditions.items():
                if not conditions or not valid_ids: continue
                if cond_type == 'characters':
                    char_names = [item['name'] for item in conditions[0]['items']]
                    char_ids = set(summary_df[summary_df['キャラ名'].isin(char_names)]['個体ID'])
                    valid_ids.intersection_update(char_ids)
                elif cond_type == 'score':
                    temp_summary = summary_df[summary_df['個体ID'].isin(valid_ids)].copy()
                    for cond in conditions:
                        score_col = f"合計({cond['sheet']})"
                        if score_col in temp_summary.columns:
                            temp_summary[score_col] = pd.to_numeric(temp_summary[score_col], errors='coerce').fillna(0)
                            temp_summary = temp_summary[temp_summary[score_col] >= cond['score']]
                    valid_ids.intersection_update(set(temp_summary['個体ID']))
                elif cond_type in ['blue_factors', 'green_factors']:
                    matched_ids_for_or_group = set()
                    for cond in conditions:
                        item = cond['items'][0]
                        factor_id = item['id']
                        min_stars = item['stars']
                        factor_match_df = factors_df[(factors_df['因子ID'] == factor_id) & (pd.to_numeric(factors_df['星の数'], errors='coerce').fillna(0) >= min_stars)]
                        matched_ids_for_or_group.update(set(factor_match_df['個体ID']))
                    valid_ids.intersection_update(matched_ids_for_or_group)
                elif cond_type in ['required_skills', 'required_genes']:
                    for cond in conditions:
                        item = cond['items'][0]
                        factor_id = item['id']
                        min_stars = item['stars']
                        factor_match_df = factors_df[(factors_df['因子ID'] == factor_id) & (pd.to_numeric(factors_df['星の数'], errors='coerce').fillna(0) >= min_stars)]
                        valid_ids.intersection_update(set(factor_match_df['個体ID']))
                elif cond_type in ['optional_skills', 'optional_genes']:
                    cond_group = conditions[0]
                    items = cond_group['items']
                    required_count = cond_group.get('count', 1)
                    skill_conditions = {item['id']: item['stars'] for item in items}
                    candidate_factors = factors_df[factors_df['因子ID'].isin(skill_conditions.keys())].copy()
                    def check_stars(row):
                        return pd.to_numeric(row['星の数'], errors='coerce').fillna(0) >= skill_conditions.get(row['因子ID'], 99)
                    candidate_factors = candidate_factors[candidate_factors.apply(check_stars, axis=1)]
                    if not candidate_factors.empty:
                        match_counts = candidate_factors.groupby('個体ID').size()
                        or_valid_ids = set(match_counts[match_counts >= required_count].index)
                        valid_ids.intersection_update(or_valid_ids)
                    else:
                        valid_ids = set()

            body_conds = self.conditions.get('red_factor_body', [])
            parent_conds = self.conditions.get('red_factor_parent', [])
            overall_conds = self.conditions.get('red_factor_overall', [])
            
            if body_conds:
                matched_ids_for_or_group = set()
                for cond in body_conds:
                    factor_match_df = factors_df[(factors_df['因子ID'] == cond['id']) & (pd.to_numeric(factors_df['星の数'], errors='coerce').fillna(0) >= cond['stars'])]
                    matched_ids_for_or_group.update(set(factor_match_df['個体ID']))
                valid_ids.intersection_update(matched_ids_for_or_group)

            if parent_conds:
                target_summary_df = summary_df[summary_df['個体ID'].isin(valid_ids)].copy()
                for i in [1, 2]:
                    if f'親赤因子{i}_星数' in target_summary_df.columns:
                        target_summary_df[f'親赤因子{i}_星数'] = pd.to_numeric(target_summary_df[f'親赤因子{i}_星数'], errors='coerce').fillna(0)
                    else:
                        target_summary_df[f'親赤因子{i}_星数'] = 0
                temp_ids = valid_ids.copy()
                for cond in parent_conds:
                    is_p1_match = (target_summary_df['親赤因子1_ID'] == cond['id'])
                    is_p2_match = (target_summary_df['親赤因子2_ID'] == cond['id'])
                    p1_stars = target_summary_df['親赤因子1_星数'].where(is_p1_match, 0)
                    p2_stars = target_summary_df['親赤因子2_星数'].where(is_p2_match, 0)
                    matched_df = target_summary_df[(p1_stars + p2_stars) >= cond['stars']]
                    temp_ids.intersection_update(set(matched_df['個体ID']))
                valid_ids.intersection_update(temp_ids)

            if overall_conds:
                target_summary_df = summary_df[summary_df['個体ID'].isin(valid_ids)].copy()
                target_factors_df = factors_df[factors_df['個体ID'].isin(valid_ids)].copy()
                for i in [1, 2]:
                    if f'親赤因子{i}_星数' in target_summary_df.columns:
                        target_summary_df[f'親赤因子{i}_星数'] = pd.to_numeric(target_summary_df[f'親赤因子{i}_星数'], errors='coerce').fillna(0)
                    else:
                        target_summary_df[f'親赤因子{i}_星数'] = 0
                target_factors_df['星の数'] = pd.to_numeric(target_factors_df['星の数'], errors='coerce').fillna(0)
                temp_ids = valid_ids.copy() 
                for cond in overall_conds:
                    factor_id = cond['id']
                    min_total_stars = cond['stars']
                    is_p1_match = (target_summary_df['親赤因子1_ID'] == factor_id)
                    is_p2_match = (target_summary_df['親赤因子2_ID'] == factor_id)
                    p1_stars = target_summary_df['親赤因子1_星数'].where(is_p1_match, 0)
                    p2_stars = target_summary_df['親赤因子2_星数'].where(is_p2_match, 0)
                    parent_stars_series = (p1_stars + p2_stars)
                    parent_stars_series.index = target_summary_df['個体ID']
                    body_factors = target_factors_df[target_factors_df['因子ID'] == factor_id]
                    body_stars_series = body_factors.set_index('個体ID')['星の数']
                    overall_total_stars = parent_stars_series.add(body_stars_series, fill_value=0)
                    overall_valid_ids = set(overall_total_stars[overall_total_stars >= min_total_stars].index)
                    temp_ids.intersection_update(overall_valid_ids)
                valid_ids.intersection_update(temp_ids)
            
            final_df = summary_df[summary_df['個体ID'].isin(valid_ids)].reset_index(drop=True)
            
            if final_df.empty:
                back_to_builder_view = ui.View(timeout=600)
                back_button = ui.Button(label="🔄 条件を編集する", style=ButtonStyle.secondary)
                async def back_callback(interaction: discord.Interaction):
                    await interaction.response.defer()
                    builder = SearchView(self.gspread_client, self.author, self.message, self.factor_dictionary, self.character_data, self.score_sheets, self.character_list_sorted, self.conditions)
                    await self.message.edit(content=None, embed=builder.create_embed(), view=builder)
                back_button.callback = back_callback
                back_to_builder_view.add_item(back_button)
                await self.message.edit(content="残念ですが、お探しの因子は見つかりませんでしたの。", embed=None, view=back_to_builder_view)
            else:
                result_view = SearchResultView(self.gspread_client, self.author, self.message, final_df, self.conditions, self.factor_dictionary, self.character_data, self.score_sheets, self.character_list_sorted)
                await self.message.edit(content=f"ふふっ、**{len(final_df)}件**の因子が見つかりました♪", embed=result_view.create_embed(), view=result_view)
        except Exception as e:
            await self.message.edit(content=f"検索中にエラーが発生しました…\n`{e}`", view=None, embed=None)
            traceback.print_exc()
    
    @ui.button(label="🍀 条件リセット", style=ButtonStyle.danger, row=4)
    async def reset_conditions(self, interaction: Interaction, button: ui.Button):
        self.conditions.clear(); self.skill_cart.clear(); self.character_cart.clear()
        self.search_only_mine = False 
        new_view = SearchView(self.gspread_client, self.author, self.message, self.factor_dictionary, self.character_data, self.score_sheets, self.character_list_sorted)
        await interaction.response.edit_message(embed=new_view.create_embed(), view=new_view)

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

class RankingView(ui.View):
    def __init__(self, author, ranking_df: pd.DataFrame, sheet_name: str, factor_dictionary: dict):
        super().__init__(timeout=600)
        self.author = author
        self.ranking_df = ranking_df.reset_index(drop=True)
        self.sheet_name = sheet_name
        self.factor_dictionary = factor_dictionary
        self.current_index = 0
        self.update_components()

    def update_components(self):
        self.clear_items()
        total = len(self.ranking_df)
        is_first_page = self.current_index == 0
        is_last_page = self.current_index >= total - 1

        first_btn = ui.Button(label="<<", style=ButtonStyle.secondary, disabled=is_first_page, custom_id="go_first")
        prev_btn = ui.Button(label="<", style=ButtonStyle.primary, disabled=is_first_page, custom_id="go_prev")
        page_label = ui.Button(label=f"{self.current_index + 1} / {total}", style=ButtonStyle.secondary, disabled=True)
        next_btn = ui.Button(label=">", style=ButtonStyle.primary, disabled=is_last_page, custom_id="go_next")
        last_btn = ui.Button(label=">>", style=ButtonStyle.secondary, disabled=is_last_page, custom_id="go_last")
        
        first_btn.callback = self.navigate_results
        prev_btn.callback = self.navigate_results
        next_btn.callback = self.navigate_results
        last_btn.callback = self.navigate_results
        
        self.add_item(first_btn); self.add_item(prev_btn); self.add_item(page_label); self.add_item(next_btn); self.add_item(last_btn)

    def create_embed(self) -> Embed:
        if self.ranking_df.empty:
            return Embed(title=f"🍀 {self.sheet_name} ハイスコアランキング", description="あらあら、まだランキングに誰もいないようですわ。ふふっ、一番乗りのチャンスですわよ♪", color=Color.orange())
        
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

        embed = create_themed_embed(
            title=f"🍀 検索結果 ({self.current_index + 1}/{len(self.summary_df)})",
            description=f"**{owner_name}** の **{char_name}**",
            footer_text=f"個体ID: {individual_id}"
        )

        if pd.notna(image_url) and image_url:
            embed.set_image(url=image_url)

        score_info = []
        for sheet_name in self.score_sheets.keys():
            score_col = f"合計({sheet_name})"
            if score_col in current_row and pd.notna(current_row[score_col]):
                score = pd.to_numeric(current_row[score_col], errors='coerce')
                if pd.notna(score) and score > 0:
                    score_info.append(f"**{sheet_name}**: `{int(score)}`点")
        
        if score_info:
            embed.add_field(name="📊 スコア", value="\n".join(score_info), inline=False)
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
        await interaction.response.defer()
        builder_view = SearchView(self.gspread_client, self.author, self.message, self.factor_dictionary, self.character_data, self.score_sheets, self.character_list_sorted, self.conditions)
        await interaction.edit_original_response(content=None, embed=builder_view.create_embed(), view=builder_view)

class ParentFactorSelectionView(ui.View):
    def __init__(self, editor_view: "RedFactorEditorView", factor_dictionary: dict):
        super().__init__(timeout=180)
        self.editor_view = editor_view
        self.factor_dictionary = factor_dictionary
        self.selected_factor_id = None
        self.selected_stars = None

        red_factor_options = [
            discord.SelectOption(label=finfo['name'], value=fid)
            for fid, finfo in self.factor_dictionary.items() if finfo['type'] == '赤因子'
        ]
        if len(red_factor_options) > 25: red_factor_options = red_factor_options[:25]
        
        factor_select = ui.Select(placeholder="1. 条件に追加する赤因子を選択...", options=red_factor_options, row=0)
        factor_select.callback = self.on_factor_select
        self.add_item(factor_select)

        star_options = [discord.SelectOption(label=f"合計 ★{i} 以上", value=str(i)) for i in range(1, 7)]
        stars_select = ui.Select(placeholder="2. 合計の最低星数を選択...", options=star_options, row=1)
        stars_select.callback = self.on_stars_select
        self.add_item(stars_select)

    @ui.button(label="✅ この条件で確定", style=ButtonStyle.success, row=2)
    async def confirm(self, interaction: Interaction, button: ui.Button):
        if not self.selected_factor_id or not self.selected_stars:
            return await interaction.response.send_message("因子と星数の両方を選択してください。", ephemeral=True, delete_after=5)

        new_condition = {'id': self.selected_factor_id, 'stars': self.selected_stars}
        self.editor_view.temp_conditions['parent'].append(new_condition)

        self.editor_view.build_view()
        await interaction.response.edit_message(embed=self.editor_view.create_embed(), view=self.editor_view)

    @ui.button(label="❌ キャンセル", style=ButtonStyle.secondary, row=2)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=self.editor_view.create_embed(), view=self.editor_view)

    async def on_factor_select(self, interaction: Interaction):
        self.selected_factor_id = interaction.data['values'][0]
        await interaction.response.defer()

    async def on_stars_select(self, interaction: Interaction):
        self.selected_stars = int(interaction.data['values'][0])
        await interaction.response.defer()

class BodyFactorSelectionView(ui.View):
    def __init__(self, editor_view: "RedFactorEditorView", factor_dictionary: dict):
        super().__init__(timeout=180)
        self.editor_view = editor_view
        self.factor_dictionary = factor_dictionary
        self.selected_factor_id = None
        self.selected_stars = None

        red_factor_options = [
            discord.SelectOption(label=finfo['name'], value=fid)
            for fid, finfo in self.factor_dictionary.items() if finfo['type'] == '赤因子'
        ]
        if len(red_factor_options) > 25: red_factor_options = red_factor_options[:25]
        
        factor_select = ui.Select(
            placeholder="条件に追加する赤因子を選択",
            options=red_factor_options,
            row=0,
            min_values=1,
            max_values=1
        )
        factor_select.callback = self.on_factor_select
        self.add_item(factor_select)

        star_options = [discord.SelectOption(label=f"★{i}", value=str(i)) for i in range(1, 4)]
        stars_select = ui.Select(placeholder="因子の星数を指定...", options=star_options, row=1)
        stars_select.callback = self.on_stars_select
        self.add_item(stars_select)

    @ui.button(label="✅ この条件で確定", style=ButtonStyle.success, row=2)
    async def confirm(self, interaction: Interaction, button: ui.Button):
        if not self.selected_factor_id or not self.selected_stars:
            return await interaction.response.send_message("因子と星数の両方を選択してください。", ephemeral=True, delete_after=5)

        new_condition = {'id': self.selected_factor_id, 'stars': self.selected_stars}
        self.editor_view.temp_conditions['body'].append(new_condition)

        self.editor_view.build_view()
        await interaction.response.edit_message(embed=self.editor_view.create_embed(), view=self.editor_view)

    @ui.button(label="❌ キャンセル", style=ButtonStyle.secondary, row=2)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=self.editor_view.create_embed(), view=self.editor_view)

    async def on_factor_select(self, interaction: Interaction):
        self.selected_factor_id = interaction.data['values'][0]
        await interaction.response.defer()

    async def on_stars_select(self, interaction: Interaction):
        self.selected_stars = int(interaction.data['values'][0])
        await interaction.response.defer()

class OverallFactorSelectionView(ui.View):
    def __init__(self, editor_view: "RedFactorEditorView", factor_dictionary: dict):
        super().__init__(timeout=180)
        self.editor_view = editor_view
        self.factor_dictionary = factor_dictionary
        self.selected_factor_id = None
        self.selected_stars = None

        red_factor_options = [
            discord.SelectOption(label=finfo['name'], value=fid)
            for fid, finfo in self.factor_dictionary.items() if finfo['type'] == '赤因子'
        ]
        if len(red_factor_options) > 25: red_factor_options = red_factor_options[:25]
        
        factor_select = ui.Select(placeholder="1. 条件に追加する赤因子を選択...", options=red_factor_options, row=0)
        factor_select.callback = self.on_factor_select
        self.add_item(factor_select)

        star_options = [discord.SelectOption(label=f"合計 ★{i} 以上", value=str(i)) for i in range(1, 10)]
        stars_select = ui.Select(placeholder="2. 全体の合計最低星数を選択...", options=star_options, row=1)
        stars_select.callback = self.on_stars_select
        self.add_item(stars_select)

    @ui.button(label="✅ この条件で確定", style=ButtonStyle.success, row=2)
    async def confirm(self, interaction: Interaction, button: ui.Button):
        if not self.selected_factor_id or not self.selected_stars:
            return await interaction.response.send_message("因子と星数の両方を選択してください。", ephemeral=True, delete_after=5)

        new_condition = {'id': self.selected_factor_id, 'stars': self.selected_stars}
        self.editor_view.temp_conditions['overall'].append(new_condition)

        self.editor_view.build_view()
        await interaction.response.edit_message(embed=self.editor_view.create_embed(), view=self.editor_view)

    @ui.button(label="❌ キャンセル", style=ButtonStyle.secondary, row=2)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=self.editor_view.create_embed(), view=self.editor_view)

    async def on_factor_select(self, interaction: Interaction):
        self.selected_factor_id = interaction.data['values'][0]
        await interaction.response.defer()

    async def on_stars_select(self, interaction: Interaction):
        self.selected_stars = int(interaction.data['values'][0])
        await interaction.response.defer()

class RedFactorEditorView(ui.View):
    def __init__(self, parent_view: "SearchView", factor_dictionary: dict):
        super().__init__(timeout=600)
        self.parent_view = parent_view
        self.factor_dictionary = factor_dictionary
        self.temp_conditions = {'body': [],'parent': [], 'overall': []}
        
        if self.parent_view.conditions.get('red_factor_body'):
            self.temp_conditions['body'] = self.parent_view.conditions.get('red_factor_body', []).copy()
        if self.parent_view.conditions.get('red_factor_parent'):
            self.temp_conditions['parent'] = self.parent_view.conditions.get('red_factor_parent', []).copy()
        if self.parent_view.conditions.get('red_factor_overall'):
            self.temp_conditions['overall'] = self.parent_view.conditions.get('red_factor_overall', []).copy()
            
        self.build_view()

    def create_embed(self) -> Embed:
        embed = Embed(title="🍀 赤因子 条件エディタ", color=Color.red())
        description_lines = []
        if not self.temp_conditions['body'] and not self.temp_conditions['parent'] and not self.temp_conditions['overall']:
            description_lines.append("下のボタンから条件を追加してください。")

        if self.temp_conditions['body']:
            body_names = [self.factor_dictionary.get(f['id'], {}).get('name', '不明') + f"(★{f['stars']})" for f in self.temp_conditions['body']]
            description_lines.append(f"**▼本体の赤因子 (OR)**\n- `{' / '.join(body_names)}`")
        if self.temp_conditions['parent']:
            parent_lines = [f"- `{self.factor_dictionary.get(f['id'], {}).get('name', '不明')} (合計★{f['stars']}以上)`" for f in self.temp_conditions['parent']]
            description_lines.append(f"**▼親の赤因子 (AND)**\n" + "\n".join(parent_lines))
        
        if self.temp_conditions['overall']:
            overall_lines = [f"- `{self.factor_dictionary.get(f['id'], {}).get('name', '不明')} (全体合計★{f['stars']}以上)`" for f in self.temp_conditions['overall']]
            description_lines.append(f"**▼全体の赤因子 (AND)**\n" + "\n".join(overall_lines))

        embed.description = "\n\n".join(description_lines)
        embed.set_footer(text="設定が終わったら「✅全て確定して戻る」を押してください。")
        return embed

    def build_view(self):
        self.clear_items()
        add_body_btn = ui.Button(label="本体の条件を追加", style=ButtonStyle.primary, row=0)
        add_body_btn.callback = self.add_body_condition
        self.add_item(add_body_btn)

        add_parent_btn = ui.Button(label="親の条件を追加", style=ButtonStyle.primary, row=0)
        add_parent_btn.callback = self.add_parent_condition
        self.add_item(add_parent_btn)
        
        add_overall_btn = ui.Button(label="全体の条件を追加", style=ButtonStyle.primary, row=0)
        add_overall_btn.callback = self.add_overall_condition
        self.add_item(add_overall_btn)

        can_edit = self.temp_conditions['body'] or self.temp_conditions['parent'] or self.temp_conditions['overall']
        edit_btn = ui.Button(label="条件を削除", style=ButtonStyle.secondary, row=1, disabled=not can_edit)
        edit_btn.callback = self.delete_condition
        self.add_item(edit_btn)

        confirm_btn = ui.Button(label="✅ 全て確定して戻る", style=ButtonStyle.success, row=2)
        confirm_btn.callback = self.confirm_and_return
        self.add_item(confirm_btn)

        cancel_btn = ui.Button(label="❌ キャンセルして戻る", style=ButtonStyle.danger, row=2)
        cancel_btn.callback = self.cancel_and_return
        self.add_item(cancel_btn)

    async def add_body_condition(self, interaction: Interaction):
        selection_view = BodyFactorSelectionView(self, self.factor_dictionary)
        embed = Embed(title="本体の赤因子を追加", description="追加したい赤因子と、星数を選択してください。", color=Color.red())
        await interaction.response.edit_message(embed=embed, view=selection_view)

    async def add_parent_condition(self, interaction: Interaction):
        selection_view = ParentFactorSelectionView(self, self.factor_dictionary)
        embed = Embed(title="親の赤因子を追加", description="追加したい赤因子と、合計の最低星数を選択してください。", color=Color.red())
        await interaction.response.edit_message(embed=embed, view=selection_view)

    async def add_overall_condition(self, interaction: Interaction):
        selection_view = OverallFactorSelectionView(self, self.factor_dictionary)
        embed = Embed(title="全体の赤因子を追加", description="追加したい赤因子と、全体の合計最低星数を選択してください。", color=Color.red())
        await interaction.response.edit_message(embed=embed, view=selection_view)
    
    async def delete_condition(self, interaction: Interaction):
        options = []
        if self.temp_conditions['body']:
            for i, cond in enumerate(self.temp_conditions['body']):
                label_text = f"【本体】{self.factor_dictionary.get(cond['id'], {}).get('name', '不明')} (★{cond['stars']})"
                options.append(discord.SelectOption(label=label_text[:100], value=f'body_{i}'))

        if self.temp_conditions['parent']:
            for i, cond in enumerate(self.temp_conditions['parent']):
                label_text = f"【親】{self.factor_dictionary.get(cond['id'], {}).get('name', '不明')} (合計★{cond['stars']}以上)"
                options.append(discord.SelectOption(label=label_text[:100], value=f'parent_{i}'))

        if self.temp_conditions['overall']:
            for i, cond in enumerate(self.temp_conditions['overall']):
                label_text = f"【全体】{self.factor_dictionary.get(cond['id'], {}).get('name', '不明')} (全体合計★{cond['stars']}以上)"
                options.append(discord.SelectOption(label=label_text[:100], value=f'overall_{i}'))
        
        if not options:
            return await interaction.response.send_message("削除できる条件がありません。", ephemeral=True, delete_after=5)

        delete_select = ui.Select(placeholder="削除したい条件を選択してください...", options=options)
        delete_select.callback = self.handle_delete_selection
        
        self.add_item(delete_select)
        await interaction.response.edit_message(view=self)

    async def handle_delete_selection(self, interaction: Interaction):
        selected_value = interaction.data['values'][0]
        cond_type, index_str = selected_value.split('_')
        index = int(index_str)

        if cond_type == 'body':
            if 0 <= index < len(self.temp_conditions['body']):
                del self.temp_conditions['body'][index]
        elif cond_type == 'parent':
            if 0 <= index < len(self.temp_conditions['parent']):
                del self.temp_conditions['parent'][index]
        elif cond_type == 'overall':
            if 0 <= index < len(self.temp_conditions['overall']):
                del self.temp_conditions['overall'][index]
        
        self.build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
           
    async def confirm_and_return(self, interaction: Interaction):
        self.parent_view.conditions.pop('red_factor_body', None)
        self.parent_view.conditions.pop('red_factor_parent', None)
        self.parent_view.conditions.pop('red_factor_overall', None)
        if self.temp_conditions['body']:
            self.parent_view.conditions['red_factor_body'] = self.temp_conditions['body']
        if self.temp_conditions['parent']:
            self.parent_view.conditions['red_factor_parent'] = self.temp_conditions['parent']
        if self.temp_conditions['overall']:
            self.parent_view.conditions['red_factor_overall'] = self.temp_conditions['overall']
        
        await interaction.response.edit_message(
            embed=self.parent_view.create_embed(), 
            view=self.parent_view
        )

    async def cancel_and_return(self, interaction: Interaction):
        await interaction.response.edit_message(
            embed=self.parent_view.create_embed(), 
            view=self.parent_view
        )        

class DeleteConditionView(ui.View):
    def __init__(self, parent_view: "SearchView"):
        super().__init__(timeout=300)
        self.parent_view = parent_view

        options = []
        for cond_type, conditions in self.parent_view.conditions.items():
            if cond_type.startswith('red_factor'):
                type_jp = {"body":"本体","parent":"親","overall":"全体"}[cond_type.split('_')[2]]
                names = ", ".join([self.parent_view.factor_dictionary.get(f['id'],{}).get('name','不明') for f in conditions])
                label = f"【赤因子/{type_jp}】{names}"
                options.append(discord.SelectOption(label=label[:100], value=f"{cond_type}_0"))
                continue
            
            for i, cond in enumerate(conditions):
                if cond is None: continue
                label = f"不明な条件: {cond_type}"
                if cond_type == 'characters':
                    names = ", ".join([c['name'] for c in cond['items']])
                    label = f"【キャラ】{names}"
                elif cond_type == 'score':
                    label = f"【スコア】{cond['sheet']} ({cond['score']}点以上)"
                else:
                    type_map = {
                        'blue_factors': '青因子', 'green_factors': '緑因子',
                        'required_skills': '必須白', 'optional_skills': '選択白',
                        'required_genes': '必須遺伝子', 'optional_genes': '選択遺伝子'
                    }
                    type_jp = type_map.get(cond_type, 'スキル')
                    skill_names = ", ".join([self.parent_view.factor_dictionary.get(s['id'],{}).get('name','不明') + f"(★{s['stars']})" for s in cond['items']])
                    label = f"【{type_jp}】{skill_names}"
                
                options.append(discord.SelectOption(label=label[:100], value=f"{cond_type}_{i}"))
        
        if options:
            delete_select = ui.Select(
                placeholder="削除したい条件を選択してください...", 
                options=options, 
                max_values=min(len(options), 25)
            )
            delete_select.callback = self.handle_delete_selection
            self.add_item(delete_select)

    async def handle_delete_selection(self, interaction: Interaction):
        for selected_value in interaction.data['values']:
            cond_type, index_str = selected_value.rsplit('_', 1)
            index = int(index_str)
            
            if cond_type.startswith('red_factor'):
                if cond_type in self.parent_view.conditions:
                    del self.parent_view.conditions[cond_type]
            elif cond_type in self.parent_view.conditions and 0 <= index < len(self.parent_view.conditions[cond_type]):
                self.parent_view.conditions[cond_type][index] = None
        
        for cond_type in list(self.parent_view.conditions.keys()):
            if self.parent_view.conditions[cond_type]:
                self.parent_view.conditions[cond_type] = [cond for cond in self.parent_view.conditions[cond_type] if cond is not None]
            
            if not self.parent_view.conditions[cond_type]:
                del self.parent_view.conditions[cond_type]

        await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)

    @ui.button(label="キャンセルして戻る", style=ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=self.parent_view.create_embed(), view=self.parent_view)