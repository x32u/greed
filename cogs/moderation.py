import re
import json as orjson
import asyncio
import datetime

from discord import (
    Member,
    PermissionOverwrite,
    Embed,
    Interaction,
    utils,
    TextChannel,
    User,
    Object,
    Role,
    Thread
)
from discord.ext.commands import (
    Cog,
    hybrid_command,
    has_guild_permissions,
    command,
    group,
    CurrentChannel,
    bot_has_guild_permissions,
)
from discord.abc import GuildChannel
from tools.handlers.logs import ctx_to_log_data

from typing import Union, Optional
from collections import defaultdict
from humanfriendly import format_timespan

from tools.bot import Pretend
from tools.helpers import PretendContext, Invoking
from tools.converters import NoStaff, NewRoleConverter
from tools.validators import ValidTime, ValidNickname
from tools.predicates import is_jail, admin_antinuke
from tools.misc.views import BoosterMod


class Moderation(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Moderation commands"
        self.locks = defaultdict(asyncio.Lock)
        self.role_lock = defaultdict(asyncio.Lock)

    async def punish_a_bitch(
        self: "Moderation",
        module: str,
        member: Member,
        reason: str,
        role: Optional[Role] = None,
    ):
        """
        Antinuke punish someone

        module [`str`] - the name of the module
        member [`discord.Member`] - the author of the command
        reason [`str`] - the reason of punishment
        role: [`typing.Optional[discord.Role]`] - A role for the role command (can be None)
        """

        if self.bot.an.get_bot_perms(member.guild):
            if await self.bot.an.is_module(module, member.guild):
                if not await self.bot.an.is_whitelisted(member):
                    if not role:
                        if not await self.bot.an.check_threshold(module, member):
                            return

                    if self.bot.an.check_hieracy(member, member.guild.me):
                        cache = self.bot.cache.get(f"{module}-{member.guild.id}")
                        if not cache:
                            await self.bot.cache.set(
                                f"{module}-{member.guild.id}", True, 5
                            )
                            tasks = [
                                await self.bot.an.decide_punishment(
                                    module, member, reason
                                )
                            ]
                            action_time = datetime.datetime.now()
                            check = await self.bot.db.fetchrow(
                                "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                member.guild.id,
                            )
                            await self.bot.an.take_action(
                                reason,
                                member,
                                tasks,
                                action_time,
                                check["owner_id"],
                                member.guild.get_channel(check["logs"]),
                            )

    @Cog.listener()
    async def on_guild_channel_create(self, channel: GuildChannel):
        if check := await self.bot.db.fetchrow(
            "SELECT * FROM jail WHERE guild_id = $1", channel.guild.id
        ):
            if role := channel.guild.get_role(int(check["role_id"])):
                await channel.set_permissions(
                    role,
                    view_channel=False,
                    reason="overwriting permissions for jail role",
                )

    @Cog.listener()
    async def on_member_join(self, member: Member):
        if await self.bot.db.fetchrow(
            "SELECT * FROM jail_members WHERE guild_id = $1 AND user_id = $2",
            member.guild.id,
            member.id,
        ):
            if re := await self.bot.db.fetchrow(
                "SELECT role_id FROM jail WHERE guild_id = $1", member.guild.id
            ):
                if role := member.guild.get_role(re[0]):
                    await member.add_roles(role, reason="member jailed")

    @Cog.listener()
    async def on_member_remove(self, member: Member):
        await self.bot.redis.set(f"re-{member.id}-{member.guild.id}", orjson.dumps([r.id for r in member.roles]))

    @hybrid_command(brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def restore(self, ctx: PretendContext, *, member: NoStaff):
        """
        give a member their roles back after rejoining
        """

        async with self.locks[ctx.guild.id]:
            check = await self.bot.redis.get(f"re-{member.id}-{ctx.guild.id}")

            if not check:
                return await ctx.send_error("This member doesn't have any roles saved")

            roles = [
                ctx.guild.get_role(r)
                for r in orjson.loads(check)
                if ctx.guild.get_role(r)
            ]
            await member.edit(
                roles=[r for r in roles if r.is_assignable()],
                reason=f"roles restored by {ctx.author}",
            )

            await self.bot.redis.delete(f"re-{member.id}-{ctx.guild.id}")
            await self.bot.logs.send_moderator(ctx, member)
            return await ctx.send_success(f"Restored {member.mention}'s roles")

    @command(brief="administrator")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    async def setme(self, ctx: PretendContext):
        """
        Set up jail module
        """

        async with self.locks[ctx.guild.id]:
            if await self.bot.db.fetchrow(
                "SELECT * FROM jail WHERE guild_id = $1", ctx.guild.id
            ):
                return await ctx.send_warning("Jail is **already** configured")

            mes = await ctx.pretend_send("Configuring jail..")
            async with ctx.typing():
                role = await ctx.guild.create_role(
                    name="jail", reason="creating jail channel"
                )

                await asyncio.gather(
                    *[
                        channel.set_permissions(role, view_channel=False)
                        for channel in ctx.guild.channels
                    ]
                )

                overwrite = {
                    role: PermissionOverwrite(view_channel=True),
                    ctx.guild.default_role: PermissionOverwrite(view_channel=False),
                }

                text = await ctx.guild.create_text_channel(
                    name="jail-greed",
                    overwrites=overwrite,
                    reason="creating jail channel",
                )
                await self.bot.db.execute(
                    """
      INSERT INTO jail
      VALUES ($1,$2,$3)
      """,
                    ctx.guild.id,
                    text.id,
                    role.id,
                )

                return await mes.edit(
                    embed=Embed(
                        color=self.bot.yes_color,
                        description=f"{self.bot.yes} {ctx.author.mention}: Jail succesfully configured",
                    )
                )

    @command(brief="administrator")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    @is_jail()
    async def unsetme(self, ctx: PretendContext):
        """
        disable the jail module
        """

        async def yes_func(interaction: Interaction):
            check = await self.bot.db.fetchrow(
                "SELECT * FROM jail WHERE guild_id = $1", interaction.guild.id
            )
            role = interaction.guild.get_role(check["role_id"])
            channel = interaction.guild.get_channel(check["channel_id"])

            if role:
                await role.delete(reason=f"jail disabled by {ctx.author}")

            if channel:
                await channel.delete(reason=f"jail disabled by {ctx.author}")

            for idk in [
                "DELETE FROM jail WHERE guild_id = $1",
                "DELETE FROM jail_members WHERE guild_id = $1",
            ]:
                await self.bot.db.execute(idk, interaction.guild.id)

            return await interaction.response.edit_message(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {interaction.user.mention}: Disabled the jail module",
                ),
                view=None,
            )

        async def no_func(interaction: Interaction) -> None:
            await interaction.response.edit_message(
                embed=Embed(color=self.bot.color, description="Cancelling action..."),
                view=None,
            )

        return await ctx.confirmation_send(
            f"{ctx.author.mention}: Are you sure you want to **disable** the jail module?\nThis action is **IRREVERSIBLE**",
            yes_func,
            no_func,
        )

    @hybrid_command(brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_roles=True)
    @is_jail()
    async def jail(
        self,
        ctx: PretendContext,
        member: NoStaff,
        *,
        reason: str = "No reason provided",
    ):
        """
        Restrict someone from the server's channels
        """

        if member.id == ctx.author.id:
            return await ctx.send_warning(f"You cannot manage {ctx.author.mention}")

        if await self.bot.db.fetchrow(
            "SELECT * FROM jail_members WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member.id,
        ):
            return await ctx.send_warning(f"{member.mention} is **already** jailed")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM jail WHERE guild_id = $1", ctx.guild.id
        )
        role = ctx.guild.get_role(check["role_id"])

        if not role:
            return await ctx.send_error(
                "Jail role **not found**. Please unset jail and set it back"
            )

        old_roles = [r.id for r in member.roles if r.is_assignable()]
        roles = [r for r in member.roles if not r.is_assignable()]
        roles.append(role)
        await member.edit(roles=roles, reason=reason)

        try:
            await member.send(
                f"{member.mention}, you have been jailed in **{ctx.guild.name}** (`{ctx.guild.id}`) - {reason}! Wait for a staff member to unjail you"
            )
        except:
            pass

        await self.bot.db.execute(
            """
    INSERT INTO jail_members VALUES ($1,$2,$3,$4)
    """,
            ctx.guild.id,
            member.id,
            orjson.dumps(old_roles),
            datetime.datetime.now(),
        )
        await self.bot.logs.send_moderator(ctx, member)
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Jailed {member.mention} - {reason}")

    @hybrid_command(brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_roles=True)
    @is_jail()
    async def unjail(
        self, ctx: PretendContext, member: Member, *, reason: str = "No reason provided"
    ):
        """
        lift the jail restriction from a member
        """

        re = await self.bot.db.fetchrow(
            """
    SELECT roles FROM jail_members
    WHERE guild_id = $1
    AND user_id = $2
    """,
            ctx.guild.id,
            member.id,
        )
        if not re:
            return await ctx.send_warning(f"{member.mention} is **not** jailed")

        roles = [
            ctx.guild.get_role(r) for r in orjson.loads(re[0]) if ctx.guild.get_role(r)
        ]

        if ctx.guild.premium_subscriber_role in member.roles:
            roles.append(ctx.guild.premium_subscriber_role)

        await member.edit(roles=[r for r in roles], reason=reason)
        await self.bot.db.execute(
            """
    DELETE FROM jail_members
    WHERE guild_id = $1
    AND user_id = $2
    """,
            ctx.guild.id,
            member.id,
        )
        await self.bot.logs.send_moderator(ctx, member)
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Unjailed {member.mention} - {reason}")

    @command()
    async def jailed(self, ctx: PretendContext):
        """
        returns the jailed members
        """

        results = await self.bot.db.fetch(
            "SELECT * FROM jail_members WHERE guild_id = $1", ctx.guild.id
        )
        jailed = [
            f"<@{result['user_id']}> - {utils.format_dt(result['jailed_at'], style='R')}"
            for result in results
            if ctx.guild.get_member(result["user_id"])
        ]

        if len(jailed) > 0:
            return await ctx.paginate(
                jailed,
                f"Jailed members ({len(results)})",
                {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
            )
        else:
            return await ctx.send_warning("There are no jailed members")

    @hybrid_command(brief="mute members")
    @has_guild_permissions(mute_members=True)
    @bot_has_guild_permissions(mute_members=True)
    async def voicemute(self, ctx: PretendContext, *, member: NoStaff):
        """
        Voice mute a member
        """

        if not member.voice:
            return await ctx.send_error("This member is **not** in a voice channel")

        if member.voice.mute:
            return await ctx.send_warning("This member is **already** muted")

        await member.edit(mute=True, reason=f"Member voice muted by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        await ctx.send_success(f"Voice muted {member.mention}")

    @hybrid_command(brief="mute members")
    @has_guild_permissions(mute_members=True)
    @bot_has_guild_permissions(mute_members=True)
    async def voiceunmute(self, ctx: PretendContext, *, member: NoStaff):
        """
        Voice unmute a member
        """

        if not member.voice.mute:
            return await ctx.send_warning(f"This member is **not** voice muted")

        await member.edit(mute=False, reason=f"Member voice unmuted by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        await ctx.send_success(f"Voice unmuted {member.mention}")

    @hybrid_command(brief="deafen members")
    @has_guild_permissions(deafen_members=True)
    @bot_has_guild_permissions(deafen_members=True)
    async def voicedeafen(self, ctx: PretendContext, *, member: NoStaff):
        """
        Deafen a member in a voice channel
        """

        if not member.voice:
            return await ctx.send_error("This member is **not** in a voice channel")

        if member.voice.deaf:
            return await ctx.send_warning(f"This member is **already** voice deafened")

        await member.edit(deafen=True, reason=f"Member voice deafened by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        await ctx.send_success(f"Voice deafened {member.mention}")

    @hybrid_command(brief="deafen members")
    @has_guild_permissions(deafen_members=True)
    @bot_has_guild_permissions(deafen_members=True)
    async def voiceundeafen(self, ctx: PretendContext, *, member: NoStaff):
        """
        Voice undeafen a member
        """

        if not member.voice.deaf:
            return await ctx.send_warning("This member is **not** deafened")

        await member.edit(deafen=False, reason=f"Voice undeafened by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        await ctx.send_success(f"Voice undeafened {member.mention}")

    @group(name="clear", invoke_without_command=True)
    async def idk_clear(self, ctx):
        return await ctx.create_pages()

    @idk_clear.command(name="invites", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def clear_invites(self, ctx: PretendContext):
        """
        clear messages that contain discord invite links
        """

        regex = r"discord(?:\.com|app\.com|\.gg)/(?:invite/)?([a-zA-Z0-9\-]{2,32})"
        await ctx.channel.purge(limit=300, check=lambda m: re.search(regex, m.content))

    @idk_clear.command(brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def contains(self, ctx: PretendContext, *, word: str):
        """
        clear messages that contain a certain word
        """

        await ctx.channel.purge(limit=300, check=lambda m: word in m.content)

    @idk_clear.command(name="images", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def clear_images(self, ctx: PretendContext):
        """
        clear messages that have attachments
        """

        await ctx.channel.purge(limit=300, check=lambda m: m.attachments)

    @command(brief="manage messages", aliases=["c"])
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def purge(self, ctx: PretendContext, number: int, *, member: Member = None):
        """
        delete more messages at once
        """

        async with self.locks[ctx.channel.id]:
            if not member:
                check = lambda m: not m.pinned
            else:
                check = lambda m: m.author.id == member.id and not m.pinned

            await ctx.message.delete()
            await ctx.channel.purge(
                limit=number, check=check, reason=f"Chat purged by {ctx.author}"
            )

    @command(brief="manage messages", aliases=["bc", "bp", "botpurge"])
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def botclear(self, ctx: PretendContext):
        """
        delete messages sent by bots
        """

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=100,
                check=lambda m: m.author.bot and not m.pinned,
                reason=f"Bot messages purged by {ctx.author}",
            )

    @hybrid_command(brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def lock(self, ctx: PretendContext, *, channel: TextChannel = CurrentChannel):
        """
        lock a channel
        """

        if channel.overwrites_for(ctx.guild.default_role).send_messages is False:
            return await ctx.send_error("Channel is **already** locked")

        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = False
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=f"channel locked by {ctx.author}",
        )
        await self.bot.logs.send_moderator(ctx, channel)
        return await ctx.send_success(f"Locked {channel.mention}")

    @hybrid_command(brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def unlock(
        self, ctx: PretendContext, *, channel: TextChannel = CurrentChannel
    ):
        """
        unlock a channel
        """

        if (
            channel.overwrites_for(ctx.guild.default_role).send_messages is True
            or channel.overwrites_for(ctx.guild.default_role).send_messages is None
        ):
            return await ctx.send_error("Channel is **already** unlocked")

        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = None
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=f"channel unlocked by {ctx.author}",
        )
        await self.bot.logs.send_moderator(ctx, channel)
        return await ctx.send_success(f"Unlocked {channel.mention}")

    @hybrid_command(brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def slowmode(
        self,
        ctx: PretendContext,
        time: ValidTime,
        *,
        channel: TextChannel = CurrentChannel,
    ):
        """
        enable slowmode option in a text channel
        """

        await channel.edit(
            slowmode_delay=time, reason=f"Slowmode invoked by {ctx.author}"
        )
        await ctx.send_success(
            f"Slowmode for {channel.mention} set to **{format_timespan(time)}**"
        )

    @hybrid_command(brief="moderate members", aliases=["timeout"])
    @has_guild_permissions(moderate_members=True)
    @bot_has_guild_permissions(moderate_members=True)
    async def mute(
        self,
        ctx: PretendContext,
        member: NoStaff,
        time: ValidTime = 3600,
        *,
        reason: str = "No reason provided",
    ):
        """
        timeout a member
        """

        if member.is_timed_out():
            return await ctx.send_error(f"{member.mention} is **already** muted")

        if member.guild_permissions.administrator:
            return await ctx.send_warning("You **cannot** mute an administrator")

        await member.timeout(
            utils.utcnow() + datetime.timedelta(seconds=time), reason=reason
        )
        await self.bot.logs.send_moderator(ctx, member)
        if not await Invoking(ctx).send(member, reason):
            await ctx.send_success(
                f"Muted {member.mention} for {format_timespan(time)} - **{reason}**"
            )

    @hybrid_command(brief="moderate members", aliases=["untimeout"])
    @has_guild_permissions(moderate_members=True)
    @bot_has_guild_permissions(moderate_members=True)
    async def unmute(
        self,
        ctx: PretendContext,
        member: NoStaff,
        *,
        reason: str = "No reason provided",
    ):
        """
        Remove the timeout from a member
        """
        if not member.is_timed_out():
            return await ctx.send_error(f"{member.mention} is **not** muted")

        await member.timeout(None, reason=reason)
        await self.bot.logs.send_moderator(ctx, member)
        if not await Invoking(ctx).send(member, reason):
            await ctx.send_success(f"Unmuted {member.mention} - **{reason}**")

    @hybrid_command(brief="ban members")
    @has_guild_permissions(ban_members=True)
    @bot_has_guild_permissions(ban_members=True)
    async def ban(
        self,
        ctx: PretendContext,
        member: Union[Member, User],
        *,
        reason: str = "No reason provided",
    ):
        """
        ban a member from the server
        """

        if isinstance(member, Member):
            member = await NoStaff().convert(ctx, str(member.id))

            if member.premium_since:
                view = BoosterMod(ctx, member, reason)
                embed = Embed(
                    color=self.bot.color,
                    description=f"{ctx.author.mention}: Are you sure you want to **ban** {member.mention}? They're boosting this server since **{self.bot.humanize_date(datetime.datetime.fromtimestamp(member.premium_since.timestamp()))}**",
                )
                return await ctx.reply(embed=embed, view=view)

        await ctx.guild.ban(member, reason=reason)
        await self.bot.logs.send_moderator(ctx, member)
        await self.punish_a_bitch("ban", ctx.author, "Banning Members")
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Banned {member.mention} - **{reason}**")

    @hybrid_command(brief="kick members")
    @has_guild_permissions(kick_members=True)
    @bot_has_guild_permissions(kick_members=True)
    async def kick(
        self,
        ctx: PretendContext,
        member: NoStaff,
        *,
        reason: str = "No reason provided",
    ):
        """
        kick a member from the server
        """

        if ctx.guild.premium_subscriber_role in member.roles:
            view = BoosterMod(ctx, member, reason)
            embed = Embed(
                color=self.bot.color,
                description=f"{ctx.author.mention}: Are you sure you want to **kick** {member.mention}? They're boosting this server since **{self.bot.humanize_date(datetime.datetime.fromtimestamp(member.premium_since.timestamp()))}**",
            )
            return await ctx.reply(embed=embed, view=view)

        await member.kick(reason=reason)
        await self.bot.logs.send_moderator(ctx, member)
        await self.punish_a_bitch("ban", ctx.author, "Kicking Members")
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Kicked {member.mention} - **{reason}**")

    @command(brief="ban members")
    @admin_antinuke()
    @bot_has_guild_permissions(ban_members=True)
    async def unbanall(self, ctx: PretendContext):
        """
        unban all members from the server
        """

        async with self.locks[ctx.guild.id]:
            bans = [m.user async for m in ctx.guild.bans()]
#            await self.bot.logs.send_moderator(ctx)
            await ctx.pretend_send(f"Unbanning **{len(bans)}** members..")
            await asyncio.gather(*[ctx.guild.unban(Object(m.id)) for m in bans])

    @command(brief="ban members")
    @has_guild_permissions(ban_members=True)
    @bot_has_guild_permissions(ban_members=True)
    async def unban(
        self, ctx: PretendContext, member: User, *, reason: str = "No reason provided"
    ):
        """
        unban a member from the server
        """

        if not member.id in [m.user.id async for m in ctx.guild.bans()]:
            return await ctx.send_warning("This member is not banned")

        await ctx.guild.unban(user=member, reason=reason)
        await self.bot.logs.send_moderator(ctx, member)
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"I unbanned **{member}**")

    @hybrid_command(brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def strip(self, ctx: PretendContext, *, member: NoStaff):
        """
        remove someone's dangerous roles
        """

        roles = [
            role
            for role in member.roles
            if role.is_assignable()
            and not self.bot.is_dangerous(role)
            or role == ctx.guild.premium_subscriber_role
        ]
        await self.bot.logs.send_moderator(ctx, member)
        await member.edit(roles=roles, reason=f"member stripped by {ctx.author}")
        return await ctx.send_success(f"Stripped {member.mention}'s roles")

    @command(aliases=["nick"], brief="manage nicknames")
    @has_guild_permissions(manage_nicknames=True)
    @bot_has_guild_permissions(manage_nicknames=True)
    async def nickname(
        self, ctx: PretendContext, member: NoStaff, *, nick: ValidNickname
    ):
        """
        change a member's nickname
        """

        await member.edit(nick=nick, reason=f"Nickname changed by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        return await ctx.send_success(
            f"Changed {member.mention} nickname to **{nick}**"
            if nick
            else f"Removed {member.mention}'s nickname"
        )

    @group(invoke_without_command=True)
    @has_guild_permissions(manage_messages=True)
    async def warn(
        self,
        ctx: PretendContext,
        member: NoStaff = None,
        *,
        reason: str = "No reason provided",
    ):
        if member is None:
            return await ctx.create_pages()
        await self.bot.logs.send_moderator(ctx, member)
        date = datetime.datetime.now()
        await self.bot.db.execute(
            """
      INSERT INTO warns
      VALUES ($1,$2,$3,$4,$5)
      """,
            ctx.guild.id,
            member.id,
            ctx.author.id,
            f"{date.day}/{f'0{date.month}' if date.month < 10 else date.month}/{str(date.year)[-2:]} at {datetime.datetime.strptime(f'{date.hour}:{date.minute}', '%H:%M').strftime('%I:%M %p')}",
            reason,
        )
        await ctx.send_success(f"Warned {member.mention} | {reason}")

    @warn.command(name="clear", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    async def warn_clear(self, ctx: PretendContext, *, member: NoStaff):
        """
        clear all warns from an user
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM warns
      WHERE guild_id = $1
      AND user_id = $2
      """,
            ctx.guild.id,
            member.id,
        )

        if len(check) == 0:
            return await ctx.send_warning("this user has no warnings".capitalize())

        await self.bot.db.execute(
            "DELETE FROM warns WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member.id,
        )
        await ctx.send_success(f"Removed {member.mention}'s warns")

    @warn.command(name="list")
    async def warn_list(self, ctx: PretendContext, *, member: Member):
        """
        returns all warns that an user has
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM warns 
      WHERE guild_id = $1
      AND user_id = $2
      """,
            ctx.guild.id,
            member.id,
        )

        if len(check) == 0:
            return await ctx.send_warning("this user has no warnings".capitalize())

        return await ctx.paginate(
            [
                f"{result['time']} by <@!{result['author_id']}> - {result['reason']}"
                for result in check
            ],
            f"Warnings ({len(check)})",
            {"name": member.name, "icon_url": member.display_avatar.url},
        )

    @command()
    async def warns(self, ctx: PretendContext, *, member: Member):
        """
        shows all warns of an user
        """

        return await ctx.invoke(self.bot.get_command("warn list"), member=member)

    @command(brief="server owner")
    @admin_antinuke()
    @bot_has_guild_permissions(manage_channels=True)
    async def nuke(self, ctx: PretendContext):
        """
        replace the current channel with a new one
        """

        async with self.locks[ctx.channel.id]:

            async def yes_callback(interaction: Interaction) -> None:
                new_channel = await interaction.channel.clone(
                    name=interaction.channel.name,
                    reason="Nuking channel invoked by the server owner",
                )
                await new_channel.edit(
                    topic=interaction.channel.topic,
                    position=interaction.channel.position,
                    nsfw=interaction.channel.nsfw,
                    slowmode_delay=interaction.channel.slowmode_delay,
                    type=interaction.channel.type,
                    reason="Nuking channel invoked by the server owner",
                )

                await interaction.channel.delete(
                    reason="Channel nuked by the server owner"
                )
                await self.bot.logs.send_moderator(ctx, ctx.channel)
                await new_channel.send("💣")

            async def no_callback(interaction: Interaction) -> None:
                await interaction.response.edit_message(
                    embed=Embed(
                        color=self.bot.color, description="Cancelling action..."
                    ),
                    view=None,
                )

            await ctx.confirmation_send(
                f"{ctx.author.mention}: Are you sure you want to **nuke** this channel?\nThis action is **IRREVERSIBLE**",
                yes_callback,
                no_callback,
            )

    @command(brief="manage_roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def roleall(self, ctx: PretendContext, *, role: NewRoleConverter):
        """
        add a role to all members
        """

        async with self.role_lock[ctx.guild.id]:
            tasks = [
                m.add_roles(role, reason=f"Role all invoked by {ctx.author}")
                for m in ctx.guild.members
                if not role in m.roles
            ]

            if len(tasks) == 0:
                return await ctx.send_warning("Everyone has this role")

            mes = await ctx.pretend_send(
                f"Giving {role.mention} to **{len(tasks)}** members. This operation might take around **{format_timespan(0.3*len(tasks))}**"
            )
            await self.bot.logs.send_moderator(ctx, role)
            await asyncio.gather(*tasks)
            return await mes.edit(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {ctx.author.mention}: Added {role.mention} to **{len(tasks)}** members",
                )
            )

    @command(brief="manage_roles", aliases=["r"])
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def role(self, ctx: PretendContext, member: Member, *, role_string: str):
        """
        Add roles to a member
        """

        roles = [
            await NewRoleConverter().convert(ctx, r) for r in role_string.split(", ")
        ]

        if len(roles) == 0:
            return await ctx.send_help(ctx.command)

        if len(roles) > 7:
            return await ctx.send_error("Too many roles parsed")

        if any(self.bot.is_dangerous(r) for r in roles):
            if await self.bot.an.is_module("role giving", ctx.guild):
                if not await self.bot.an.is_whitelisted(ctx.author):
                    roles = [r for r in roles if not self.bot.is_dangerous(r)]

        if len(roles) > 0:
            async with self.locks[ctx.guild.id]:
                role_mentions = []
                for role in roles:
                    if not role in member.roles:
                        await member.add_roles(
                            role, reason=f"{ctx.author} added the role"
                        )
                        role_mentions.append(f"**+**{role.mention}")
                    else:
                        await member.remove_roles(
                            role, reason=f"{ctx.author} removed the role"
                        )
                        role_mentions.append(f"**-**{role.mention}")

                return await ctx.send_success(
                    f"Edited {member.mention}'s roles: {', '.join(role_mentions)}"
                )
        else:
            return await ctx.send_error("There are no roles that you can give")

    @group(
        name="thread",
        brief="manage threads",
        invoke_without_command=True
    )
    @has_guild_permissions(manage_threads=True)
    async def thread(self, ctx: PretendContext):
        """
        Manage threads/forum posts
        """

        await ctx.create_pages()

    @thread.command(
        name="lock",
        brief="manage threads"
    )
    @has_guild_permissions(manage_threads=True)
    async def thread_lock(self, ctx: PretendContext, thread: Thread = None):
        """
        Lock a thread/forum post
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a **thread**")
        
        if thread.locked:
            return await ctx.send_warning(f"{thread.mention} is already **locked**")
        
        await thread.edit(locked=True)
        await ctx.send_success(f"Successfully **locked** {thread.mention}")

    @thread.command(
        name="unlock",
        brief="manage threads"
    )
    @has_guild_permissions(manage_threads=True)
    async def thread_unlock(self, ctx: PretendContext, thread: Thread = None):
        """
        Unock a thread/forum post
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a **thread**")
        
        if not thread.locked:
            return await ctx.send_warning(f"{thread.mention} is already **unlocked**")
        
        await thread.edit(locked=False)
        await ctx.send_success(f"Successfully **unlocked** {thread.mention}")

    @thread.command(
        name="rename",
        brief="manage threads"
    )
    @has_guild_permissions(manage_threads=True)
    async def thread_rename(
        self,
        ctx: PretendContext,
        thread: Optional[Thread] = None,
        *,
        name: str
    ):
        """
        Rename a thread/forum post
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a **thread**")
        
        await thread.edit(name=name)
        await ctx.message.add_reaction("✅")

    @thread.command(
        name="delete",
        brief="manage threads"
    )
    @has_guild_permissions(manage_threads=True)
    async def thread_delete(self, ctx: PretendContext, thread: Thread = None):
        """
        Delete a thread/forum post
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a **thread**")

        await thread.delete()
        if thread != ctx.channel:
            await ctx.message.add_reaction("✅")

async def setup(bot: Pretend) -> None:
    await bot.add_cog(Moderation(bot))
