import os
import sys
import asyncio
import warnings
from datetime import datetime

# Ignore library future warnings
warnings.filterwarnings('ignore')

# Windows terminal UTF-8 encoding & unbuffered output
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

import discord
from discord.ext import commands
from aiohttp import web

# Import our PSX data, indicators, and Gemini AI pipeline
from psx_data_fetcher import analyze_stock

# ==========================================
# CONFIGURATION & TOKENS
# ==========================================
# Read from .env if present
def get_env_var(key, default=""):
    val = os.environ.get(key)
    if val:
        return val
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default

DISCORD_TOKEN = get_env_var("DISCORD_BOT_TOKEN")

# Setup Discord Bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ==========================================
# DISCORD BOT EVENTS & COMMANDS
# ==========================================
@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user.name}#{bot.user.discriminator} (ID: {bot.user.id})")
    print("✅ Discord Python Bot is online and listening for commands!")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="PSX Market | !analyze <SYM>"
        )
    )


@bot.command(name="ping")
async def ping_command(ctx):
    latency = round(bot.latency * 1000)
    await ctx.reply(f"🏓 Pong! Latency: `{latency}ms`")


@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="📈 PSX AI Trading Signal Bot",
        description="Pakistan Stock Exchange (PSX) ke kisi bhi share ka technical analysis aur Gemini AI trading signal hasil karein.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Commands", value="`!analyze <SYMBOL>` - Analyze any PSX stock\n`!ping` - Bot health check\n`!help` - Show this menu", inline=False)
    embed.add_field(name="Examples", value="`!analyze OGDC`\n`!analyze PPL`\n`!analyze SYS`\n`!analyze HUBC`", inline=False)
    embed.set_footer(text="Powered by PSX Portal & Google Gemini AI")
    await ctx.reply(embed=embed)


@bot.command(name="analyze")
async def analyze_command(ctx, symbol: str = None):
    if not symbol:
        await ctx.reply("❌ **Symbol zaroor dein!** Maslan: `!analyze OGDC` ya `!analyze PPL`")
        return

    sym = symbol.upper().strip()
    status_msg = await ctx.reply(f"⏳ Fetching live PSX data and generating AI report for **{sym}**...\nPlease wait...")

    # Run technical analysis & Gemini generation in a thread so bot remains non-blocking
    try:
        data = await asyncio.to_thread(analyze_stock, sym)

        if not data or data.get('latest') is None:
            await status_msg.edit(content=f"❌ **Error:** `{sym}` ka data nahi mil saka. Symbol check karein (e.g. `OGDC`, `PPL`, `SYS`).")
            return

        latest = data['latest']
        report = data.get('report', 'No report generated.')

        close_price = round(latest['Close'], 2)
        rsi_val = round(latest['RSI_14'], 2)
        macd_line = round(latest['MACD_12_26_9'], 2)
        macd_signal = round(latest['MACDs_12_26_9'], 2)
        volume = int(latest['Volume'])

        # Color based on verdict / momentum
        report_lower = report.lower()
        if "buy" in report_lower and "not recommended" not in report_lower and "avoid" not in report_lower:
            embed_color = discord.Color.green()
        elif "sell" in report_lower:
            embed_color = discord.Color.red()
        else:
            embed_color = discord.Color.gold()

        embed = discord.Embed(
            title=f"🤖 AI TRADING REPORT: {sym}",
            description=f"**Date:** {latest['Date']}\n**Current Price:** Rs. {close_price:,.2f}\n**Volume:** {volume:,}",
            color=embed_color,
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="RSI (14)", value=f"`{rsi_val}` ({'Oversold 🟢' if rsi_val < 30 else 'Overbought 🔴' if rsi_val > 70 else 'Neutral ⚪'})", inline=True)
        embed.add_field(name="MACD Line", value=f"`{macd_line}`", inline=True)
        embed.add_field(name="MACD Signal", value=f"`{macd_signal}` ({'Bullish 🟢' if macd_line > macd_signal else 'Bearish 🔴'})", inline=True)

        # Truncate report if it exceeds Discord embed description limit (4096 chars)
        if len(report) > 3900:
            report_trimmed = report[:3900] + "\n... (report truncated)"
        else:
            report_trimmed = report

        embed.add_field(name="📋 Detailed AI Signal & Verdict", value=report_trimmed, inline=False)
        embed.set_footer(text="PSX AI Trading Bot | Free Cloud Ready")

        await status_msg.edit(content=None, embed=embed)

    except Exception as e:
        print(f"Error in analyze_command for {sym}: {e}")
        await status_msg.edit(content=f"❌ Error analyzing `{sym}`: {e}")


# ==========================================
# LIGHTWEIGHT WEB SERVER (FOR CLOUD HOSTING)
# ==========================================
async def handle_ping_web(request):
    return web.Response(text="PSX Trading Signal Bot is Alive and Running!")

async def start_web_server():
    """
    Starts a tiny HTTP server on $PORT for platforms like Render, Koyeb, Railway.
    Allows 24/7 keep-alive via free ping services like UptimeRobot.
    """
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", handle_ping_web)
    app.router.add_get("/health", handle_ping_web)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port, reuse_address=True)
    try:
        await site.start()
        print(f"🌐 Cloud Keep-Alive Web Server listening on port {port}")
    except Exception as e:
        print(f"Web server notice: {e} (running in pure bot mode)")


# ==========================================
# MAIN RUNNER
# ==========================================
async def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("⚠️ ERROR: Discord Bot Token missing! Set DISCORD_BOT_TOKEN in .env or environment variable.")
        sys.exit(1)

    # Start the cloud web server in background
    await start_web_server()

    # Start the discord bot
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
