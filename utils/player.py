"""
utils/player.py — v4
======================
- Log รายงานเหตุการณ์ (ใคร/ทำอะไร/ที่ไหน) ไม่ใช่ debug
- ติดตาม elapsed time ของเพลงปัจจุบัน
"""

import asyncio, random, logging, time
from typing import Optional
import discord
import yt_dlp

log = logging.getLogger("Player")

FFMPEG_OPTS = {
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 "
        "-reconnect_delay_max 5 -nostdin"
    ),
    "options": "-vn -bufsize 64k",
}

_YDL_COMMON = {
    "quiet": True, "no_warnings": True, "source_address": "0.0.0.0",
}
YDL_SEARCH   = {**_YDL_COMMON, "format": "bestaudio/best", "noplaylist": True}
YDL_PLAYLIST = {**_YDL_COMMON, "format": "bestaudio/best", "noplaylist": False,
                "playlistend": 50, "extract_flat": "in_playlist"}
YDL_STREAM   = {**_YDL_COMMON, "format": "bestaudio[ext=webm]/bestaudio/best", "noplaylist": True}


# ── Song ──────────────────────────────────────────────────────────────────────
class Song:
    def __init__(self, data: dict, requester=None):
        url = (data.get("webpage_url") or data.get("url")
               or (f"https://www.youtube.com/watch?v={data['id']}" if data.get("id") else ""))
        self.title       = (data.get("title") or "Unknown")[:100]
        self.webpage_url = url
        self.uploader    = data.get("uploader") or data.get("channel") or "Unknown"
        self.duration    = int(data.get("duration") or 0)
        self.thumbnail   = data.get("thumbnail", "")
        self.requester   = requester

    @property
    def duration_str(self) -> str:
        s = int(self.duration or 0)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ── YouTube ───────────────────────────────────────────────────────────────────
async def _ydl(opts: dict, url: str) -> Optional[dict]:
    loop = asyncio.get_event_loop()
    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    try:
        return await loop.run_in_executor(None, _run)
    except Exception as e:
        log.error(f"yt-dlp error: {e}")
        return None

async def search_songs(query: str) -> list[Song]:
    log.info(f"ค้นหาเพลง: '{query}'")
    is_url = query.startswith(("http://", "https://", "www."))
    q      = query if is_url else f"ytsearch5:{query}"
    info   = await _ydl(YDL_SEARCH, q)
    if not info:
        return []
    entries = info.get("entries") or [info]
    songs   = [Song(e) for e in entries if e and e.get("title")]
    log.info(f"พบ {len(songs)} เพลง")
    return songs[:5]

async def load_playlist(url: str, requester=None) -> list[Song]:
    log.info(f"โหลด Playlist: {url[:60]}")
    info = await _ydl(YDL_PLAYLIST, url)
    if not info:
        return []
    entries = info.get("entries", [])
    songs   = [Song(e, requester=requester) for e in entries if e and e.get("title")]
    log.info(f"Playlist: {len(songs)} เพลง")
    return songs

async def get_stream_url(song: Song) -> str:
    info = await _ydl(YDL_STREAM, song.webpage_url)
    if not info:
        return ""
    if "entries" in info:
        info = info["entries"][0]
    return info.get("url", "")


# ── MusicPlayer ───────────────────────────────────────────────────────────────
class MusicPlayer:
    def __init__(self, bot, guild: discord.Guild, channel: discord.TextChannel):
        self.bot     = bot
        self.guild   = guild
        self.channel = channel

        self.queue:   list[Song]      = []
        self.current: Optional[Song]  = None
        self.volume:  float           = 0.7
        self.loop:    bool            = False
        self.shuffle: bool            = False

        # ติดตาม progress
        self._start_time: float       = 0.0   # unix timestamp ตอนเริ่มเล่น
        self._elapsed_offset: float   = 0.0   # วินาทีที่ผ่านไปก่อน pause

        self.panel_msg:     Optional[discord.Message]    = None
        self.panel_channel: Optional[discord.TextChannel] = channel

        log.info(f"[{guild.name}] เริ่มต้น Music Player")

    # ── Progress ──────────────────────────────────────────────────────────────
    @property
    def elapsed(self) -> float:
        """วินาทีที่เพลงเล่นไปแล้ว"""
        if not self.current:
            return 0.0
        if self.is_paused:
            return self._elapsed_offset
        if self._start_time == 0:
            return 0.0
        return self._elapsed_offset + (time.time() - self._start_time)

    @property
    def progress_pct(self) -> float:
        """0.0 – 1.0"""
        if not self.current or not self.current.duration:
            return 0.0
        return min(1.0, self.elapsed / self.current.duration)

    def progress_bar(self, width: int = 20) -> str:
        """▰▰▰▱▱▱▱ progress bar"""
        pct    = self.progress_pct
        filled = round(pct * width)
        bar    = "▰" * filled + "▱" * (width - filled)
        e      = int(self.elapsed)
        em, es = divmod(e, 60)
        eh, em = divmod(em, 60)
        cur    = f"{eh}:{em:02d}:{es:02d}" if eh else f"{em}:{es:02d}"
        return f"`{cur}` {bar} `{self.current.duration_str}`"

    # ── State ─────────────────────────────────────────────────────────────────
    @property
    def is_playing(self) -> bool:
        vc = self.guild.voice_client
        return bool(vc and vc.is_playing())

    @property
    def is_paused(self) -> bool:
        vc = self.guild.voice_client
        return bool(vc and vc.is_paused())

    # ── Play ──────────────────────────────────────────────────────────────────
    async def play(self, song: Song, *, update_panel: bool = True):
        vc = self.guild.voice_client
        if not vc or not vc.is_connected():
            log.error(f"[{self.guild.name}] ไม่มี Voice Client")
            return

        self._stop_current()
        self.current        = song
        self._start_time    = 0.0
        self._elapsed_offset = 0.0

        log.info(f"[{self.guild.name}] ▶ เล่น: {song.title}"
                 + (f"  (ขอโดย {song.requester})" if song.requester else ""))

        stream_url = await get_stream_url(song)
        if not stream_url:
            log.error(f"[{self.guild.name}] ไม่พบ stream URL: {song.title}")
            await self._advance()
            return

        try:
            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS)
            source = discord.PCMVolumeTransformer(source, volume=self.volume)
            vc.play(source, after=self._after)
            self._start_time = time.time()
        except Exception as e:
            log.error(f"[{self.guild.name}] FFmpeg error: {e}")
            await self._advance()
            return

        if update_panel:
            await self.update_panel()

    def _stop_current(self):
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            if hasattr(vc, "_player") and vc._player:
                vc._player.after = None
            vc.stop()

    def _after(self, error):
        if error:
            log.error(f"[{self.guild.name}] Playback error: {error}")
        else:
            log.info(f"[{self.guild.name}] ✓ เล่นเสร็จ: {self.current.title if self.current else '-'}")
        asyncio.run_coroutine_threadsafe(self._advance(), self.bot.loop)

    async def _advance(self):
        if self.loop and self.current:
            log.info(f"[{self.guild.name}] 🔁 Loop: {self.current.title}")
            await self.play(self.current)
            return
        if not self.queue:
            log.info(f"[{self.guild.name}] คิวหมดแล้ว")
            self.current = None
            await self.update_panel()
            return
        if self.shuffle:
            idx  = random.randrange(len(self.queue))
            song = self.queue.pop(idx)
            log.info(f"[{self.guild.name}] 🔀 Shuffle: {song.title}")
        else:
            song = self.queue.pop(0)
        await self.play(song)

    # ── Controls ──────────────────────────────────────────────────────────────
    def pause(self, by=None):
        vc = self.guild.voice_client
        if vc and vc.is_playing():
            self._elapsed_offset += time.time() - self._start_time
            self._start_time = 0.0
            vc.pause()
            log.info(f"[{self.guild.name}] ⏸ หยุดชั่วคราว"
                     + (f"  โดย {by}" if by else ""))

    def resume(self, by=None):
        vc = self.guild.voice_client
        if vc and vc.is_paused():
            self._start_time = time.time()
            vc.resume()
            log.info(f"[{self.guild.name}] ▶ เล่นต่อ"
                     + (f"  โดย {by}" if by else ""))

    def skip(self, by=None):
        vc = self.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            self.loop = False
            vc.stop()
            log.info(f"[{self.guild.name}] ⏭ ข้ามเพลง: {self.current.title if self.current else '-'}"
                     + (f"  โดย {by}" if by else ""))

    def toggle_loop(self, by=None) -> bool:
        self.loop = not self.loop
        log.info(f"[{self.guild.name}] 🔁 Loop {'ON' if self.loop else 'OFF'}"
                 + (f"  โดย {by}" if by else ""))
        return self.loop

    def toggle_shuffle(self, by=None) -> bool:
        self.shuffle = not self.shuffle
        log.info(f"[{self.guild.name}] 🔀 Shuffle {'ON' if self.shuffle else 'OFF'}"
                 + (f"  โดย {by}" if by else ""))
        return self.shuffle

    def set_volume(self, vol: float, by=None):
        self.volume = max(0.0, min(1.0, vol))
        vc = self.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = self.volume
        log.info(f"[{self.guild.name}] 🔊 Volume {int(self.volume*100)}%"
                 + (f"  โดย {by}" if by else ""))

    def move_song(self, f: int, t: int) -> bool:
        fi, ti = f - 1, t - 1
        if not (0 <= fi < len(self.queue) and 0 <= ti < len(self.queue)):
            return False
        song = self.queue.pop(fi)
        self.queue.insert(ti, song)
        log.info(f"[{self.guild.name}] ↕ ย้ายเพลง #{f}→#{t}: {song.title}")
        return True

    def remove_song(self, idx: int) -> Optional[Song]:
        i = idx - 1
        if not (0 <= i < len(self.queue)):
            return None
        song = self.queue.pop(i)
        log.info(f"[{self.guild.name}] 🗑 ลบเพลง #{idx}: {song.title}")
        return song

    async def stop(self, by=None):
        self.queue.clear()
        self.loop = self.shuffle = False
        self.current = None
        vc = self.guild.voice_client
        if vc:
            self._stop_current()
            await vc.disconnect()
        log.info(f"[{self.guild.name}] ⏹ หยุดและออกจากห้องเสียง"
                 + (f"  โดย {by}" if by else ""))

    async def destroy(self):
        await self.stop()
        gid = self.guild.id
        if gid in self.bot.music_players:
            del self.bot.music_players[gid]
        await self.update_panel()

    # ── Panel ─────────────────────────────────────────────────────────────────
    async def set_panel_channel(self, channel: discord.TextChannel):
        log.info(f"[{self.guild.name}] 📺 ย้าย Panel → #{channel.name}")
        self.panel_channel = channel
        if self.panel_msg:
            try:
                await self.panel_msg.delete()
            except Exception:
                pass
            self.panel_msg = None
        await self._send_new_panel()

    async def _send_new_panel(self):
        from utils.ui import build_now_playing_embed, build_idle_embed, MusicControlView
        if not self.panel_channel:
            return
        try:
            embed = build_now_playing_embed(self) if self.current else build_idle_embed()
            view  = MusicControlView(self) if self.current else None
            self.panel_msg = await self.panel_channel.send(embed=embed, view=view)
        except Exception as e:
            log.error(f"[{self.guild.name}] ส่ง Panel ไม่ได้: {e}")

    async def update_panel(self):
        from utils.ui import build_now_playing_embed, build_idle_embed, MusicControlView
        if not self.panel_channel:
            return
        if not self.panel_msg:
            await self._send_new_panel()
            return
        try:
            embed = build_now_playing_embed(self) if self.current else build_idle_embed()
            view  = MusicControlView(self) if self.current else None
            await self.panel_msg.edit(embed=embed, view=view)
        except discord.NotFound:
            self.panel_msg = None
            await self._send_new_panel()
        except Exception as e:
            log.error(f"[{self.guild.name}] อัปเดต Panel ไม่ได้: {e}")
