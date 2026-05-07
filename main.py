import discord
from discord.ext import tasks, commands
from curl_cffi import requests
import os
import random
import string

# Railway will pull these from your "Variables" tab
TOKEN = os.getenv('DISCORD_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
THREAD_ID = "1286856"
POST_KEY = "272e30b3f043f0bb7584364da77dafbe"

COOKIES = {
    'mybbuser': os.getenv('MYBBUSER_COOKIE'),
    'sid': os.getenv('SID_COOKIE')
}

bot = commands.Bot(command_prefix="/", intents=discord.Intents.all())

@tasks.loop(minutes=61)
async def bump_loop():
    ref = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    url = f"https://oguser.com/newreply.php?tid={THREAD_ID}&processed=1"
    payload = {
        "my_post_key": POST_KEY, "tid": THREAD_ID, "action": "do_newreply",
        "message": f"bump\n\n[size=xx-small]Ref: {ref}[/size]", "submit": "Post Reply"
    }
    # TLS Fingerprinting to beat Cloudflare protection
    r = requests.post(url, data=payload, cookies=COOKIES, impersonate="chrome110")
    
    status = "✅ **Cloud Bump Success**" if r.status_code == 200 else f"❌ **Failed** ({r.status_code})"
    requests.post(WEBHOOK_URL, json={"content": f"{status} | Ref: {ref}"})

@bot.event
async def on_ready():
    requests.post(WEBHOOK_URL, json={"content": "🟢 **Cloud Bumper Online** - The browser can now be closed."})

@bot.command()
async def start(ctx):
    if not bump_loop.is_running():
        bump_loop.start()
        await ctx.send("🚀 Bumper started!")

bot.run(TOKEN)
