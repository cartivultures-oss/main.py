import discord
from discord import app_commands
from discord.ext import tasks, commands
from curl_cffi import requests
import os
import random
import string
import json
import redis
from datetime import datetime, timedelta

TOKEN = os.getenv('DISCORD_TOKEN')
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
db = redis.from_url(redis_url, decode_responses=True)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Track active DM messages { "user_id:slot": message_object }
active_messages = {}

async def run_bump(user_id, slot, config):
    ref = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    url = "https://oguser.com/newreply.php?processed=1"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Referer": f"https://oguser.com/newreply.php?tid={config['tid']}",
        "Origin": "https://oguser.com",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    }

    payload = {
        "my_post_key": config['post_key'], "tid": config['tid'], "action": "do_newreply",
        "message": f"bump\n\n[size=xx-small]Ref: {ref}[/size]",
        "posthash": "", "quoted_ids": "", "lastpid": "", "from_page": "", "submit": "Post Reply"
    }

    cookies = {'mybbuser': config['mybbuser'], 'sid': config['sid']}
    
    try:
        with requests.Session() as s:
            # Establishing session handshake
            s.get(f"https://oguser.com/newreply.php?tid={config['tid']}", cookies=cookies, headers=headers, impersonate="chrome110")
            r = s.post(url, data=payload, headers=headers, impersonate="chrome110", allow_redirects=True, timeout=15)
        
        if r.status_code == 200 and (f"tid={config['tid']}" in r.url or "posted" in r.text):
            return "✅ Success"
        return "❌ Session Error"
    except:
        return "⚠️ Conn Error"

async def update_display(user_id, slot, config):
    key = f"{user_id}:{slot}"
    if key not in active_messages: return
    try:
        next_bump = datetime.fromisoformat(config['next_bump'])
        diff = next_bump - datetime.now()
        mins = max(0, int(diff.total_seconds() / 60))
        
        embed = discord.Embed(title=f"OGUser Bumper - Slot {slot}", color=0x3498db)
        embed.add_field(name="Thread ID", value=config['tid'], inline=True)
        embed.add_field(name="Next Bump", value=f"⏳ {mins}m", inline=True)
        embed.add_field(name="Last Status", value=config.get('last_status', 'Waiting...'), inline=False)
        embed.set_footer(text=f"Last Updated: {datetime.now().strftime('%H:%M:%S')}")
        
        await active_messages[key].edit(content=None, embed=embed)
    except: pass

@tasks.loop(minutes=5)
async def global_loop():
    keys = db.keys("*:*")
    for key in keys:
        raw = db.get(key)
        if not raw: continue
        config = json.loads(raw)
        if not config.get('active'): continue
        
        u_id, slot = key.split(":")
        if datetime.now() >= datetime.fromisoformat(config['next_bump']):
            status = await run_bump(u_id, slot, config)
            config['last_status'] = status
            config['next_bump'] = (datetime.now() + timedelta(minutes=61)).isoformat()
            db.set(key, json.dumps(config))
        
        await update_display(u_id, slot, config)

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not global_loop.is_running(): global_loop.start()
    print("Multi-Slot Bumper Active.")

@bot.hybrid_command(name="setup", description="Configure a specific slot (1-5)")
@app_commands.describe(slot="Slot number (1-5)")
async def setup(ctx, slot: int, thread_id: str, post_key: str, mybbuser: str, sid: str):
    if not (1 <= slot <= 5): return await ctx.send("❌ Choose slot 1-5.", ephemeral=True)
    await ctx.defer(ephemeral=True)
    data = {"tid": thread_id, "post_key": post_key, "mybbuser": mybbuser, "sid": sid, "active": False, "next_bump": datetime.now().isoformat()}
    db.set(f"{ctx.author.id}:{slot}", json.dumps(data))
    await ctx.send(f"✅ Slot {slot} saved! Use `/start slot:{slot}` to begin.", ephemeral=True)

@bot.hybrid_command(name="start", description="Start a specific slot")
async def start(ctx, slot: int):
    if not (1 <= slot <= 5): return await ctx.send("❌ Choose slot 1-5.", ephemeral=True)
    await ctx.defer(ephemeral=True)
    key = f"{ctx.author.id}:{slot}"
    raw = db.get(key)
    if not raw: return await ctx.send(f"❌ Slot {slot} is empty.", ephemeral=True)
    
    config = json.loads(raw)
    config['active'] = True
    
    try:
        msg = await ctx.author.send(f"🚀 **Activating Slot {slot}...**")
        active_messages[key] = msg
        await ctx.send(f"✅ Slot {slot} started! Check DMs.", ephemeral=True)
        
        # Immediate Bump
        status = await run_bump(ctx.author.id, slot, config)
        config['last_status'] = status
        config['next_bump'] = (datetime.now() + timedelta(minutes=61)).isoformat()
        db.set(key, json.dumps(config))
        await update_display(ctx.author.id, slot, config)
    except:
        await ctx.send("❌ Open your DMs!", ephemeral=True)

@bot.hybrid_command(name="stop", description="Stop a specific slot")
async def stop(ctx, slot: int):
    await ctx.defer(ephemeral=True)
    key = f"{ctx.author.id}:{slot}"
    raw = db.get(key)
    if raw:
        config = json.loads(raw)
        config['active'] = False
        db.set(key, json.dumps(config))
    if key in active_messages:
        try: await active_messages[key].edit(content=f"🛑 Slot {slot} Stopped.", embed=None)
        except: pass
        del active_messages[key]
    await ctx.send(f"🛑 Slot {slot} stopped.", ephemeral=True)

bot.run(TOKEN)
