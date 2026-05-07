import discord
from discord.ext import tasks, commands
from curl_cffi import requests
import os
import random
import string

TOKEN = os.getenv('DISCORD_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Storage for user settings (In a real app, use a database)
user_configs = {}

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

async def run_bump(user_id):
    config = user_configs.get(user_id)
    if not config: return

    ref = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    url = f"https://oguser.com/newreply.php?tid={config['tid']}&processed=1"
    
    payload = {
        "my_post_key": config['post_key'],
        "tid": config['tid'],
        "action": "do_newreply",
        "message": f"bump\n\n[size=xx-small]Ref: {ref}[/size]",
        "submit": "Post Reply"
    }

    cookies = {'mybbuser': config['mybbuser'], 'sid': config['sid']}
    
    r = requests.post(url, data=payload, cookies=cookies, impersonate="chrome110")
    
    status = "✅ **Bump Success**" if r.status_code == 200 else f"❌ **Failed** ({r.status_code})"
    requests.post(WEBHOOK_URL, json={"content": f"User <@{user_id}>: {status} | Ref: {ref}"})

@tasks.loop(minutes=61)
async def global_bump_loop():
    for user_id in list(user_configs.keys()):
        await run_bump(user_id)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.hybrid_command(name="setup", description="Link your OGUser info to the bumper")
async def setup(ctx, thread_id: str, post_key: str, mybbuser: str, sid: str):
    user_configs[ctx.author.id] = {
        "tid": thread_id,
        "post_key": post_key,
        "mybbuser": mybbuser,
        "sid": sid
    }
    await ctx.send(f"✅ Setup complete for Thread `{thread_id}`! Use `!start` to begin your loop.", ephemeral=True)

@bot.hybrid_command(name="start", description="Start your auto-bump loop")
async def start(ctx):
    if ctx.author.id not in user_configs:
        return await ctx.send("❌ You haven't used `/setup` yet!")
    
    if not global_bump_loop.is_running():
        global_bump_loop.start()
    
    await ctx.send("🚀 **Auto-Bumper Activated.**")

bot.run(TOKEN)
