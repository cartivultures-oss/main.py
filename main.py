import discord
from discord.ext import tasks, commands
from curl_cffi import requests
import os
import random
import string
import asyncio
from datetime import datetime, timedelta

TOKEN = os.getenv('DISCORD_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Temporary storage for users
user_configs = {} 

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

async def run_bump(user_id):
    config = user_configs.get(user_id)
    if not config: return None

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
    
    try:
        r = requests.post(url, data=payload, cookies=cookies, impersonate="chrome110")
        success = r.status_code == 200
        status_text = "✅ Success" if success else f"❌ Failed ({r.status_code})"
    except:
        status_text = "⚠️ Connection Error"

    # Send update to your private webhook
    requests.post(WEBHOOK_URL, json={"content": f"User <@{user_id}>: {status_text} | Ref: {ref}"})
    return status_text

@tasks.loop(minutes=5)
async def global_timer_loop():
    for user_id, config in user_configs.items():
        if not config.get('active'): continue
        
        now = datetime.now()
        # If it's time to bump (60 mins passed)
        if now >= config['next_bump']:
            status = await run_bump(user_id)
            config['next_bump'] = now + timedelta(minutes=61)
            config['last_status'] = status
        
        # Calculate countdown
        diff = config['next_bump'] - now
        minutes_left = int(diff.total_seconds() / 60)
        
        # Update the Discord message the user sees
        if config.get('status_msg'):
            try:
                embed = discord.Embed(title="OGUser Auto-Bumper", color=0x3498db)
                embed.add_field(name="Thread ID", value=config['tid'], inline=True)
                embed.add_field(name="Next Bump In", value=f"⏳ {minutes_left} minutes", inline=True)
                embed.add_field(name="Last Result", value=config.get('last_status', 'Waiting...'), inline=False)
                embed.set_footer(text="Updates every 5 minutes")
                
                msg = config['status_msg']
                await msg.edit(content=None, embed=embed)
            except:
                pass # Message might have been deleted

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.hybrid_command(name="setup", description="Link your OGUser info")
async def setup(ctx, thread_id: str, post_key: str, mybbuser: str, sid: str):
    user_configs[ctx.author.id] = {
        "tid": thread_id,
        "post_key": post_key,
        "mybbuser": mybbuser,
        "sid": sid,
        "active": False,
        "next_bump": datetime.now()
    }
    await ctx.send("✅ Info saved! Type `!start` to begin the countdown.", ephemeral=True)

@bot.hybrid_command(name="start", description="Start your auto-bump loop")
async def start(ctx):
    if ctx.author.id not in user_configs:
        return await ctx.send("❌ Use `/setup` first!")
    
    user_configs[ctx.author.id]['active'] = True
    user_configs[ctx.author.id]['next_bump'] = datetime.now() # Bump immediately on start
    
    # Create the live-updating message
    msg = await ctx.send("🚀 Starting Bumper... generating timer...")
    user_configs[ctx.author.id]['status_msg'] = msg

    if not global_timer_loop.is_running():
        global_timer_loop.start()

bot.run(TOKEN)
