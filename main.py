import discord
from discord import app_commands
from discord.ext import tasks, commands
import os, asyncio, json, redis, re, random
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# --- CRASH-PROOF STEALTH IMPORT ---
try:
    from playwright_stealth import stealth_async as stealth_run
except ImportError:
    try:
        from playwright_stealth import stealth as stealth_run
    except ImportError:
        stealth_run = None
        print("⚠️ Stealth library not loaded, but bot will still boot!")

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
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        if stealth_run:
            await stealth_run(page) 
        
        await context.add_cookies([
            {'name': 'mybbuser', 'value': config['mybbuser'], 'domain': 'oguser.com', 'path': '/'},
            {'name': 'sid', 'value': config['sid'], 'domain': 'oguser.com', 'path': '/'}
        ])
        
        try:
            print(f"[{slot}] Navigating directly to thread...")
            await page.goto(f"https://oguser.com/newreply.php?tid={tid}", wait_until="commit", timeout=60000)
            
            # Giving Cloudflare 15 seconds to resolve over the sticky proxy
            await asyncio.sleep(15) 
            
            textarea = await page.wait_for_selector('textarea[name="message"]', timeout=30000)
            if textarea:
                print(f"[{slot}] Box found! Posting...")
                await textarea.fill(f"bump\n\n[size=xx-small]{os.urandom(3).hex()}[/size]")
                await asyncio.sleep(2)
                await page.click('input[type="submit"][name="submit"]')
                await asyncio.sleep(5)
                await browser.close()
                return "✅ Success"
            
            await browser.close()
            return "❌ Security Wall (Turnstile)"
        except Exception as e:
            print(f"[{slot}] Error: {e}")
            if 'browser' in locals(): await browser.close()
            return "❌ Connection Fail"

@bot.hybrid_command(name="setup")
async def setup(ctx, slot: int, thread_link: str, mybbuser: str, sid: str):
    await ctx.defer(ephemeral=True)
    db.set(f"{ctx.author.id}:{slot}", json.dumps({
        "link": thread_link, "mybbuser": mybbuser, "sid": sid,
        "active": False, "next_bump": datetime.now().isoformat()
    }))
    await ctx.send(f"✅ Slot {slot} saved!", ephemeral=True)

@bot.hybrid_command(name="start")
async def start(ctx, slot: int):
    await ctx.defer(ephemeral=True) 
    
    key = f"{ctx.author.id}:{slot}"
    raw = db.get(key)
    if not raw: return await ctx.send("❌ Run /setup first.", ephemeral=True)
    
    config = json.loads(raw)
    config['active'] = True
    await ctx.interaction.edit_original_response(content="🚀 **Bypassing security... wait ~30s**")
    
    status = await run_bump(ctx.author.id, slot, config)
    config['last_status'] = status
    config['next_bump'] = (datetime.now() + timedelta(minutes=61)).isoformat()
    db.set(key, json.dumps(config))
    
    await ctx.interaction.edit_original_response(content=f"Slot {slot} Status: {status}")

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}. Proxy Active: {bool(PROXY_URL)}")

bot.run(TOKEN)
