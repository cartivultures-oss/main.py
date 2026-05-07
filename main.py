import discord
from discord.ext import tasks, commands
from curl_cffi import requests
import os
import random
import string
import json
import redis
from datetime import datetime, timedelta

TOKEN = os.getenv('DISCORD_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Connect to Railway's Redis
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
db = redis.from_url(redis_url, decode_responses=True)

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

active_messages = {}

async def run_bump(user_id, config):
    ref = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # Updated URL and Headers to mimic a real browser perfectly
    url = f"https://oguser.com/newreply.php?tid={config['tid']}&processed=1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Referer": f"https://oguser.com/showthread.php?tid={config['tid']}",
        "Origin": "https://oguser.com",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    payload = {
        "my_post_key": config['post_key'],
        "tid": config['tid'],
        "action": "do_newreply",
        "message": f"bump\n\n[size=xx-small]Ref: {ref}[/size]",
        "posthash": "",
        "quoted_ids": "",
        "lastpid": "",
        "from_page": "",
        "submit": "Post Reply"
    }

    cookies = {'mybbuser': config['mybbuser'], 'sid': config['sid']}
    
    try:
        # Using curl_cffi to bypass potential Cloudflare/bot detection
        r = requests.post(url, data=payload, cookies=cookies, headers=headers, impersonate="chrome110")
        
        # Checking if the post was successful based on status or page text
        if r.status_code == 200:
            if "Your message has been posted" in r.text or "redirect" in r.text or r.url != url:
                status_text = "✅ Success"
            else:
                status_text = "❌ Error (Check Login/Cookies)"
        else:
            status_text = f"❌ Failed ({r.status_code})"
    except Exception as e:
        status_text = f"⚠️ Connection Error"

    if WEBHOOK_URL:
        try: requests.post(WEBHOOK_URL, json={"content": f"User <@{user_id}>: {status_text} | Ref: {ref}"})
        except: pass
        
    return status_text

@tasks.loop(minutes=5)
async def global_timer_loop():
    all_users = db.hgetall("user_configs")
    
    for user_id, config_json in all_users.items():
        config = json.loads(config_json)
        if not config.get('active'): continue
        
        now = datetime.now()
        next_bump = datetime.fromisoformat(config['next_bump'])

        if now >= next_bump:
            status = await run_bump(user_id, config)
            config['next_bump'] = (now + timedelta(minutes=61)).isoformat()
            config['last_status'] = status
            db.hset("user_configs", user_id, json.dumps(config))
        
        if user_id in active_messages:
            try:
                diff = next_bump - now
                minutes_left = max(0, int(diff.total_seconds() / 60))
                
                embed = discord.Embed(title="OGUser Auto-Bumper", color=0x3498db)
                embed.add_field(name="Thread ID", value=config['tid'], inline=True)
                embed.add_field(name="Next Bump In", value=f"⏳ {minutes_left} mins", inline=True)
                embed.add_field(name="Last Result", value=config.get('last_status', 'Waiting...'), inline=False)
                embed.set_footer(text="Updates every 5 minutes • Database Active")
                
                await active_messages[user_id].edit(content=None, embed=embed)
            except:
                pass

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not global_timer_loop.is_running():
        global_timer_loop.start()
    print(f"Bumper Online as {bot.user}")

@bot.hybrid_command(name="setup", description="Link your OGUser info")
async def setup(ctx, thread_id: str, post_key: str, mybbuser: str, sid: str):
    await ctx.defer(ephemeral=True) # Fixes "Did not respond" error
    data = {
        "tid": thread_id,
        "post_key": post_key,
        "mybbuser": mybbuser,
        "sid": sid,
        "active": False,
        "next_bump": datetime.now().isoformat()
    }
    db.hset("user_configs", str(ctx.author.id), json.dumps(data))
    await ctx.send("✅ Info saved to Database! Type `/start` to begin.", ephemeral=True)

@bot.hybrid_command(name="start", description="Start your auto-bump loop")
async def start(ctx):
    await ctx.defer() # Fixes "Did not respond" error
    user_id = str(ctx.author.id)
    raw_data = db.hget("user_configs", user_id)
    
    if not raw_data:
        return await ctx.send("❌ Use `/setup` first!")
    
    config = json.loads(raw_data)
    config['active'] = True
    config['next_bump'] = datetime.now().isoformat()
    
    db.hset("user_configs", user_id, json.dumps(config))
    
    msg = await ctx.send("🚀 Starting Bumper... generating timer...")
    active_messages[user_id] = msg

@bot.hybrid_command(name="stop", description="Stop your auto-bump loop")
async def stop(ctx):
    await ctx.defer(ephemeral=True)
    user_id = str(ctx.author.id)
    raw_data = db.hget("user_configs", user_id)
    
    if not raw_data:
        return await ctx.send("❌ Setup not found.")

    config = json.loads(raw_data)
    config['active'] = False
    db.hset("user_configs", user_id, json.dumps(config))
    
    if user_id in active_messages:
        try:
            await active_messages[user_id].edit(content="🛑 **Bumper Stopped.** Use `/start` to resume.", embed=None)
            del active_messages[user_id]
        except: pass
            
    await ctx.send("🛑 **Auto-Bumper Deactivated.**", ephemeral=True)

bot.run(TOKEN)
