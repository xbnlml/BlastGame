---
name: chinese-platforms-gateway
description: Set up, configure, and troubleshoot Chinese messaging platforms (WeChat/Weixin, DingTalk, Feishu/Lark, QQ Bot, Yuanbao) on the Hermes messaging gateway
version: 1.0.0
author: Hermes Agent
tags: [hermes, gateway, wechat, weixin, dingtalk, feishu, qq, yuanbao, chinese-platforms]
---

# Chinese Platforms Gateway Setup

Set up Chinese messaging platforms (微信/Weixin, DingTalk, Feishu/Lark, QQ Bot, Yuanbao) on the Hermes messaging gateway. These platforms commonly use QR-code-based auth and Tencent iLink APIs, distinct from Western platforms like Telegram/Discord.

## Common Patterns

Chinese platform adapters share these characteristics:
- **QR-code login** — most require scanning a QR code with a mobile app
- **Long-polling transport** — no public webhook endpoint needed
- **Interactive wizard** — `hermes gateway setup` runs an interactive TUI

## Prerequisites

All Chinese platform adapters need:

```bash
pip install aiohttp cryptography
# Optional: terminal QR code rendering
pip install qrcode[pil]
```

## Automated Wizard Interaction

The `hermes gateway setup` wizard is a TUI that expects interactive input. For automation, pipe answers through stdin:

```bash
# Answer Y to start gateway, then select platform by number:
#   3 = Weixin/WeChat, 6 = Yuanbao, 7 = DingTalk, 10 = Feishu, 5 = QQ Bot
printf 'Y\n3\n' | hermes gateway setup
```

To extract a QR URL from the wizard output:

```bash
printf 'Y\n3\n' | timeout 30 hermes gateway setup 2>&1 | grep -oP 'https://liteapp\.weixin\.qq\.com/q/[^\s]+' | head -1
```

## QR Code Image Generation

When the wizard displays a QR code URL but the terminal ASCII rendering is insufficient, generate a scannable image:

```python
import qrcode
url = 'https://liteapp.weixin.qq.com/q/...'
img = qrcode.make(url)
img.save('C:/Users/Administrator/wechat_qr.png')
```

**Critical workflow — race condition with QR expiry:** The QR code is only valid for ~30s. Do NOT generate the image first and then run the wizard. Instead:

1. Run the wizard in **background mode** with full piped answers so it's waiting at the QR display:
   ```bash
   printf 'Y\n3\ny\nY\n1\n1\n' | timeout 180 hermes gateway setup &
   ```
2. **Immediately** extract the QR URL from process output via `process(action='log')` or grepping the log file.
3. Generate the image from that URL in the same response turn.
4. Tell the user the **direct file path** (e.g. `C:\Users\Administrator\wechat_qr.png`) — on Hermes desktop app, `MEDIA:` links may not render inline.

Then tell the user to:
1. Open the image file on their computer (provide the absolute path)
2. Scan with the relevant mobile app
3. Confirm login on their phone

The wizard auto-refreshes expired QR codes (3 retries, ~30s each). If all 3 expire, re-run the wizard.

## Platforms

### Weixin / WeChat (微信)

Uses Tencent's **iLink Bot API** for personal WeChat accounts. Key points:

- Connects to an **iLink bot identity** (e.g. `a5ace6fd482e@im.bot`), **not** a scriptable personal account
- **Cannot** be invited into ordinary WeChat groups (iLink limitation)
- Group events are typically NOT delivered for iLink bot accounts
- Most deployments get **DMs only** working reliably
- Default iLink app_id resolves to server-side name — visible as "Open Claw's AI bot" on WeChat. Workaround: let the user change the contact nickname on their phone.

**Full automated setup (incl. post-scan DM policy & group chat):**

```bash
# FRESH setup (Weixin not previously configured):
# Y(start gateway) → 3(WeChat) → Y(start QR) → 1(DM pairing) → 1(disable groups)
printf 'Y\n3\nY\n1\n1\n' | hermes gateway setup

# RECONFIGURE (Weixin already configured — extra "Reconfigure? [y/N]" prompt appears):
# Y(start gateway) → 3(WeChat) → y(yes reconfigure) → Y(start QR) → 1(DM pairing) → 1(disable groups)
printf 'Y\n3\ny\nY\n1\n1\n' | hermes gateway setup
```

**IMPORTANT:** The difference between fresh and reconfigure is the intermediate "Reconfigure Weixin? [y/N]:" question that appears ONLY when a prior config exists. Using the wrong pipe (e.g. your `3\ny` sequence in a fresh setup) causes the `y` to be consumed by a different prompt, offsetting all subsequent answers.

The piped examples above include an extra `1` for **group chat policy** ("Disable group chats" = option 1), which appears after DM pairing. After group chat, the wizard also asks whether to use the user's WeChat ID as the **home channel** — defaults to `Y` (yes), so no extra input is needed for that. The total piped answer count for a full reconfigure is **6**; for fresh setup **5**.

DM policy options (selected with `1`-`4` after QR scan):
- `1` = **Pairing approval** (recommended — users must request access)
- `2` = **Open** (allow all DMs)
- `3` = **Allowlist** (only listed user IDs)
- `4` = **Disabled** (block all DMs)

After QR scan, credentials are auto-saved to `~/.hermes/weixin/accounts/` AND appended to `~/.hermes/.env` (WEIXIN_ACCOUNT_ID, WEIXIN_TOKEN, WEIXIN_BASE_URL, WEIXIN_CDN_BASE_URL). The .env write happens even if the wizard exits before the DM policy prompt is answered — check .env first if a piped setup fails mid-way.

**Piped input timing:** The wizard's TUI reads answers sequentially from stdin. When the QR code is shown, the wizard pauses for the user's phone scan — remaining piped answers stay buffered and are consumed afterward for the DM policy prompt. Use `pty=true` + background process if the auto-refresh loop outruns the user's scan (the wizard retries QR codes 3 times).

**Environment variables (.env):**
```bash
WEIXIN_ACCOUNT_ID=your-account-id     # Required (auto-saved from QR login)
WEIXIN_TOKEN=your-bot-token           # Optional override
WEIXIN_DM_POLICY=open                 # open | allowlist | disabled | pairing
WEIXIN_ALLOWED_USERS=user1,user2      # comma-separated user IDs
WEIXIN_GROUP_POLICY=disabled          # disabled | open | allowlist
WEIXIN_BASE_URL=https://ilinkai.weixin.qq.com
WEIXIN_CDN_BASE_URL=https://novac2c.cdn.weixin.qq.com/c2c
```

**Config (config.yaml under platforms.weixin.extra):**
- `dm_policy`: Access control for DMs
- `group_policy`: Group chat access (default: disabled — intentional)
- `split_multiline_messages`: Split long messages (default: false)
- `text_batch_delay_seconds`: Delay between message chunks (default: 3.0)

### Maintenance — iLink Session Expiry

WeChat iLink bot sessions **expire periodically** (hours to days depending on iLink server state). This is the #1 operational failure mode. Symptom pattern:

```
[Weixin] Session expired; pausing for 10 minutes           ← gateway log
iLink sendmessage error: errcode=-14 errmsg=session timeout ← hermes send / outbound
```

**Critical diagnostic trap:** `hermes gateway status` and `gateway_state.json` report `"state":"connected"` even when the session is expired. The gateway adapter connects at the account level, but the iLink session token itself is dead. Always verify session health by attempting a send or checking the log for `Session expired`.

**Context token file:**
Each WeChat DM contact gets a token stored in:
```
~/.hermes/weixin/accounts/<account_id>.context-tokens.json
```
This is a local client-side session cache — deleting it does NOT fix expiry because the iLink server considers the session invalid. Only a fresh QR login creates a new server-side session.

**Recovery (requires human with phone):**

```bash
# Stop the gateway first
hermes gateway stop

# Re-run the setup wizard with reconfigure answers
# Y(gateway) → 3(WeChat) → y(reconfigure) → Y(QR) → 1(DM pairing)
printf 'Y\n3\ny\nY\n1\n' | hermes gateway setup
```

The wizard generates a new QR code. The user must scan it with WeChat on their phone to establish a fresh iLink session. Credentials are auto-updated.

**Post-recovery gateway restart:** After the wizard updates credentials in `.env`, the running gateway still holds the old session token. Always force a restart to pick up fresh credentials:

```bash
hermes gateway stop && sleep 2 && hermes gateway start
```

The new gateway log should show `Connected account=<new_id>` (not `Session expired`) within 5 seconds. Verify with `tail -5 ~/.hermes/logs/gateway.log`.

**Automated health-check** (for cron jobs / monitoring):
```bash
# Quick check: does the gateway log show a recent session expiry?
grep -c "Session expired" ~/.hermes/logs/gateway.log | tail -3

# Direct send test (non-blocking):
hermes send --to weixin "🟢 看门狗心跳: iLink 在线" 2>&1 || \
  echo "WARNING: WeChat session may be expired"
```

### Account-Level Credential Refresh

The iLink bot identity (`<id>.context-tokens.json`) and account credentials (`~/.hermes/.env`) persist across restarts. If the .env credentials become stale:

```bash
# Remove stale credentials and context tokens
rm -rf ~/.hermes/weixin/accounts/
# Then re-run setup to generate fresh credentials
```

### DingTalk (钉钉)

See the official docs at https://hermes-agent.nousresearch.com/docs/user-guide/messaging/dingtalk

### Feishu / Lark (飞书)

See the official docs at https://hermes-agent.nousresearch.com/docs/user-guide/messaging/feishu

### QQ Bot

See the official docs at https://hermes-agent.nousresearch.com/docs/user-guide/messaging/qq

### Yuanbao (元宝)

See the official docs at https://hermes-agent.nousresearch.com/docs/user-guide/messaging/yuanbao

**Group interaction reference** at `references/yuanbao-group-interaction.md` — covers @mentioning users, querying group info and members, and sending DMs through the Yuanbao platform. Key workflow:

- To @mention a user, call `yb_query_group_members(name="<target>", mention=true)` to get their exact nickname, then include `@nickname` in your reply text
- To send a DM, use `yb_send_dm(group_code, name, message)` with optional media files
- The gateway delivers your text reply to the Yuanbao chat automatically — no special send tool needed

## Gateway Service

After platform setup, start the gateway:

```bash
hermes gateway start      # Background service
hermes gateway run        # Foreground
hermes gateway status     # Check status
```

Logs: `~/.hermes/logs/gateway.log`

## Pitfalls

1. **QR codes expire quickly (~30s).** The wizard auto-refreshes 3 times. If all expire, re-run the wizard.
2. **iLink bot accounts can't join ordinary WeChat groups.** This is a Tencent limitation, not a Hermes bug.
3. **The gateway setup wizard is a TUI.** Background PTY processes have trouble with it — always pipe stdin or run in a real terminal.
4. **pip install -c flag is blocked by Hermes security.** Use a `.py` file or `execute_code` tool for QR code generation.
5. **WSL2 gateway dies on session close.** Enable systemd in `/etc/wsl.conf` or use `nohup`.
6. **iLink QR login shows "Open Claw's AI bot" on WeChat.** The code has `ILINK_APP_ID = "bot"` hardcoded — this is a shared iLink app whose server-side display name can't be changed from Hermes. **Do not modify the code.** The fix is a 5-second workaround: tell the user to open the bot's contact card in WeChat, tap the name/avatar area, and change the 备注 (nickname). This overrides the display name locally on their phone. The user's reaction in a real session was: "我改个备注就行了" (I'll just change the nickname) — this is the correct, pragmatic approach.

7. **Piped input gets consumed by intermediate prompts.** The wizard shows "Reconfigure? [y/N]:" ONLY when prior config exists (the "Weixin is already configured" banner). For a **fresh** setup use `printf 'Y\n3\nY\n1\n'` (3 inputs: gateway→platform→QR). For **reconfigure** use `printf 'Y\n3\ny\nY\n1\n'` (4 inputs: add `y` for reconfirm). Using the wrong pipe offsets all answers: e.g. sending `y` on a fresh setup causes the Y/n default on the QR prompt to consume it, producing "✗ Please enter 'y' or 'n'" and breaking the sequence.

8. **Credentials saved to .env even if wizard exits before DM prompt.** The wizard writes `WEIXIN_ACCOUNT_ID`, `WEIXIN_TOKEN`, `WEIXIN_BASE_URL`, `WEIXIN_CDN_BASE_URL` to `.env` immediately upon QR login success, *before* the DM policy question. If an automated pipe exhausted input before reaching that question, check `.env` — you can manually add `WEIXIN_DM_POLICY=pairing` and start the gateway directly (`hermes gateway start`). The adapter reads credentials from .env on startup.

9. **Gateway shows \"connected\" when iLink session is already expired.** `hermes gateway status` and `gateway_state.json` report `\"state\":\"connected\"` as long as the adapter process is running, even when the underlying iLink session token is dead. The only trustworthy indicators are: (a) the `[Weixin] Session expired; pausing for 10 minutes` log entry, or (b) a failed `hermes send` returning `errcode=-14 errmsg=session timeout`. Do not rely on `gateway status` alone — always perform a send test or check the log for expiry markers.

10. **Deleting the context token file locally does NOT fix session expiry.** The file `weixin/accounts/<id>.context-tokens.json` is a client-side session cache. If the iLink server considers the session invalid, removing this file has no effect — the next QR code generated by the wizard will be the same expired session. Only a fresh QR scan creates a new server-side session.

11. **Cron jobs and iLink expiry are fundamentally incompatible without monitoring.** Since iLink sessions expire unpredictably and require phone-based QR scanning to recover, any cron job that depends on WeChat delivery must include a health check that detects session expiry and alerts the user to re-login, rather than silently failing.

12. **MEDIA: links may not render on Hermes desktop app.** When sharing a QR code image via the `MEDIA:/path` syntax in the Hermes desktop GUI, the image may fail to display inline. Always provide the **absolute file path** as a fallback (e.g. `C:\Users\<user>\wechat_qr.png`) so the user can open it manually.

## Verification

### Initial Setup Check

After setup, send a message to the bot on the platform and check the gateway log:

```bash
grep -i "weixin\\|dingtalk\\|feishu" ~/.hermes/logs/gateway.log | tail -10
```

Use `/platforms` or `hermes gateway status` to confirm the platform is connected.

### Ongoing Health Check (Session Expiry)

**Do NOT rely solely on `gateway status`** — it reports `"connected"` even when the iLink session is expired. Always probe the session with a send test or log inspection:

```bash
# Quick log check for recent expiry
grep -c "Session expired" ~/.hermes/logs/gateway.log | awk '{if($0>0) print "WARNING: Session has expired " $0 " times this run"; else print "OK: No session expiry detected"}'

# Direct send test (verifies the session is alive)
hermes send --to weixin "🟢 健康检查" 2>&1 && echo "✓ WeChat session alive" || echo "✗ WeChat session dead — needs QR re-login"
```

See the **Weixin → Maintenance** section for full recovery steps.
