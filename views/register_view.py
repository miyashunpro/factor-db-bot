import discord
from discord import ui, Interaction, ButtonStyle, TextStyle, SelectOption, Embed
import gspread

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
            from bot import check_rank_in
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
            from bot import check_rank_in
            await interaction.client.check_rank_in(interaction, self.gspread_client, self.individual_id, selected_user)
            await self.show_details_editor(interaction, f"まあ！「{selected_user.display_name}」さんがトレーナーですのね♪")

    @ui.button(label="サーバー外の所有者情報を入力", style=ButtonStyle.secondary, row=2)
    async def set_external_callback(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_modal(ExternalOwnerModal(self))

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