import discord
from discord import app_commands
from discord.ext import tasks, commands
import os
import asyncio
import json
import redis
import re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

TOKEN = os.getenv('DISCORD_TOKEN')
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
db = redis.from_url(redis_url, decode_responses=True)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
active_messages = {}

# Helper to pull the ID out of a link
def extract_tid(link):
    match = re.search(r"tid=(\d+)|Thread-.*?(\d+)", link)
    if match:
        return match.group(1) or match.group(2)
    return None

async def run_bump(user_id, slot, config):
    tid = extract_tid(config['link'])
    if not tid: return "❌ Invalid Link"

    async with async_playwright() as p:
        # Mimics a real Windows Chrome browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36")
        
        await context.add_cookies([
            {'name': 'mybbuser', 'value': config['mybbuser'], 'domain': 'oguser.com', 'path': '/'},
            {'name': 'sid', 'value': config['sid'], 'domain': 'oguser.com', 'path': '/'}
        ])
        
        page = await context.new_page()
        try:
            # Navigate directly to the thread
            await page.goto(f"https://oguser.com/showthread.php?tid={tid}", timeout=60000)
            
            # Look for the reply box (TextArea)
            await page.wait_for_selector('textarea[name="message"]', timeout=15000)
            
            # Type the bump message
            ref = os.urandom(4).hex()
            await page.fill('textarea[name="message"]', f"bump\n\n[size=xx-small]Ref: {ref}[/size]")
            
            # Click the post button
            await page.click('input[type="submit"][name="submit"]')
            
            # Wait for redirect/reload
            await page.wait_for_load_state("networkidle")
            
            # Confirm success
            if "posted" in page.url or tid in page.url:
                print(f"[LOG] Slot {slot} Success for {user_id}")
                await browser.close()
                return "✅ Success"
            
            await browser.close()
            return "❌ Forum Rejected"
        except Exception as e:
            print(f"[ERROR] Slot {slot} Browser Error: {str(e)}")
            await browser.close()
            return "❌ Session Error"

async def update_display(user_id, slot, config):
    key = f"{user_id}:{slot}"
    if key not in active_messages: return
    try:
        next_bump = datetime.fromisoformat(config['next_bump'])
        diff = next_bump - datetime.now()
        mins = max(0, int(diff.total_seconds() / 60))
        
        embed = discord.Embed(title=f"OGUser Bumper - Slot {slot}", color=0x2ecc71 if "✅" in config.get('last_status', '') else 0xe74c3c)
        embed.add_field(name="Thread Link", value=f"[Click Here]({config['link']})", inline=True)
        embed.add_field(name="Next Bump In", value=f"⏳ {mins}m", inline=True)
        embed.add_field(name="Last Status", value=config.get('last_status', 'Initializing...'), inline=False)
        embed.set_footer(text=f"Last Sync: {datetime.now().strftime('%H:%M:%S')}")
        
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
    print("Link-Based Bumper Online.")

@bot.hybrid_command(name="setup")
async def setup(ctx, slot: int, thread_link: str, post_key: str, mybbuser: str, sid: str):
    if not (1 <= slot <= 5): return await ctx.send("❌ Use slot 1-5.", ephemeral=True)
    await ctx.defer(ephemeral=True)
    data = {"link": thread_link, "post_key": post_key, "mybbuser": mybbuser, "sid": sid, "active": False, "next_bump": datetime.now().isoformat()}
    db.set(f"{ctx.author.id}:{slot}", json.dumps(data))
    await ctx.send(f"✅ Slot {slot} saved with link!", ephemeral=True)

@bot.hybrid_command(name="start")
async def start(ctx, slot: int):
    if not (1 <= slot <= 5): return await ctx.send("❌ Use slot 1-5.", ephemeral=True)
    await ctx.defer(ephemeral=True)
    key = f"{ctx.author.id}:{slot}"
    raw = db.get(key)
    if not raw: return await ctx.send(f"❌ Slot {slot} empty.", ephemeral=True)
    
    config = json.loads(raw)
    config['active'] = True
    
    try:
        msg = await ctx.author.send(f"🛰️ **Slot {slot} browser launching...**")
        active_messages[key] = msg
        await ctx.send(f"✅ Started! Check DMs for Slot {slot}.", ephemeral=True)
        
        status = await run_bump(ctx.author.id, slot, config)
        config['last_status'] = status
        config['next_bump'] = (datetime.now() + timedelta(minutes=61)).isoformat()
        db.set(key, json.dumps(config))
        await update_display(ctx.author.id, slot, config)
    except:
        await ctx.send("❌ Check your DM settings!", ephemeral=True)

@bot.hybrid_command(name="stop")
async def stop(ctx, slot: int):
    await ctx.defer(ephemeral=True)
    key = f"{ctx.author.id}:{slot}"
    raw = db.get(key)
    if raw:
        config = json.loads(raw)
        config['active'] = False
        db.set(key, json.dumps(config))
    if key in active_messages:
        try: await active_messages[key].delete()
        except: pass
        del active_messages[key]
    await ctx.send(f"🛑 Slot {slot} stopped.", ephemeral=True)

bot.run(TOKEN)
