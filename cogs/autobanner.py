import discord
import asyncio
import os
import random
import json
from images import banners

from discord.ext import commands, tasks

class AutoBannerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.settings = self.load_settings()
        self.banner_links = banners.banners
        self.banner_tasks = {}

    def load_settings(self):
        try:
            with open('/home/ubuntu/greedrecodetotallynotpretend/events/banner.json', 'r') as file:
                settings = json.load(file)
        except FileNotFoundError:
            settings = {}
        return settings

    def save_settings(self):
        with open('/home/ubuntu/greedrecodetotallynotpretend/events/banner.json', 'w') as file:
            json.dump(self.settings, file)

    async def send_banner_task(self, guild_id, channel_id):
        while True:
            if not self.banner_links:
                print("No banner links found.")
                return
            banner_link = random.choice(self.banner_links)
            channel = self.bot.get_guild(guild_id).get_channel(channel_id)
            if channel:
                embed = discord.Embed(title="New Banner", url="https://https://discord.gg/greedbot")
                embed.set_image(url=banner_link)
                embed.set_footer(text="sent from greed ^_^")
                await channel.send(embed=embed)
            await asyncio.sleep(15)

    @commands.command()
    async def autobanner(self, ctx, channel: discord.TextChannel=None):
        if not channel:
            # Stop autobanner for the guild
            if ctx.guild.id in self.banner_tasks:
                self.banner_tasks[ctx.guild.id].cancel()
                del self.banner_tasks[ctx.guild.id]
            self.settings.pop(str(ctx.guild.id), None)
            self.save_settings()
            embed = discord.Embed(color=self.bot.color, description=f"<:check_white:1204583868435271731> Auto banner disabled.")
            await ctx.send(embed=embed)
            return

        # Start autobanner for the specified channel in the guild
        self.settings[str(ctx.guild.id)] = {"channel_id": channel.id}
        self.save_settings()
        if ctx.guild.id not in self.banner_tasks:
            self.banner_tasks[ctx.guild.id] = asyncio.create_task(self.send_banner_task(ctx.guild.id, channel.id))
        embed = discord.Embed(color=self.bot.color, description=f"<:check_white:1204583868435271731> Auto banner enabled for {channel.mention}.")
        await ctx.send(embed=embed)

    async def start_banner_tasks(self):
        for guild_id, data in self.settings.items():
            channel_id = data.get("channel_id")
            guild = self.bot.get_guild(int(guild_id))
            if guild and channel_id:
                if guild_id not in self.banner_tasks:
                    self.banner_tasks[guild_id] = asyncio.create_task(self.send_banner_task(guild.id, channel_id))

    def cog_unload(self):
        for task in self.banner_tasks.values():
            task.cancel()


async def setup(bot):
    cog = AutoBannerCog(bot)
    await cog.start_banner_tasks()
    await bot.add_cog(cog)
