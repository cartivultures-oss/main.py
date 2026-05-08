async def run_bump(user_id, slot, config):
    tid = extract_tid(config['link'])
    if not tid: return "❌ Invalid Link"
    
    launch_args = {
        'headless': True, 
        'args': [
            '--no-sandbox', 
            '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--window-size=1920,1080'
        ]
    }
    if PROXY_URL: launch_args['proxy'] = {'server': PROXY_URL}

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch_args)
        # Use a more generic, high-reputation User Agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await stealth(page)
        
        await context.add_cookies([
            {'name': 'mybbuser', 'value': config['mybbuser'], 'domain': 'oguser.com', 'path': '/'},
            {'name': 'sid', 'value': config['sid'], 'domain': 'oguser.com', 'path': '/'}
        ])
        
        try:
            # Shift wait_until to 'commit' so we don't wait for slow ads/images to load over proxy
            print(f"[{slot}] Navigating to reply page...")
            await page.goto(f"https://oguser.com/newreply.php?tid={tid}", wait_until="commit", timeout=60000)
            
            # Persistent Retry Loop: Check for the box every 2 seconds for 40 seconds total
            for i in range(20):
                print(f"[{slot}] Check {i+1}/20 for message box...")
                textarea = await page.query_selector('textarea[name="message"]')
                if textarea:
                    await asyncio.sleep(random.uniform(1, 3))
                    await textarea.fill(f"bump\n\n[size=xx-small]{os.urandom(3).hex()}[/size]")
                    await page.click('input[type="submit"][name="submit"]')
                    await asyncio.sleep(5)
                    await browser.close()
                    return "✅ Success"
                
                # If we see a Cloudflare checkbox, we might be stuck
                if await page.query_selector('iframe[title*="Cloudflare"]'):
                    print(f"[{slot}] Cloudflare detected, waiting...")
                
                await asyncio.sleep(2)

            await browser.close()
            return "❌ Timeout (Security Wall)"
        except Exception as e:
            print(f"Error: {e}")
            if 'browser' in locals(): await browser.close()
            return "❌ Connection Fail"
