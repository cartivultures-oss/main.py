import random
from playwright_stealth import stealth_async # You need this!

async def run_bump(user_id, slot, config):
    tid = extract_tid(config['link'])
    if not tid: return "❌ Invalid Link"
    
    launch_args = {
        'headless': True, 
        'args': [
            '--no-sandbox', 
            '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled', # Standard bypass
            '--use-fake-ui-for-media-stream',
            '--window-size=1920,1080'
        ]
    }
    
    if PROXY_URL:
        launch_args['proxy'] = {'server': PROXY_URL}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_args)
        # Create a realistic "Human" context
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False,
            locale="en-US",
            timezone_id="America/New_York"
        )
        
        # Apply the Stealth Plugin
        page = await context.new_page()
        await stealth_async(page) 
        
        await context.add_cookies([
            {'name': 'mybbuser', 'value': config['mybbuser'], 'domain': 'oguser.com', 'path': '/'},
            {'name': 'sid', 'value': config['sid'], 'domain': 'oguser.com', 'path': '/'}
        ])
        
        try:
            # Step 1: Visit the homepage first to look like a normal session
            await page.goto("https://oguser.com/index.php", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(4, 7)) 
            
            # Step 2: Navigate to the reply page
            await page.goto(f"https://oguser.com/newreply.php?tid={tid}", wait_until="load", timeout=90000)
            
            # Step 3: Wait for Cloudflare "Turnstile" or the Textbox
            # We use a long wait here because residential proxies are slower
            await asyncio.sleep(10) 
            
            textarea = await page.wait_for_selector('textarea[name="message"]', timeout=30000)
            if textarea:
                # Type the message like a human
                bump_msg = f"bump\n\n[size=xx-small]{os.urandom(3).hex()}[/size]"
                for char in bump_msg:
                    await page.keyboard.type(char)
                    await asyncio.sleep(random.uniform(0.05, 0.15))
                
                await asyncio.sleep(random.uniform(1, 3))
                await page.click('input[type="submit"][name="submit"]')
                await asyncio.sleep(6) # Wait for post to register
                await browser.close()
                return "✅ Success"
            
            await browser.close()
            return "❌ Blocked (Captcha?)"
            
        except Exception as e:
            print(f"Bumper Error: {e}")
            if 'browser' in locals(): await browser.close()
            return "❌ Connection Fail"
