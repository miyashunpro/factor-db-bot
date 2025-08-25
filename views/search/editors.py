import discord
from discord import ui, Interaction, Embed, Color, ButtonStyle

# 循環参照を避けるための型ヒント用
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .main_view import SearchView

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