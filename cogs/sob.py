import discord
from discord.ext import commands
import json
import os

class sobCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = "/home/ubuntu/greedrecodetotallynotpretend/events/sob.json"
        self.ensure_file_exists()

    def ensure_file_exists(self):
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w") as f:
                json.dump({"server": {}}, f)

    async def log_server(self):
        await self.bot.wait_until_ready()
        current_server = {guild.id: {"sob_users": []} for guild in self.bot.guilds}
        data = {"server": current_server}
        self.save_data(data)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        data = self.load_data()
        guild_id = str(guild.id)
        if guild_id not in data["server"]:
            data["server"][guild_id] = {"sob_users": []}
            self.save_data(data)

    @commands.group()
    async def sob(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = self.generate_sob_help_embed()
            await ctx.send(embed=embed)

    @sob.command()
    @commands.has_permissions(manage_messages=True)
    async def add(self, ctx, user: discord.User):
        if ctx.guild is None:
            return await ctx.send("This command can only be used in a server.")
        
        data = self.load_data()
        guild_id = str(ctx.guild.id)
        if guild_id not in data["server"]:
            data["server"][guild_id] = {"sob_users": []}
        
        if str(user.id) not in data["server"][guild_id]["sob_users"]:
            data["server"][guild_id]["sob_users"].append(str(user.id))
            self.save_data(data)
            await ctx.send(embed=self.generate_embed(user, added=True))
        else:
            await ctx.send(f"{user.name} is already in the sob list.")

    @sob.command()
    @commands.has_permissions(manage_messages=True)
    async def remove(self, ctx, user: discord.User):
        if ctx.guild is None:
            return await ctx.send("This command can only be used in a server.")
        
        data = self.load_data()
        guild_id = str(ctx.guild.id)
        if guild_id not in data["server"]:
            return await ctx.send("There are no users in the sob list for this server.")
        
        if str(user.id) in data["server"][guild_id]["sob_users"]:
            data["server"][guild_id]["sob_users"].remove(str(user.id))
            self.save_data(data)
            await ctx.send(embed=self.generate_embed(user, added=False))
        else:
            await ctx.send(f"{user.name} is not in the sob list for this server.")

    async def sob_message(self, message):
        if not message.guild:
            return
        
        data = self.load_data()
        guild_id = str(message.guild.id)
        if guild_id in data["server"]:
            if str(message.author.id) in data["server"][guild_id]["sob_users"]:
                await message.add_reaction("😭")

    def generate_embed(self, user, added=True):
        action = "added to" if added else "removed from"
        embed = discord.Embed(
            title="sob update",
            description=f"<:check_white:1204583868435271731> sob reactions {action} {user.mention}'s messages.",
            color=self.bot.color if added else self.bot.color
        )
        return embed
    
    def generate_sob_help_embed(self):
        embed = discord.Embed(
            title="sob Command Help",
            description="Manage the sob list.",
            color=self.bot.color
        )
        embed.add_field(name="Add User to sob List", value="`sob add <@user>`", inline=False)
        embed.add_field(name="Remove User from sob List", value="`sob remove <@user>`", inline=False)
        return embed

    def load_data(self):
        with open(self.file_path, "r") as f:
            return json.load(f)

    def save_data(self, data):
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=4)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild:
            return
        
        data = self.load_data()
        guild_id = str(message.guild.id)
        if guild_id in data["server"]:
            if str(message.author.id) in data["server"][guild_id]["sob_users"]:
                await message.add_reaction("😭")

async def setup(bot):
    cog = sobCog(bot)
    await bot.add_cog(cog)
    await cog.log_server()
