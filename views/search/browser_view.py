import discord
from discord import ui, Interaction, Embed, Color, ButtonStyle

import math
import image_processor

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .main_view import SearchView
    from .modals import OptionalSkillCountModal


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

from .modals import FilterModal        