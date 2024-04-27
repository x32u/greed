from asyncio import gather, to_thread as thread, sleep, create_subprocess_shell as shell
from asyncio.subprocess import PIPE
from aiofiles import open as async_open
import os
from aiohttp import ClientSession as Session
from io import BytesIO
from tuuid import tuuid
from discord import File, Embed
from discord.ext.commands import Context, CommandError
from typing import Optional
class Conversion:
    def __init__(self):
        self.command = "ffmpeg"
    
    async def download(self, url: str) -> str:
        async with Session() as session:
            async with session.get(url) as resp:
                data = await resp.read()
        fp = f"{tuuid()}.mp4"
        async with async_open(fp, "wb") as file:
            await file.write(data)
        return fp
    
    async def convert(self, fp: str) -> str:
        _fp = f"{tuuid()}.gif"
        process = await shell(f"{self.command} -i {fp} {_fp}", stdout = PIPE)
        await process.communicate()
        os.remove(fp)
        if not os.path.exists(_fp):
            raise CommandError(f"Could not convert the file")
        return _fp
    
    async def do_conversion(self, ctx: Context, url: Optional[str] = None):
        if not url:
            if len(ctx.message.attachments) > 0:
                url = ctx.message.attachments[0].url
            else:
                raise CommandError(f"please provide an attachment")
        filepath = await self.download(url)
        converted = await self.convert(filepath)
        await ctx.send(embed = Embed(color = ctx.bot.color, description = f"heres your gif.."), file = File(converted))
        os.remove(converted)
    