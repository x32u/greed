import orjson
import asyncio
import aiohttp
import datetime
from discord.ui import Button, View
from typing import Optional
from collections import defaultdict
from discord.ext.commands import Cog
from discord import ButtonStyle, Embed, User, Member, Message, Button, utils
from tools.expiringdictionary import ExpiringDictionary
from discord.ui import View

from collections import defaultdict

from tools.bot import Pretend
from tools.asset import Storage


class Members(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.locks = defaultdict(asyncio.Lock)
#        self.assets = Storage(self.bot)
        self.to_send = []

        self.ratelimiter = ExpiringDictionary()

    async def get_user_avatar_url(self, member: User) -> Optional[str]:
        try:
            data = await member.display_avatar.read()
        except:
            return None

        token = member.display_avatar.url.split(".")[2].split("/")[-1]
        await self.bot.db.execute(
            """
        INSERT INTO avatar_urls 
        VALUES ($1,$2,$3)
        """,
            member.id,
            token,
            data,
        )

        return f"https://greed.best/images/{member.id}/{token}.{'gif' if member.display_avatar.is_animated() else 'png'}"



    @Cog.listener("on_user_update")
    async def avatarhistory_event(self, before, after):
        channel_id = 1225577288566046840
        if before.display_avatar.url != after.display_avatar.url:
            if "embed" in after.display_avatar.url:
                return
            if before.display_avatar != after.display_avatar:
                file = await after.display_avatar.to_file(
                    filename=f"{after.id}.{'png' if not after.display_avatar.is_animated() else 'gif'}"
                )

                # Sending the embed with the file to all specified channels
                self.to_send.append({'uid':after.id,'un':after.name,'file':file,'ts': int(datetime.datetime.now().timestamp())})

            if len(self.to_send) == 10:
                logs = self.bot.get_channel(channel_id)
                if logs:
                    message = await logs.send(files=[f['file'] for f in self.to_send])
                i = 0
                for attachment in message.attachments:
                    try:
                        await self.bot.db.execute("INSERT INTO avatars (user_id, avatar, ts, i, message_id) VALUES ($1,$2,$3,$4,$5)", self.to_send[i]['uid'], attachment.url, self.to_send[i]['ts'], i, message.id)
                    except:
                        pass
                    i+=1
                self.to_send = []
                await asyncio.sleep(15)

    @Cog.listener("on_member_join")
    async def on_joindm_event(self, member: Member):
        async with self.locks[f"joindm-{member.guild.id}"]:
            message = await self.bot.db.fetchval(
                """SELECT message FROM joindm WHERE guild_id = $1""", member.guild.id
            )
            if message:
                if await self.ratelimiter.ratelimit(
                    f"joindm-{member.guild.id}", 5, 20
                ):
                    await asyncio.sleep(5)

                x = await self.bot.embed_build.alt_convert(member, message)
                await member.send(x)


    @Cog.listener("on_member_join")
    async def on_autoping_event(self, member: Member):
        async with self.locks[f"autoping-{member.guild.id}"]:
            data = await self.bot.db.fetch(
                """SELECT channel_id, message FROM autoping WHERE guild_id = $1""",
                member.guild.id,
            )
            if not data:
                return
            for channel_id, message in data:
                if channel := self.bot.get_channel(channel_id):
                    perms = channel.permissions_for(member.guild.me)
                    if perms.send_messages and perms.embed_links:
                        x = await self.bot.embed_build.alt_convert(member, message)
                        await channel.send(**x)
                        await asyncio.sleep(0.4)


    @Cog.listener("on_user_update")
    async def username_change(self, before: User, after: User):
        if before.name != after.name:
            await self.bot.db.execute(
                "INSERT INTO usernames VALUES ($1,$2,$3)",
                after.id,
                str(before),
                int(datetime.datetime.now().timestamp()),
            )

    @Cog.listener("on_member_update")
    async def on_boost_role_update(self, before: Member, after: Member):
        if (
            not before.guild.premium_subscriber_role in before.roles
            and after.guild.premium_subscriber_role in after.roles
        ):
            if before.guild.system_channel:
                return

            results = await self.bot.db.fetch(
                "SELECT * FROM boost WHERE guild_id = $1", after.guild.id
            )
            for result in results:
                channel = self.bot.get_channel(result["channel_id"])
                if channel:
                    perms = channel.permissions_for(after.guild.me)
                    if perms.send_messages and perms.embed_links:
                        x = await self.bot.embed_build.alt_convert(
                            after, result["message"]
                        )
                        await channel.send(**x)
                        await asyncio.sleep(0.4)

    @Cog.listener("on_member_join")
    async def on_new_member(self, member: Member):
        results = await self.bot.db.fetch(
            "SELECT * FROM welcome WHERE guild_id = $1", member.guild.id
        )
        for result in results:
            channel = self.bot.get_channel(result["channel_id"])
            if channel:
                perms = channel.permissions_for(member.guild.me)
                if perms.send_messages and perms.embed_links:
                    x = await self.bot.embed_build.alt_convert(
                        member, result["message"]
                    )
                    await channel.send(**x)
                    await asyncio.sleep(0.4)

    @Cog.listener("on_member_remove")
    async def on_leave_event(self, member: Member):
        results = await self.bot.db.fetch(
            "SELECT * FROM leave WHERE guild_id = $1", member.guild.id
        )
        for result in results:
            channel = self.bot.get_channel(result["channel_id"])
            if channel:
                perms = channel.permissions_for(member.guild.me)
                if perms.send_messages and perms.embed_links:
                    x = await self.bot.embed_build.alt_convert(
                        member, result["message"]
                    )
                    await channel.send(**x)
                    await asyncio.sleep(0.4)

    @Cog.listener("on_member_join")
    async def on_autorole(self, member: Member):
        if member.guild.me.guild_permissions.manage_roles:
            if member.guild.id == 1005150492382478377:
                check = await self.bot.db.fetchrow(
                    "SELECT * FROM authorize WHERE user_id = $1", member.id
                )
                if check:
                    await member.add_roles(
                        member.guild.get_role(1124447347783520318),
                        reason="Subscriber joined the server",
                    )

            results = await self.bot.db.fetch(
                "SELECT * FROM autorole WHERE guild_id = $1", member.guild.id
            )
            for result in results:
                role = member.guild.get_role(result["role_id"])
                if role:
                    if role.is_assignable():
                        await member.add_roles(role, reason="AutoRole")

    @Cog.listener("on_member_remove")
    async def on_boost_remove(self, before: Member):
        check = await self.bot.db.fetchrow(
            "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            before.guild.id,
            before.id,
        )
        if check:
            role = before.guild.get_role(int(check["role_id"]))
            await self.bot.db.execute(
                "DELETE FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
                before.guild.id,
                before.id,
            )
            await role.delete(reason="booster left the server")

    @Cog.listener("on_member_update")
    async def on_boost_transfered(self, before: Member, after: Member):
        if (
            before.guild.premium_subscriber_role in before.roles
            and not after.guild.premium_subscriber_role in after.roles
        ):
            check = await self.bot.db.fetchrow(
                "SELECT role_id FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
                before.guild.id,
                before.id,
            )
            if check:
                role = before.guild.get_role(int(check["role_id"]))
                await self.bot.db.execute(
                    "DELETE FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
                    before.guild.id,
                    before.id,
                )
                await role.delete(reason="booster transfered all their boosts")

    @Cog.listener("on_user_update")
    async def on_username_tracking(self, before: User, after: User):
        if str(before) != str(after):
            results = await self.bot.db.fetch("SELECT webhook_url FROM username_track")
            headers = {"Content-Type": "application/json"}

            json = {
                "username": "pretend-usernames",
                "content": f"New username available: **{before}**",
                "avatar_url": self.bot.user.display_avatar.url,
            }

            for result in results:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.post(result["webhook_url"], json=json) as r:
                        if not r.status in [204, 429]:
                            await self.bot.db.execute(
                                "DELETE FROM username_track WHERE webhook_url = $1",
                                result["webhook_url"],
                            )


async def setup(bot: Pretend) -> None:
    await bot.add_cog(Members(bot))
