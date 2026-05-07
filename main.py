async def run_bump(user_id, config):
    ref = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # We use the explicit 'newreply' URL for MyBB
    url = f"https://oguser.com/newreply.php?tid={config['tid']}&processed=1"
    
    payload = {
        "my_post_key": config['post_key'],
        "tid": config['tid'],
        "action": "do_newreply",
        "message": f"bump\n\n[size=xx-small]Ref: {ref}[/size]",
        "posthash": "",
        "quoted_ids": "",
        "lastpid": "",
        "from_page": "",
        "submit": "Post Reply"
    }

    cookies = {'mybbuser': config['mybbuser'], 'sid': config['sid']}
    
    # Adding a Header makes the bot look like a real Chrome browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Referer": f"https://oguser.com/showthread.php?tid={config['tid']}"
    }
    
    try:
        r = requests.post(url, data=payload, cookies=cookies, headers=headers, impersonate="chrome110")
        
        # If we get a 200, we check if the page actually contains a success message
        if r.status_code == 200:
            if "Your message has been posted" in r.text or "redirect" in r.text:
                status_text = "✅ Success"
            else:
                status_text = "❌ Error (Check Cookies/Post Key)"
        else:
            status_text = f"❌ Failed ({r.status_code})"
    except Exception as e:
        status_text = "⚠️ Connection Error"

    if WEBHOOK_URL:
        requests.post(WEBHOOK_URL, json={"content": f"User <@{user_id}>: {status_text} | Ref: {ref}"})
    return status_text
