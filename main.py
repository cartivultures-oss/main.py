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
active_interactions = {}

def extract_tid(link):
    match = re.search(r"tid=(\d+)|Thread-.*?(\d+)", link)
    if match: return match.group(1) or match.group(2)
    return None

async def run_bump(user_id, slot, config):
    tid = extract_tid(config['link'])
    if not tid: return "❌ Invalid Link"
    
    async with async_playwright() as p:
        # Launch with stealth arguments
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        )
        
        await context.add_cookies([
            {'name': 'mybbuser', 'value': config['mybbuser'], 'domain': 'oguser.com', 'path': '/'},
            {'name': 'sid', 'value': config['sid'], 'domain': 'oguser.com', 'path': '/'}
        ])
        
        page = await context.new_page()
        try:
            # Go to thread and wait for content to stabilize
            await page.goto(f"https://oguser.com/showthread.php?tid={tid}", wait_until="networkidle", timeout=60000)
            
            # Wait for the reply box to be visible
            textarea = await page.wait_for_selector('textarea[name="message"]', timeout=20000)
            
            if textarea:
                await textarea.click()
                # Human-like typing speed
                await page.keyboard.type(f"bump\n\n[size=xx-small]Ref: {os.urandom(4).hex()}[/size]", delay=100)
                
                # Click and wait for the post to register
                await page.click('input[type="submit"][name="submit"]')
                await asyncio.sleep(5) 
                
                success = "posted" in page.url or tid in page.url or await page.get_by_text("Post Reply").is_hidden()
                await browser.close()
                return "✅ Success" if success else "❌ Post Failed"
            
            await browser.close()
            return "❌ Box Not Found"
        except Exception as e:
            await browser.close()
            if "Timeout" in str(e): return "❌ Login/CF Block"
            return f"❌ {str(e)[:15]}"

async def update_status_msg(interaction, slot, config):
    try:
        next_bump = datetime.fromisoformat(config['next_bump'])
        diff = next_bump - datetime.now()
        mins = max(0, int(diff.total_seconds() / 60))
        
        status_color = 0x2ecc71 if "✅" in config.get('last_status', '') else 0x3498db
        embed = discord.Embed(title=f"OGUser Bumper - Slot {slot}", color=status_color)
        embed.add_field(name="Thread Link", value=f"[View Thread]({config['link']})", inline=True)
        embed.add_field(name="Next Bump", value=f"⏳ {mins}m", inline=True)
        embed.add_field(name="Last Status", value=config.get('last_status', 'Pending...'), inline=False)
        embed.set_footer(text=f"Last Sync: {datetime.now().strftime('%H:%M:%S')}")
        
        await interaction.edit_original_response(content=None, embed=embed)
    except: pass

@tasks.loop(minutes=5)
async def global_loop():
    for key in db.keys("*:*"):
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
        
        if key in active_interactions:
            await update_status_msg(active_interactions[key], slot, config)

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not global_loop.is_running(): global_loop.start()
    print("Final Version Bumper Ready.")

@bot.hybrid_command(name="setup")
async def setup(ctx, slot: int, thread_link: str, post_key: str, mybbuser: str, sid: str):
    await ctx.defer(ephemeral=True)
    data = {"link": thread_link, "post_key": post_key, "mybbuser": mybbuser, "sid": sid, "active": False, "next_bump": datetime.now().isoformat()}
    db.set(f"{ctx.author.id}:{slot}", json.dumps(data))
    await ctx.send(f"✅ Slot {slot} updated.", ephemeral=True)

@bot.hybrid_command(name="start")
async def start(ctx, slot: int):
    await ctx.defer(ephemeral=True)
    key = f"{ctx.author.id}:{slot}"
    raw = db.get(key)
    if not raw: return await ctx.send("❌ Setup this slot first.", ephemeral=True)
    
    config = json.loads(raw)
    config['active'] = True
    active_interactions[key] = ctx.interaction
    
    await ctx.send(f"🚀 **Starting Ghost Browser for Slot {slot}...**", ephemeral=True)
    status = await run_bump(ctx.author.id, slot, config)
    config['last_status'] = status
    config['next_bump'] = (datetime.now() + timedelta(minutes=61)).isoformat()
    db.set(key, json.dumps(config))
    await update_status_msg(ctx.interaction, slot, config)

bot.run(TOKEN)
