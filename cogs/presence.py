from typing import Optional, Union, Any
from discord import Member, User, File, Guild, Role
from dataclasses import dataclass
import discord
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageMath
import datetime, asyncio
from io import BytesIO
from asyncio import to_thread as thread, Lock
from humanize import naturaldelta
from discord.ext import commands, tasks
from discord.ext.commands import Context
from collections import defaultdict
try:
	from functions import util
except:
	pass
import matplotlib
matplotlib.use('agg')
plt.switch_backend('agg')
intents = discord.Intents.all()

@dataclass
class Vanity:
	vanity: str
	role: Role

class Pres(commands.Bot):
	def __init__(self, cog):
		self.cog = cog
		super().__init__(intents = discord.Intents.all(), command_prefix = "46464636363363636363636363363637$3$3$3$32$2$4$", help_command = None)

	async def get_user(self, user: int):
		if user := self.get_user(user): return user
		else: raise discord.ext.commands.error.CommandError(f"User is not fetchable")

	def get_member(self, guild: discord.Guild, member_id: int) -> Optional[Member]:
		if member := guild.get_member(member_id):
			return member
		else:
			return None

	async def on_presence_update(self, before: Member, after: Member):
		await self.cog.write_usage(after, before, after)
		await self.cog.check_vanity_role(before, after)

class Presence(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		self.locks = defaultdict(Lock)
		self.users={}
		self.pres = Pres(cog = self)
		self.cache = {}
		self.update_screentime.start()

	async def cog_load(self):
		if self.bot.user.name != "rival":
			await self.bot.db.execute("""CREATE TABLE IF NOT EXISTS screentime_overall (user_id BIGINT NOT NULL, online DECIMAL DEFAULT 0.0, offline DECIMAL DEFAULT 0.0, idle DECIMAL DEFAULT 0.0, dnd DECIMAL DEFAULT 0.0, streaming DECIMAL DEFAULT 0.0, PRIMARY KEY (user_id));""")
		self.users = {user.id: datetime.datetime.now().timestamp() for user in self.bot.users}


	async def get_vanity_data(self, guild: Guild) -> Optional[Vanity]:
		if data := await self.bot.db.fetchval("""SELECT role_id FROM vanity_role WHERE guild_id = $1""", guild.id):
			if vanity := guild.vanity_url_code:
				if role := guild.get_role(data):
					return Vanity(vanity, role)
				else:
					return None
				
	def activity(self, member: discord.Member):
		if member.activity:
			if member.activity.name != None: return member.activity.name
			else: return ""
		return ""

	async def check_vanity_role(self, before: Member, after: Member):
		if self.activity(before) != self.activity(after):
			vanity_data = self.cache.get(before.guild.id, None)
			if vanity_data == None:
				vanity_data = await self.get_vanity_data(after.guild)
				if vanity_data == None:
					return
				else:
					self.cache[after.guild.id] = vanity_data
			if f"/{vanity_data.vanity} " not in self.activity(after) and self.activity(after) != f"/{vanity_data.vanity}" and vanity_data.role in after.roles:
				await after.remove_roles(vanity_data.role)
			if f"/{vanity_data.vanity} " in self.activity(after) or self.activity(after) == f"/{vanity_data.vanity}":
				if vanity_data.role in after.roles:
					return
				else:
					return await after.add_roles(vanity_data.role)
			
	@commands.command(name = 'vanityrole', usage = "manage_guild")
	@commands.has_permissions(manage_guild = True)
	async def vanityrole(self, ctx, *, role: Optional[Role] = None):
		vanity = ctx.guild.vanity_url_code
		if vanity == None:
			return await ctx.send_warning(f"you cannot use **vanity roles**")
		if role == None:
			await self.bot.db.execute("""DELETE FROM vanity_role WHERE guild_id = $1""", ctx.guild.id)
			try:
				self.cache.pop(ctx.guild.id)
			except:
				pass
			return await ctx.send_success(f"successfully **disabled** vanity roles")
		else:
			await self.bot.db.execute("""INSERT INTO vanity_role (guild_id, role_id) VALUES($1,$2) ON CONFLICT (guild_id) DO UPDATE SET role_id = excluded.role_id""", ctx.guild.id, role.id)
			self.cache[ctx.guild.id] = Vanity(vanity = vanity, role = role)
			return await ctx.send_success(f"successfully **enabled** vanity roles, vanity repping will now reward with {role.mention}")



	async def write_usage(self, member: Member, before: Member, after: Member):
		async with self.locks['screentime']:
			if hasattr(self.bot, "redis") and self.bot.user.name == "rival":
				check=await self.bot.redis.ratelimited(f"st{member.id}",1,10,1)
				if check == True: return
				online=0
				offline=0
				idle=0
				dnd=0
				if member.id in self.users:
					elapsed = datetime.datetime.now().timestamp() - self.users[member.id]
					if str(before.status) == "online": online+=elapsed
					if str(before.status) == "offline": offline+=elapsed
					if str(before.status) == "idle": idle+=elapsed
					if str(before.status) == "dnd": dnd+=elapsed
					await self.bot.db.execute("""INSERT INTO screentime_overall (user_id,online,offline,idle,dnd) VALUES(%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE online = online + VALUES(online), offline = offline + VALUES(offline), idle = idle + VALUES(idle), dnd = dnd + VALUES(dnd)""",member.id,online,offline,idle,dnd)
					self.users[member.id] = datetime.datetime.now().timestamp()
				else:
					self.users[member.id] = datetime.datetime.now().timestamp()
			else:
				online=0.0
				offline=0.0
				idle=0.0
				dnd=0.0
				streaming = 0.0
				if member.id in self.users:
					if before.status != after.status:
						elapsed = datetime.datetime.now().timestamp() - self.users[member.id]
						if str(before.status) == "online": online+=elapsed
						if str(before.status) == "offline": offline+=elapsed
						if str(before.status) == "idle": idle+=elapsed
						if str(before.status) == "dnd": dnd+=elapsed
						if before.activity != None:
							if before.activity.type.name == "streaming": streaming+=elapsed
						await self.bot.db.execute("""INSERT INTO screentime_overall (user_id, online, offline, idle, dnd, streaming) VALUES($1, $2, $3, $4, $5, $6) ON CONFLICT(user_id) DO UPDATE SET online = screentime_overall.online + excluded.online, offline = screentime_overall.offline + screentime_overall.offline, idle = screentime_overall.idle + excluded.idle, dnd = screentime_overall.dnd + excluded.dnd, streaming = screentime_overall.streaming + excluded.streaming""", member.id, online, offline, idle, dnd, streaming)
						self.users[member.id] = datetime.datetime.now().timestamp()
				else:
					self.users[member.id] = datetime.datetime.now().timestamp()
		return True
		
	@tasks.loop(hours=1)
	async def update_screentime(self):
		l=list(self.users.keys())
		for m in l:
			try:
				if member := self.bot.get_user(m):
					if hasattr(self.bot, "redis") and self.bot.user.name == "rival":
						if await self.bot.redis.ratelimited(f'sc{member.id}',1,30,1) != True:
							if member:
								await self.write_usage(member, member, member)
					else:
						if member:
							await self.write_usage(member, member, member)
			except:
				pass
		del l

	async def get_all_commands(self):
		if not hasattr(self.bot, 'command_list'):
			commands = {}
			for command in self.bot.walk_commands():
				commands[command.qualified_name.lower()] = command
				for alias in command.aliases:
					commands[alias.lower()] = command
			self.bot.command_list = commands
			del commands
		return self.bot.command_list			

	@commands.Cog.listener('on_presence_update')
	async def on_screentime_update(self, before: Member, after: Member):
		return await self.write_usage(before, before, after)

    
	async def make_chart(self, member: Union[Member, User], data: Any) -> File:
		def do_generation(member: Union[Member, User], data: Any, avatar: bytes):
			member = member
			if self.bot.user.name == "rival":
				status = ['online', 'idle', 'dnd', 'offline']
				seconds = [0, 0, 0, 0]
				for i, s in enumerate(status):
					seconds[i] += data[i]
				durations = [naturaldelta(datetime.timedelta(seconds = s)) for s in seconds]
				colors = ['#43b581', '#faa61a', '#f04747', '#747f8d']
			else:
				status = ['online', 'idle', 'dnd', 'offline', 'streaming']
				seconds = [0, 0, 0, 0, 0]
				for i, s in enumerate(status):
					seconds[i] += int(data[i])
				durations = [naturaldelta(datetime.timedelta(seconds = s)) for s in seconds]
				colors = ['#43b581', '#faa61a', '#f04747', '#747f8d', '#593695']
			fig, ax = plt.subplots(figsize=(6, 8))
			wedges, _ = ax.pie(seconds, colors=colors, startangle=90, wedgeprops=dict(width=0.3))
			ax.axis('equal')
			ax.set_aspect('equal')
			img = Image.open(BytesIO(avatar)).convert("RGBA")
			if img.format == 'GIF':
				img = img.convert('RGBA').copy()
			mask = Image.new('L', img.size, 0)
			draw = ImageDraw.Draw(mask)
			draw.ellipse((0, 0) + img.size, fill=255)
			alpha = ImageMath.eval("a*b/255", a=img.split()[3], b=mask).convert("L")
			img.putalpha(alpha)
			width, height = img.size
			aspect_ratio = height / width
			half_width = 0.91
			half_height = aspect_ratio * half_width
			extent = [-half_width, half_width, -half_height, half_height]
			plt.imshow(img, extent=extent, zorder=-1)
			legend = ax.legend(wedges, durations, title=f"{member.name}'s activity overall", loc="upper center", bbox_to_anchor=(0.5, 0.08))
			frame = legend.get_frame()
			frame.set_facecolor('#2C2F33')
			frame.set_edgecolor('#23272A')
			for text in legend.get_texts():
				text.set_color('#FFFFFF')
			plt.setp(legend.get_title(), color='w')
			buffer = BytesIO()
			plt.savefig(buffer, transparent=True)
			buffer.seek(0)
			file = File(fp = buffer, filename=f"{member.name}.png")
			return file
		avatar = await member.display_avatar.read()
		file = await thread(do_generation, member, data, avatar)
		return file
	
	@commands.command(name="screentime",aliases=['screen'],description="show screentime statistics",brief="member")
	async def screentime(self, ctx, *, member: Union[Member,User] = commands.Author):
		await self.pres.get_user(member.id)
		if self.bot.user.name == "rival":
			data = await self.bot.db.execute("""SELECT online,idle,dnd,offline FROM screentime_overall WHERE user_id = %s""", member.id)
		else:
			data = await self.bot.db.fetchrow("""SELECT online,idle,dnd,offline,streaming FROM screentime_overall WHERE user_id = $1""", member.id)
		if not data: 
			if self.bot.user.name == "rival":
				return await util.send_error(ctx,f"no data found")
			else:
				return await ctx.send_warning(f"no data found for {member.mention}")
		if self.bot.user.name == "rival":
			for online,idle,dnd,offline in data:
				dataset = [int(online),int(idle),int(dnd),int(offline)]
		else:
			dataset = [int(data['online']), int(data['idle']), int(data['dnd']), int(data['offline']), int(data['streaming'])]
		try:
			now = int(datetime.datetime.now().timestamp())
			if member.id in self.users:
				if str(member.status) == "online": dataset[0]+=(now-self.users[member.id])
				elif str(member.status) == "idle": dataset[1]+=(now-self.users[member.id])
				elif str(member.status) == "dnd": dataset[2]+=(now-self.users[member.id])
				elif self.bot.user.name != "rival" and member.activity != None:
					if member.activity.type.name == "streaming": dataset[4]+=(now-self.users[member.id])
				else: dataset[3]+=(now-self.users[member.id])
			chart = await self.make_chart(member, dataset)
			await ctx.send(file = chart)
		except: 
			if self.bot.user.name == "rival":
				try:
					await util.send_error(ctx,f"no data found")
				except:
					pass
			else:
				try:
					await ctx.send_warning(f"no data found for {member.mention}")
				except:
					pass
		del dataset

async def setup(bot):
#    presence_bot = commands.Bot(command_prefix="$", intents=intents)
	await bot.add_cog(Presence(bot))
