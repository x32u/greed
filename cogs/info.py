import asyncio
from datetime import timedelta, datetime
import json
import os
import discord
import humanize
import psutil
import pytz

from tools.bot import Pretend
from tools.helpers import PretendContext
from tools.validators import ValidCommand
from tools.conversion import Conversion
from tools.socials import get_instagram_user, get_tiktok_user
from discord import User, Embed, __version__, utils, Permissions
from discord.ext.commands import Cog, command, hybrid_command
from discord.ui import View, Button
import platform

my_system = platform.uname()


class Info(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Information commands"
        self.conversion = Conversion()


    def create_bot_invite(self, user: User) -> View:
        """
        Create a view containing a button with the bot invite url
        """

        view = View()
        view.add_item(
            Button(
                label=f"invite {user.name}",
                url=utils.oauth_url(client_id=user.id, permissions=Permissions(8)),
            )
        )
        return view
    
    @command(name = "tiktok")
    async def tiktok(self, ctx: PretendContext, *, username: str):
        try:
            data = await get_tiktok_user(username)
            embed = data.to_embed(ctx)
            return await ctx.send(embed = embed)
        except:
            return await ctx.send_warning(f"tiktok user {username} not found")
        
    @command(name = "instagram")
    async def instagram(self, ctx: PretendContext, *, username: str):
        try:
            data = await get_instagram_user(username)
            embed = data.to_embed(ctx)
            return await ctx.send(embed = embed)
        except:
            return await ctx.send_warning(f"instagram user {username} not found")
        
    @command(name = 'creategif')
    async def creategif(self, ctx: PretendContext, *, url: str = None):
        return await self.conversion.do_conversion(ctx, url)

    @hybrid_command(name="commands", aliases=["h"])
    async def _help(self, ctx: PretendContext, *, command: ValidCommand = None):
        """
        The help command menu
        """

        if not command:
            return await ctx.send_help()
        else:
            return await ctx.send_help(command)

    @command()
    async def getbotinvite(self, ctx: PretendContext, *, member: User):
        """
        Get the bot invite based on it's id
        """

        if not member.bot:
            return await ctx.send_error("This is **not** a bot")

        await ctx.reply(ctx.author.mention, view=self.create_bot_invite(member))


    @hybrid_command(aliases=["up"])
    async def uptime(self, ctx: PretendContext):
        """
        Displays how long has the bot been online for
        """

        return await ctx.reply(
            embed=Embed(
                color=self.bot.color,
                description=f"<:phone:1205998412902830130> {ctx.author.mention}: **{self.bot.uptime}**",
            )
        )




        
    @command(aliases=["pi"])
    async def profileicon(self, ctx: PretendContext, *, member: discord.User = None):
        if member == None:member = ctx.author
        user = await self.bot.fetch_user(member.id)
        if user.banner == None:
            em = discord.Embed(
                color=0x8D7F64,
                description=f"{member.mention}: doesn't have a profile I can display.")
            await ctx.reply(embed=em, mention_author=False)
        else:
            banner_url = user.banner.url
            avatar_url = user.avatar.url
            button1 = Button(label="Icon", url=avatar_url)
            button2 = Button(label="Banner", url=banner_url)
            e = discord.Embed(color=0x8D7F64, description=f'*Here is the icon and banner for [**{member.display_name}**](https://discord.com/users/{member.id})*')
            e.set_author(name=f"{member.display_name}", icon_url=f"{member.avatar}", url=f"https://discord.com/users/{member.id}")
            e.set_image(url=f"{banner_url}")
            e.set_thumbnail(url=f"{avatar_url}")
            view = View()
            view.add_item(button1)
            view.add_item(button2)
            await ctx.reply(embed=e, view=view, mention_author=False)



    @Cog.listener()
    async def on_command(self, ctx):
        # Increment command count in the JSON file
        self._increment_stats()

    def _load_stats(self):
        try:
            with open("/home/ubuntu/greedrecodetotallynotpretend/tools/stats.json", "r") as file:
                data = json.load(file)
                return data.get("commands_executed", 0)
        except FileNotFoundError:
            return 0

    def _increment_stats(self):
        # Increment command count in the JSON file
        try:
            with open("/home/ubuntu/greedrecodetotallynotpretend/tools/stats.json", "r+") as file:
                data = json.load(file)
                data["commands_executed"] = data.get("commands_executed", 0) + 1
                file.seek(0)
                json.dump(data, file, indent=4)
        except FileNotFoundError:
            pass



    @command(name='status')
    async def status(self, ctx):
        """Displays bot statistics."""
        # Calculate uptime

        # Calculate bot ping
        latency = round(self.bot.latency * 1000)

        # Get bot process memory usage
        process = psutil.Process()
        memory_usage = process.memory_full_info().rss / 1024 ** 2

        # Get shard information
        shard_id = ctx.guild.shard_id if ctx.guild else 0
        shard_count = self.bot.shard_count


        commands_executed = self._load_stats()

        # Send statistics embed
        embed = discord.Embed(title="ᓚᘏᗢ", color=self.bot.color)
        embed.add_field(name="Uptime", value=self.bot.uptime, inline=False)
        embed.add_field(name="Ping", value=f"{latency}ms", inline=False)
        embed.add_field(name="Memory Usage", value=f"{memory_usage:.2f} MB", inline=False)
        embed.add_field(name="Shard ID", value=str(shard_id), inline=True)
        embed.add_field(name="Shard Count", value=str(shard_count), inline=True)
        embed.add_field(name="Commands Executed", value=str(commands_executed), inline=True)
        await ctx.send(embed=embed)



    @hybrid_command()
    async def ping(self, ctx: PretendContext):
        """
        Check status of each bot shard
        """

        embed = Embed(
            color=self.bot.color, description=f"client `{round(self.bot.latency * 1000)}`ms\nshards ({self.bot.shard_count})"
        )

        for shard in self.bot.shards:
            guilds = [g for g in self.bot.guilds if g.shard_id == shard]
            users = sum([g.member_count for g in guilds])
            embed.add_field(
                name=f"<:IconStatusOnline:1227206120892792923> shard {shard}",
                value=f"> <:server:1227206797350273045> **ping**: {round(self.bot.shards.get(shard).latency * 1000)}ms\n> <:BadgeServerVerifiedBlue:1227206877524525088> **guilds**: {len(guilds)}\n> <:usericn:1227206919169769482> **users**: {users:,}",
                inline=False,
            )

        await ctx.send(embed=embed)

    @hybrid_command(aliases=["inv", "link"])
    async def invite(self, ctx: PretendContext):
        """
        Send an invite link of the bot
        """

        await ctx.reply("greed is free btw", view=self.create_bot_invite(ctx.guild.me))




    @command()
    async def ready(self, ctx):
        online = "<a:online:1215869134265520128>"
        logss_channel_id = 1215108705725448252  # Update this with your desired log channel ID
        logss_channel = self.bot.get_channel(logss_channel_id)
        total_members = sum(guild.member_count for guild in self.bot.guilds)


        if logss_channel:
            embed = discord.Embed(color=self.bot.color, description=f"{online} {self.bot.user.name} serving **{len(self.bot.guilds)}** servers & **{total_members}** users at **{round(self.bot.latency * 1000)}ms**")
            await logss_channel.send(embed=embed)
            await ctx.send("Notification sent!")
        else:
            await ctx.send("Log channel not found. Unable to send the message.")




    @hybrid_command(aliases=["bi", "bot", "info", "about"])
    async def botinfo(self, ctx: PretendContext):
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024
        cpu_usage = psutil.cpu_percent()
        disk_usage = psutil.disk_usage('/').percent
        net_io_counters = psutil.net_io_counters()
        bandwidth_usage = (net_io_counters.bytes_sent + net_io_counters.bytes_recv) / 1024 / 1024

        embed = discord.Embed(
            title=str(self.bot.user.name),
            color=self.bot.color,
            timestamp=datetime.now()
        ).set_thumbnail(
            url=(
                self.bot.user.avatar
                or self.bot.user.default_avatar
            )
        )

        embed.add_field(
            name="Bot",
            value=f"""
            Servers: **{len(self.bot.guilds):,}**
            Users: **{sum(g.member_count for g in self.bot.guilds):,}**
            Commands: [**{len(set(self.bot.walk_commands())):,}**](https://greed.best/commands)
            """
        )

        embed.add_field(
            name="System",
            value=f"""
            Ping: **{self.bot.latency*1000:.2f}**ms
            Memory: **{memory_usage:.2f}** MB
            CPU: **{cpu_usage}%**
            Bandwidth: **{bandwidth_usage:.2f}**
            Disk: **{disk_usage}%**
            """
        )

        view = discord.ui.View()
        support_button = discord.ui.Button(
            label="Support",
            url="https://discord.gg/greedbot",
            style=discord.ButtonStyle.url
        )
        invite_button = discord.ui.Button(
            label="Invite",
            url="https://greed.best/invite",
            style=discord.ButtonStyle.url
        )

        view.add_item(support_button)
        view.add_item(invite_button)

        await ctx.send(
            embed=embed,
            view=view
        )

async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Info(bot))
