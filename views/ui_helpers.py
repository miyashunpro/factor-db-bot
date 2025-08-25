import discord
from discord import Color
import config

def create_themed_embed(title: str, description: str, footer_text: str = None, thumbnail_url: str = None):
    THEME_COLOR = discord.Color(0x57F287) 
    embed = discord.Embed(title=title, description=description, color=THEME_COLOR)
    embed.set_author(name=config.AUTHOR_NAME, icon_url=config.AUTHOR_ICON_URL)
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if footer_text:
        embed.set_footer(text=footer_text)
    return embed