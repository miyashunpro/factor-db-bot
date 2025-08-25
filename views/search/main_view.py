import discord
from discord import ui, Interaction, Embed, Color, ButtonStyle
from collections import defaultdict
import pandas as pd
import traceback

import config
from ..ui_helpers import create_themed_embed
from .results_view import SearchResultView
from .browser_view import ItemBrowserView
from .editors import SingleFactorEditView, RedFactorEditorView
from .modals import ScoreSheetSelectView

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
            if self.search_only_mine:
                summary_df = summary_df[summary_df['所有者ID'] == str(self.author.id)]
                if summary_df.empty:
                    return await self.message.edit(content="あらあら、あなたの所有する因子が見つかりませんでしたわ。", view=None, embed=None)
            
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