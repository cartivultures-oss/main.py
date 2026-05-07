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

# Railway Redis Connection
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
db = redis.from_url(redis_url, decode_responses=True)

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

# Memory storage for active DM messages
active_messages = {}

async def run_bump(user_id, config):
    ref = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    url = "https://oguser.com/newreply.php?processed=1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Referer": f"https://oguser.com/newreply.php?tid={config['tid']}",
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
        with requests.Session() as s:
            r = s.post(url, data=payload, cookies=cookies, headers=headers, impersonate="chrome110", allow_redirects=True)
        
        if r.status_code == 200:
            if f"tid={config['tid']}" in r.url and "newreply" not in r.url:
                status_text = "✅ Success"
            elif "Your message has been posted" in r.text:
                status_text = "✅ Success"
            else:
                status_text = "❌ Error (Session Invalid)"
        else:
            status_text = f"❌ Failed ({r.status_code})"
    except:
        status_text = "⚠️ Connection Error"

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
                last_updated = datetime.now().strftime("%H:%M:%S")
                
                embed = discord.Embed(title="OGUser Auto-Bumper", color=0x2ecc71)
                embed.add_field(name="Thread ID", value=config['tid'], inline=True)
                embed.add_field(name="Next Bump In", value=f"⏳ {minutes_left} mins", inline=True)
                embed.add_field(name="Last Result", value=config.get('last_status', 'Waiting...'), inline=False)
                embed.set_footer(text=f"Last Updated: {last_updated} (Refreshes every 5m)")
                
                await active_messages[user_id].edit(content=None, embed=embed)
            except:
                pass

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not global_timer_loop.is_running():
        global_timer_loop.start()
    print(f"Bumper Online as {bot.user}")

@bot.hybrid_command(name="setup", description="Link your OGUser info (Private)")
async def setup(ctx, thread_id: str, post_key: str, mybbuser: str, sid: str):
    await ctx.defer(ephemeral=True)
    data = {
        "tid": thread_id,
        "post_key": post_key,
        "mybbuser": mybbuser,
        "sid": sid,
        "active": False,
        "next_bump": datetime.now().isoformat()
    }
    db.hset("user_configs", str(ctx.author.id), json.dumps(data))
    await ctx.send("✅ Info saved! Type `/start` to begin. Status will be sent to your DMs.", ephemeral=True)

@bot.hybrid_command(name="start", description="Start loop and send status to DMs")
async def start(ctx):
    await ctx.defer(ephemeral=True)
    user_id = str(ctx.author.id)
    raw_data = db.hget("user_configs", user_id)
    
    if not raw_data:
        return await ctx.send("❌ Use `/setup` first!", ephemeral=True)
    
    config = json.loads(raw_data)
    config['active'] = True
    config['next_bump'] = datetime.now().isoformat()
    db.hset("user_configs", user_id, json.dumps(config))
    
    try:
        msg = await ctx.author.send("🚀 **Bumper Activated!** Generating status card...")
        active_messages[user_id] = msg
        await ctx.send("✅ Bumper started! Check your DMs for the status card.", ephemeral=True)
    except discord.Forbidden:
        await ctx.send("❌ I can't DM you! Please open your DMs in server settings.", ephemeral=True)

@bot.hybrid_command(name="stop", description="Stop your loop (Private)")
async def stop(ctx):
    await ctx.defer(ephemeral=True)
    user_id = str(ctx.author.id)
    raw_data = db.hget("user_configs", user_id)
    
    if not raw_data: return await ctx.send("❌ Setup not found.", ephemeral=True)

    config = json.loads(raw_data)
    config['active'] = False
    db.hset("user_configs", user_id, json.dumps(config))
    
    if user_id in active_messages:
        try:
            await active_messages[user_id].edit(content="🛑 **Bumper Stopped.**", embed=None)
            del active_messages[user_id]
        except: pass
            
    await ctx.send("🛑 **Deactivated.**", ephemeral=True)

bot.run(TOKEN)
