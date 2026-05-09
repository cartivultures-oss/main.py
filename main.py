import discord
from discord import app_commands
from discord.ext import tasks, commands
import os, asyncio, json, redis, re, random
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# FIXED IMPORT: Using the standard 'stealth' name
try:
    import playwright_stealth as stealth_module
except ImportError:
    stealth_module = None

# ENV VARIABLES
TOKEN = os.getenv('DISCORD_TOKEN')
PROXY_URL = os.getenv('PROXY_URL') 
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
db = redis.from_url(redis_url, decode_responses=True)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

def extract_tid(link):
    match = re.search(r"tid=(\d+)|Thread-.*?(\d+)", link)
    if match: return match.group(1) or match.group(2)
    return None

async def run_bump(user_id, slot, config):
    tid = extract_tid(config['link'])
    if not tid: return "❌ Invalid Link"
    
    launch_args = {
        'headless': True, 
        'args': [
            '--no-sandbox', 
            '--disable-setuid-sandbox', 
            '--disable-blink-features=AutomationControlled',
            '--window-size=1920,1080'
        ]
    }
    if PROXY_URL: launch_args['proxy'] = {'server': PROXY_URL}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_args)
        
        try:
            storage_path = 'auth.json' if os.path.exists('auth.json') else None
            
            context = await browser.new_context(
                storage_state=storage_path,
                viewport={'width': 1920, 'height': 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            # FIXED: Properly calling stealth to avoid 'module not callable'
            if stealth_module:
                await stealth_module.stealth(page)
            
            print(f"[{slot}] Navigating to thread {tid} using session state...")
            await page.goto(f"https://oguser.com/newreply.php?tid={tid}", wait_until="networkidle", timeout=60000)
            
            await asyncio.sleep(8) 
            
            textarea = await page.query_selector('textarea[name="message"]')
            
            if not textarea:
                await asyncio.sleep(5)
                textarea = await page.query_selector('textarea[name="message"]')

            if textarea:
                print(f"[{slot}] Success! Typing bump...")
                unique_tag = f"\n\n[size=xx-small]{os.urandom(3).hex()}[/size]"
                await textarea.fill(f"bump{unique_tag}")
                await asyncio.sleep(2)
                await page.click('input[type="submit"][name="submit"]')
                await asyncio.sleep(5)
                await browser.close()
                return "✅ Success"
            
            title = await page.title()
            print(f"[{slot}] Failed. Page Title: {title}")
            await browser.close()
            return f"❌ Blocked ({title[:15]})"
            
        except Exception as e:
            print(f"[{slot}] Error: {str(e)}")
            if 'browser' in locals(): await browser.close()
            return "❌ Connection Fail"

@bot.hybrid_command(name="setup")
async def setup(ctx, slot: int, thread_link: str):
    await ctx.defer(ephemeral=True)
    db.set(f"{ctx.author.id}:{slot}", json.dumps({
        "link": thread_link,
        "active": False, 
        "next_bump": datetime.now().isoformat()
    }))
    await ctx.send(f"✅ Slot {slot} configured!", ephemeral=True)

@bot.hybrid_command(name="start")
async def start(ctx, slot: int):
    await ctx.defer(ephemeral=True) 
    key = f"{ctx.author.id}:{slot}"
    raw = db.get(key)
    if not raw: return await ctx.send("❌ Run /setup first.", ephemeral=True)
    
    config = json.loads(raw)
    config['active'] = True
    await ctx.interaction.edit_original_response(content="🚀 **Bypassing security via Sticky Proxy...**")
    
    status = await run_bump(ctx.author.id, slot, config)
    config['last_status'] = status
    config['next_bump'] = (datetime.now() + timedelta(minutes=61)).isoformat()
    db.set(key, json.dumps(config))
    
    await ctx.interaction.edit_original_response(content=f"Slot {slot} Status: {status}")

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"Sync error: {e}")
    print(f"Logged in as {bot.user}. Session Mode: {'auth.json found' if os.path.exists('auth.json') else 'auth.json MISSING'}")

bot.run(TOKEN)
