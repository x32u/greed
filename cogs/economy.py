import discord
from discord.ext import commands
import sqlite3
from random import randint, choice

class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.conn = sqlite3.connect('economy.db')
        self.cursor = self.conn.cursor()

        # Create tables if not exists
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            user_id INTEGER PRIMARY KEY,
                            username TEXT UNIQUE,
                            balance INTEGER DEFAULT 0,
                            bank_balance INTEGER DEFAULT 0
                            )''')

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS members (
                            user_id INTEGER,
                            guild_id INTEGER,
                            FOREIGN KEY (user_id) REFERENCES users(user_id),
                            FOREIGN KEY (guild_id) REFERENCES guilds(guild_id)
                            )''')

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                            transaction_id INTEGER PRIMARY KEY,
                            sender_id INTEGER,
                            receiver_id INTEGER,
                            amount INTEGER,
                            transaction_type TEXT,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (sender_id) REFERENCES users(user_id),
                            FOREIGN KEY (receiver_id) REFERENCES users(user_id)
                            )''')

        self.conn.commit()

        # Load jobs from file
        with open('/home/ubuntu/greedrecodetotallynotpretend/texts/jobs.txt', 'r') as file:
            self.jobs = file.read().splitlines()

    async def _send_embed(self, ctx, content):
        embed = discord.Embed(description=content, color=self.bot.color)
        await ctx.send(embed=embed)

    @commands.command(aliases=['bal'])
    async def balance(self, ctx):
        user_id = ctx.author.id
        self.cursor.execute("SELECT balance, bank_balance FROM users WHERE user_id = ?", (user_id,))
        balances = self.cursor.fetchone()
        if balances:
            money_balance = balances[0]
            bank_balance = balances[1]
            embed = discord.Embed(title=":bank: Balance", color=self.bot.color)
            embed.add_field(name="Wallet", value=f":money_with_wings: **{money_balance}**", inline=False)
            embed.add_field(name="Bank", value=f":bank: **{bank_balance}**", inline=False)
            await ctx.send(embed=embed)
        else:
            await self._send_embed(ctx, "You don't have an account yet. Use `,register` to create one.")

    @commands.command()
    async def register(self, ctx):
        user_id = ctx.author.id
        username = ctx.author.display_name
        try:
            self.cursor.execute("INSERT INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
            self.cursor.execute("INSERT INTO members (user_id, guild_id) VALUES (?, ?)", (user_id, ctx.guild.id))
            self.conn.commit()
            await self._send_embed(ctx, "You have been registered successfully!")
        except sqlite3.IntegrityError:
            await self._send_embed(ctx, "You are already registered.")

    @commands.command()
    async def rob(self, ctx, target: discord.Member):
        # Rob logic implementation
        # Example: You can rob between 1% to 10% of the target's balance
        user_id = ctx.author.id
        target_id = target.id

        self.cursor.execute("SELECT balance FROM users WHERE user_id = ?", (target_id,))
        target_balance = self.cursor.fetchone()
        if not target_balance:
            await self._send_embed(ctx, "The target doesn't have an account.")
            return

        self.cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user_balance = self.cursor.fetchone()[0]

        rob_percentage = randint(1, 10) / 100
        rob_amount = int(target_balance[0] * rob_percentage)

        if rob_amount > 0 and rob_amount <= user_balance:
            self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (rob_amount, user_id))
            self.cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (rob_amount, target_id))
            self.conn.commit()
            await self._send_embed(ctx, f"You robbed :money_with_wings: **{rob_amount}** from {target.display_name}!")
        else:
            await self._send_embed(ctx, "You failed to rob.")

    @commands.command()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def work(self, ctx):
        user_id = ctx.author.id
        income = randint(125, 4000)
        job = choice(self.jobs)
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (income, user_id))
        self.conn.commit()
        content = f"You worked as a **{job}** and earned **{income}** :money_with_wings:"
        await self._send_embed(ctx, content)


    @commands.command(aliases=["dd"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def dumpsterdive(self, ctx):
        user_id = ctx.author.id
        income = randint(50, 200)
        job = choice(self.jobs)
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (income, user_id))
        self.conn.commit()
        content = f"You decided to dumpster dive and found **{income}** :money_with_wings: nasty rat.."
        await self._send_embed(ctx, content)


    @work.error
    async def work_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await self._send_embed(ctx, f"You can work again in {error.retry_after:.0f} seconds.")

    @commands.command()
    async def deposit(self, ctx, amount: int):
        user_id = ctx.author.id
        if amount <= 0:
            await self._send_embed(ctx, "Amount must be positive.")
            return

        self.cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        self.cursor.execute("UPDATE users SET bank_balance = bank_balance + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()
        await self._send_embed(ctx, f"Deposited :money_with_wings: **{amount}** into your bank account!")

    @commands.command(aliases=['depall'])
    async def deposit_all(self, ctx):
        user_id = ctx.author.id

        self.cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = self.cursor.fetchone()[0]

        if balance <= 0:
            await self._send_embed(ctx, "You don't have any money to deposit.")
            return

        self.cursor.execute("UPDATE users SET bank_balance = bank_balance + balance WHERE user_id = ?", (user_id,))
        self.cursor.execute("UPDATE users SET balance = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()
        await self._send_embed(ctx, f"Deposited :money_with_wings: **{balance}** into your bank account!")

    @commands.command()
    async def withdraw(self, ctx, amount: int):
        user_id = ctx.author.id
        self.cursor.execute("SELECT bank_balance FROM users WHERE user_id = ?", (user_id,))
        bank_balance = self.cursor.fetchone()[0]
        if amount <= 0 or amount > bank_balance:
            await self._send_embed(ctx, "Invalid amount or insufficient balance in bank.")
            return

        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        self.cursor.execute("UPDATE users SET bank_balance = bank_balance - ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()
        await self._send_embed(ctx, f"Withdrew :money_with_wings: **{amount}** from your bank account!")

    @commands.command()
    async def wealthy(self, ctx):
          guild_id = ctx.guild.id
          self.cursor.execute("""
              SELECT username, (balance + bank_balance) AS total_balance 
              FROM users 
              WHERE EXISTS (
                  SELECT 1 FROM members 
                  WHERE users.user_id = members.user_id AND members.guild_id = ?
              ) 
              ORDER BY total_balance DESC 
              LIMIT 10
          """, (guild_id,))
          rows = self.cursor.fetchall()

          if not rows:
              await self._send_embed(ctx, "There are no users with balances in this guild.")
              return

          leaderboard_text = "\n".join(f"{index + 1}. **{row[0]}  ${row[1]}**" for index, row in enumerate(rows))
          embed = discord.Embed(title=f"Richest users in {ctx.guild.name}", description=leaderboard_text, color=self.bot.color)
          await ctx.send(embed=embed)


    @commands.command()
    async def close(self, ctx):
        # Close bank account
        user_id = ctx.author.id
        self.cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        self.cursor.execute("DELETE FROM members WHERE user_id = ?", (user_id,))
        self.conn.commit()
        await self._send_embed(ctx, "Your account has been closed.")




    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def gamble(self, ctx, amount: int):
        user_id = ctx.author.id
        self.cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user_balance = self.cursor.fetchone()[0]

        if amount <= 0:
            await self._send_embed(ctx, "Amount must be positive.")
            return

        if amount > user_balance:
            await self._send_embed(ctx, "You don't have enough money to gamble.")
            return

        outcome = randint(0, 1)  # 0 for loss, 1 for win
        if outcome == 1:
            self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            self.conn.commit()
            await self._send_embed(ctx, f"You won :money_with_wings: **{amount}**!")
        else:
            self.cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
            self.conn.commit()
            await self._send_embed(ctx, f"You lost :money_with_wings: **{amount}**.")



    @commands.command()
    async def give(self, ctx, recipient: discord.Member, amount: int):
        if amount <= 0:
            await self._send_embed(ctx, "Invalid amount.")
            return

        sender_id = ctx.author.id
        recipient_id = recipient.id

        self.cursor.execute("SELECT balance FROM users WHERE user_id = ?", (sender_id,))
        sender_balance = self.cursor.fetchone()[0]
        if amount > sender_balance:
            await self._send_embed(ctx, "You don't have enough balance to give.")
            return

        # Transfer money
        self.cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, sender_id))
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, recipient_id))
        self.conn.commit()
        await self._send_embed(ctx, f"You gave :money_with_wings: **{amount}** to {recipient.display_name}.")

    def cog_unload(self):
        self.cursor.close()
        self.conn.close()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
    
        user_id = message.author.id

        # Check if the user is registered
        self.cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        user_exists = self.cursor.fetchone()

        if user_exists:
            income = randint(1, 20)
            self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (income, user_id))
            self.conn.commit()
        else:
            # If the user is not registered, do nothing or you can prompt them to register
            pass

async def setup(bot):
    await bot.add_cog(EconomyCog(bot))

