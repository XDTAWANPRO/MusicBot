"""
Discord Music Bot v4
====================
รันด้วย: python bot.py
"""

import discord
from discord.ext import commands
import os, asyncio, logging, sys
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
class BotFormatter(logging.Formatter):
    """Log แบบอ่านง่าย — รายงานเหตุการณ์ ไม่ใช่ debug"""
    ICONS = {
        logging.INFO:    "•",
        logging.WARNING: "⚠",
        logging.ERROR:   "✗",
        logging.CRITICAL:"‼",
    }
    COLORS = {
        logging.INFO:    "\033[97m",    # White
        logging.WARNING: "\033[33m",    # Yellow
        logging.ERROR:   "\033[31m",    # Red
        logging.CRITICAL:"\033[35m",    # Magenta
    }
    RESET = "\033[0m"
    DIM   = "\033[2m"
    CYAN  = "\033[36m"
    BOLD  = "\033[1m"

    def format(self, record):
        icon  = self.ICONS.get(record.levelno, "·")
        color = self.COLORS.get(record.levelno, "")
        time  = self.formatTime(record, "%H:%M:%S")
        name  = record.name.ljust(10)
        msg   = record.getMessage()
        return (
            f"{self.DIM}{time}{self.RESET}  "
            f"{color}{icon}{self.RESET}  "
            f"{self.CYAN}{name}{self.RESET}  "
            f"{color}{msg}{self.RESET}"
        )

def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(BotFormatter())

    fh = logging.FileHandler("bot.log", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(name)-10s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    # ซ่อน noise จาก library
    for name in ("discord.gateway", "discord.client", "discord.http",
                 "discord.voice_client", "yt_dlp"):
        logging.getLogger(name).setLevel(logging.ERROR)

    root.addHandler(ch)
    root.addHandler(fh)

setup_logging()
log = logging.getLogger("Bot")

# ── Bot ───────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states    = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
bot.music_players: dict = {}

@bot.event
async def on_ready():
    log.info(f"เข้าสู่ระบบ: {bot.user}  ({len(bot.guilds)} servers)")
    try:
        synced = await bot.tree.sync()
        log.info(f"Sync สำเร็จ {len(synced)} commands")
    except Exception as e:
        log.error(f"Sync ล้มเหลว: {e}")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="🎵 /play")
    )

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    vc = member.guild.voice_client
    if not vc:
        return
    humans = [m for m in vc.channel.members if not m.bot]
    if len(humans) == 0:
        log.info(f"[{member.guild.name}] ไม่มีคนในห้อง — รอ 60s")
        await asyncio.sleep(60)
        vc = member.guild.voice_client
        if vc and len([m for m in vc.channel.members if not m.bot]) == 0:
            player = bot.music_players.get(member.guild.id)
            if player:
                await player.destroy()
            log.info(f"[{member.guild.name}] ออกห้องเสียงอัตโนมัติ")

@bot.event
async def on_guild_remove(guild):
    player = bot.music_players.get(guild.id)
    if player:
        await player.destroy()

async def main():
    async with bot:
        for cog in ["cogs.music"]:
            try:
                await bot.load_extension(cog)
                log.info(f"โหลด cog: {cog}")
            except Exception as e:
                log.error(f"โหลด {cog} ล้มเหลว: {e}")
        await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
