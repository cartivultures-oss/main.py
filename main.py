import discord
from discord import app_commands
from discord.ext import tasks, commands
import os, asyncio, json, redis, re
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
    
    # Check if a proxy is configured (format: http://user:pass@host:port)
    proxy = config.get('proxy')
    launch_args = {'headless': True, 'args': ['--no-sandbox', '--disable-setuid-sandbox']}
    if proxy:
        launch_args['proxy'] = {'server': proxy}

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(**launch_args)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            
            # Inject cookies to bypass the login wall
            await context.add_cookies([
                {'name': 'mybbuser', 'value': config['mybbuser'], 'domain': 'oguser.com', 'path': '/'},
                {'name': 'sid', 'value': config['sid'], 'domain': 'oguser.com', 'path': '/'}
            ])
            
            page = await context.new_page()
            
            # Go directly to the reply page
            # Using 'commit' wait to bypass initial Cloudflare handshakes faster
            response = await page.goto(f"https://oguser.com/newreply.php?tid={tid}", wait_until="commit", timeout=60000)
            
            if response.status == 403:
                await browser.close()
                return "❌ IP Banned (Use Proxy)"

            # Give it a moment to load the actual form
            await asyncio.sleep(5)
            
            if "Verify you are human" in await page.title() or await page.get_by_text("Login").is_visible():
                await browser.close()
                return "❌ Session Expired"

            textarea = await page.wait_for_selector('textarea[name="message"]', timeout=15000)
            if textarea:
                await textarea.fill(f"bump\n\n[size=xx-small]{os.urandom(3).hex()}[/size]")
                await page.click('input[type="submit"][name="submit"]')
                await asyncio.sleep(5)
                await browser.close()
                return "✅ Success"
            
            await browser.close()
            return "❌ No Reply Box"
            
        except Exception as e:
            if 'browser' in locals(): await browser.close()
            return "❌ Connection Fail"

async def update_status_msg(interaction, slot, config):
    try:
        next_bump = datetime.fromisoformat(config['next_bump'])
        diff = next_bump - datetime.now()
        mins = max(0, int(diff.total_seconds() / 60))
        status_color = 0x2ecc71 if "✅" in config.get('last_status', '') else 0xe74c3c
        embed = discord.Embed(title=f"OGU Bumper - Slot {slot}", color=status_color)
        embed.add_field(name="Next Bump", value=f"⏳ {mins}m", inline=True)
        embed.add_field(name="Last Status", value=config.get('last_status', 'Pending...'), inline=False)
        embed.set_footer(text=f"Sync: {datetime.now().strftime('%H:%M:%S')}")
        await interaction.edit_original_response(content=None, embed=embed)
    except: pass

@tasks.loop(minutes=5)
async def global_loop():
    for key in db.keys("*:*"):
        raw = db.get(key)
        if not raw: continue
        config = json.loads(raw)
        if not config.get('active'): continue
        if datetime.now() >= datetime.fromisoformat(config['next_bump']):
            status = await run_bump(key.split(":")[0], key.split(":")[1], config)
            config['last_status'] = status
            config['next_bump'] = (datetime.now() + timedelta(minutes=61)).isoformat()
            db.set(key, json.dumps(config))
        if key in active_interactions:
            await update_status_msg(active_interactions[key], key.split(":")[1], config)

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not global_loop.is_running(): global_loop.start()
    print("Proxy Bumper Engaged.")

@bot.hybrid_command(name="setup")
async def setup(ctx, slot: int, thread_link: str, mybbuser: str, sid: str, proxy: str = None):
    await ctx.defer(ephemeral=True)
    db.set(f"{ctx.author.id}:{slot}", json.dumps({
        "link": thread_link, "mybbuser": mybbuser, "sid": sid, "proxy": proxy,
        "active": False, "next_bump": datetime.now().isoformat()
    }))
    await ctx.send(f"✅ Slot {slot} configured.", ephemeral=True)

@bot.hybrid_command(name="start")
async def start(ctx, slot: int):
    await ctx.defer(ephemeral=True) # Essential to stop "Application did not respond"
    key = f"{ctx.author.id}:{slot}"
    raw = db.get(key)
    if not raw: return await ctx.send("❌ Setup first.", ephemeral=True)
    config = json.loads(raw)
    config['active'] = True
    active_interactions[key] = ctx.interaction
    await ctx.interaction.edit_original_response(content="🚀 **Initiating Stealth Bump...**")
    status = await run_bump(ctx.author.id, slot, config)
    config['last_status'] = status
    config['next_bump'] = (datetime.now() + timedelta(minutes=61)).isoformat()
    db.set(key, json.dumps(config))
    await update_status_msg(ctx.interaction, slot, config)

bot.run(TOKEN)
