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
    # Using the Port 10000 Sticky Proxy from your dashboard
    if PROXY_URL: launch_args['proxy'] = {'server': PROXY_URL}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_args)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await stealth(page) # Fixed import usage
        
        await context.add_cookies([
            {'name': 'mybbuser', 'value': config['mybbuser'], 'domain': 'oguser.com', 'path': '/'},
            {'name': 'sid', 'value': config['sid'], 'domain': 'oguser.com', 'path': '/'}
        ])
        
        try:
            # Step 1: Warm up the session on the home page
            print(f"[{slot}] Step 1: Warming up session on Index...")
            await page.goto("https://oguser.com/index.php", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(3, 6))
            
            # Step 2: Go to the reply page
            print(f"[{slot}] Step 2: Navigating to Thread {tid}...")
            # We use 'commit' here because residential proxies are slow
            await page.goto(f"https://oguser.com/newreply.php?tid={tid}", wait_until="commit", timeout=60000)
            
            # Step 3: Aggressive search for the text box
            print(f"[{slot}] Step 3: Hunting for the message box...")
            textarea = None
            for attempt in range(15):
                textarea = await page.query_selector('textarea[name="message"]')
                if textarea: break
                
                # Check for common Cloudflare block text
                content = await page.content()
                if "Verify you are human" in content or "Cloudflare" in content:
                    print(f"[{slot}] Blocked by Cloudflare Turnstile.")
                
                await asyncio.sleep(3)
                print(f"[{slot}] Retrying box search ({attempt+1}/15)...")

            if textarea:
                print(f"[{slot}] Box found! Typing message...")
                await textarea.fill(f"bump\n\n[size=xx-small]{os.urandom(3).hex()}[/size]")
                await asyncio.sleep(random.uniform(1, 3))
                await page.click('input[type="submit"][name="submit"]')
                await asyncio.sleep(5)
                await browser.close()
                return "✅ Success"
            
            await browser.close()
            return "❌ Security Wall (Timeout)"
            
        except Exception as e:
            print(f"[{slot}] CRITICAL ERROR: {str(e)}")
            if 'browser' in locals(): await browser.close()
            return "❌ Connection Fail"
