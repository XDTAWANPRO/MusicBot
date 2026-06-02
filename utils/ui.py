"""
utils/ui.py — v4
==================
UI ที่สวยขึ้น + Progress bar + สถานะเพลงแบบ real-time
"""

import discord
from discord.ui import View, Button, Select
from discord import ButtonStyle
import logging

log = logging.getLogger("UI")

# ── Colors ────────────────────────────────────────────────────────────────────
C_GREEN  = 0x1DB954   # กำลังเล่น
C_ORANGE = 0xF0A500   # หยุดชั่วคราว
C_RED    = 0xED4245   # หยุด/error
C_BLUE   = 0x5865F2   # คิว/info
C_DARK   = 0x1E1F22   # idle
C_PURPLE = 0x9B59B6   # เพลงถัดไป

# ── Status Icons ──────────────────────────────────────────────────────────────
STATUS_PLAYING = "<a:playing:1> "   # ถ้าไม่มี animated emoji ใช้ข้อความแทน
BADGE_LOOP     = "🔁"
BADGE_SHUFFLE  = "🔀"
BADGE_VOLUME   = "🔊"


# ── Idle Embed ────────────────────────────────────────────────────────────────
def build_idle_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎵  Music Player",
        description=(
            "```\n"
            "  ไม่มีเพลงกำลังเล่นอยู่\n"
            "```\n"
            "พิมพ์ `/play` เพื่อเริ่มเล่นเพลง"
        ),
        color=C_DARK,
    )
    embed.set_footer(text="Music Bot  •  พร้อมรับคำสั่ง")
    return embed


# ── Now Playing Embed ─────────────────────────────────────────────────────────
def build_now_playing_embed(player) -> discord.Embed:
    song      = player.current
    is_paused = player.is_paused
    color     = C_ORANGE if is_paused else C_GREEN

    # ── Header ──
    if is_paused:
        title = "⏸️  หยุดชั่วคราว"
    else:
        title = "▶️  กำลังเล่น"

    embed = discord.Embed(title=title, color=color)

    # ── Song Info ──
    embed.add_field(
        name="🎵  เพลง",
        value=f"### [{song.title}]({song.webpage_url})",
        inline=False,
    )
    embed.add_field(name="👤  ศิลปิน",   value=f"`{song.uploader}`",    inline=True)
    embed.add_field(name="⏱️  ความยาว",  value=f"`{song.duration_str}`", inline=True)
    embed.add_field(
        name="📋  คิว",
        value=f"`{len(player.queue)} เพลง`" if player.queue else "`ว่าง`",
        inline=True,
    )

    # ── Progress Bar ──
    embed.add_field(
        name="",
        value=player.progress_bar(width=22),
        inline=False,
    )

    # ── Status Badges ──
    badges = []
    if player.loop:
        badges.append(f"{BADGE_LOOP} **Loop**")
    if player.shuffle:
        badges.append(f"{BADGE_SHUFFLE} **Shuffle**")
    vol = int(player.volume * 100)
    vol_icon = "🔇" if vol == 0 else "🔉" if vol < 50 else "🔊"
    badges.append(f"{vol_icon} **{vol}%**")
    embed.add_field(name="", value="  •  ".join(badges), inline=False)

    # ── Next Up ──
    if player.queue:
        next_songs = player.queue[:3]
        lines = [f"`{i}.`  {s.title[:38]}" for i, s in enumerate(next_songs, 1)]
        if len(player.queue) > 3:
            lines.append(f"_...และอีก {len(player.queue)-3} เพลง_")
        embed.add_field(
            name="📝  ถัดไป",
            value="\n".join(lines),
            inline=False,
        )

    # ── Thumbnail & Footer ──
    if song.thumbnail:
        embed.set_thumbnail(url=song.thumbnail)

    footer_parts = []
    if song.requester:
        footer_parts.append(f"ขอโดย {song.requester.display_name}")
    footer_parts.append("Music Bot v4")
    embed.set_footer(
        text="  •  ".join(footer_parts),
        icon_url=song.requester.display_avatar.url if song.requester else discord.Embed.Empty,
    )
    return embed


# ── Queue Embed ───────────────────────────────────────────────────────────────
def build_queue_embed(player, page: int = 0) -> discord.Embed:
    PER_PAGE = 10
    queue    = player.queue
    total    = len(queue)
    pages    = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page     = max(0, min(page, pages - 1))
    start    = page * PER_PAGE

    embed = discord.Embed(
        title=f"📋  คิวเพลง",
        color=C_BLUE,
    )

    # เพลงปัจจุบัน
    if player.current:
        icon = "⏸️" if player.is_paused else "▶️"
        embed.add_field(
            name=f"{icon}  กำลังเล่น",
            value=(
                f"**[{player.current.title}]({player.current.webpage_url})**\n"
                f"{player.progress_bar(width=18)}\n"
                f"👤  {player.current.requester.display_name if player.current.requester else '—'}"
            ),
            inline=False,
        )

    # รายการคิว
    if not queue:
        embed.add_field(name="📝  รายการ", value="ไม่มีเพลงในคิว", inline=False)
    else:
        lines = []
        for i, s in enumerate(queue[start:start+PER_PAGE], start+1):
            req = s.requester.display_name if s.requester else "—"
            lines.append(
                f"`{i:2}.`  **{s.title[:40]}**\n"
                f"       ⏱️ `{s.duration_str}`  👤 {req}"
            )
        embed.add_field(
            name=f"📝  รายการ ({total} เพลง)  —  หน้า {page+1}/{pages}",
            value="\n".join(lines),
            inline=False,
        )

    # สรุปด้านล่าง
    total_sec = sum(s.duration for s in queue)
    m, s2 = divmod(total_sec, 60)
    h, m  = divmod(m, 60)
    dur   = f"{h}h {m}m" if h else f"{m}m {s2}s"

    flags = []
    if player.loop:    flags.append("🔁 Loop")
    if player.shuffle: flags.append("🔀 Shuffle")
    embed.set_footer(
        text=f"รวม {dur}  •  {'  '.join(flags) if flags else '—'}  •  🔊 {int(player.volume*100)}%"
    )
    return embed


# ── Search Embed ──────────────────────────────────────────────────────────────
def build_search_embed(query: str, songs: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"🔍  ค้นหา: {query[:50]}",
        description="เลือกเพลงจาก dropdown ด้านล่าง",
        color=C_PURPLE,
    )
    for i, s in enumerate(songs[:5], 1):
        embed.add_field(
            name=f"{i}.  {s.title[:50]}",
            value=f"👤 `{s.uploader}`  •  ⏱️ `{s.duration_str}`",
            inline=False,
        )
    embed.set_footer(text="⏰ หมดเวลาใน 30 วินาที")
    return embed


# ── Music Control View ────────────────────────────────────────────────────────
class MusicControlView(View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player
        self._sync()

    def _sync(self):
        for c in self.children:
            if not isinstance(c, Button): continue
            cid = c.custom_id
            if cid == "p_pp":
                if self.player.is_paused:
                    c.label, c.style = "▶️  เล่นต่อ", ButtonStyle.success
                else:
                    c.label, c.style = "⏸️  หยุด",    ButtonStyle.secondary
            elif cid == "p_loop":
                c.label = "🔁  ON" if self.player.loop    else "🔁  OFF"
                c.style = ButtonStyle.primary if self.player.loop    else ButtonStyle.secondary
            elif cid == "p_shuffle":
                c.label = "🔀  ON" if self.player.shuffle else "🔀  OFF"
                c.style = ButtonStyle.primary if self.player.shuffle else ButtonStyle.secondary

    async def _refresh(self, interaction: discord.Interaction):
        self._sync()
        embed = build_now_playing_embed(self.player)
        await interaction.response.edit_message(embed=embed, view=self)

    # ── Row 0 — Main ─────────────────────────────────────────────────────────
    @discord.ui.button(label="⏸️  หยุด", style=ButtonStyle.secondary,
                       custom_id="p_pp", row=0)
    async def btn_pp(self, interaction: discord.Interaction, btn: Button):
        if not await _check_vc(interaction, self.player): return
        who = str(interaction.user)
        if self.player.is_paused: self.player.resume(by=who)
        else:                     self.player.pause(by=who)
        await self._refresh(interaction)

    @discord.ui.button(label="⏭️  ข้าม", style=ButtonStyle.primary,
                       custom_id="p_skip", row=0)
    async def btn_skip(self, interaction: discord.Interaction, btn: Button):
        if not await _check_vc(interaction, self.player): return
        if not self.player.current:
            await interaction.response.send_message("❌ ไม่มีเพลงอยู่", ephemeral=True)
            return
        await interaction.response.defer()
        self.player.skip(by=str(interaction.user))

    @discord.ui.button(label="⏹️  หยุด/ออก", style=ButtonStyle.danger,
                       custom_id="p_stop", row=0)
    async def btn_stop(self, interaction: discord.Interaction, btn: Button):
        if not await _check_vc(interaction, self.player): return
        await interaction.response.defer()
        await self.player.destroy()

    # ── Row 1 — Options ──────────────────────────────────────────────────────
    @discord.ui.button(label="🔁  OFF", style=ButtonStyle.secondary,
                       custom_id="p_loop", row=1)
    async def btn_loop(self, interaction: discord.Interaction, btn: Button):
        if not await _check_vc(interaction, self.player): return
        self.player.toggle_loop(by=str(interaction.user))
        await self._refresh(interaction)

    @discord.ui.button(label="🔀  OFF", style=ButtonStyle.secondary,
                       custom_id="p_shuffle", row=1)
    async def btn_shuffle(self, interaction: discord.Interaction, btn: Button):
        if not await _check_vc(interaction, self.player): return
        self.player.toggle_shuffle(by=str(interaction.user))
        await self._refresh(interaction)

    @discord.ui.button(label="📋  จัดคิว", style=ButtonStyle.secondary,
                       custom_id="p_queue", row=1)
    async def btn_queue(self, interaction: discord.Interaction, btn: Button):
        embed = build_queue_embed(self.player)
        view  = QueueManagerView(self.player)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── Row 2 — Volume ───────────────────────────────────────────────────────
    @discord.ui.button(label="🔇  Mute", style=ButtonStyle.secondary,
                       custom_id="p_mute", row=2)
    async def btn_mute(self, interaction: discord.Interaction, btn: Button):
        if not await _check_vc(interaction, self.player): return
        vol = 0.0 if self.player.volume > 0 else 0.7
        self.player.set_volume(vol, by=str(interaction.user))
        await self._refresh(interaction)

    @discord.ui.button(label="🔉  -10%", style=ButtonStyle.secondary,
                       custom_id="p_vdn", row=2)
    async def btn_vdn(self, interaction: discord.Interaction, btn: Button):
        if not await _check_vc(interaction, self.player): return
        self.player.set_volume(self.player.volume - 0.1, by=str(interaction.user))
        await self._refresh(interaction)

    @discord.ui.button(label="🔊  +10%", style=ButtonStyle.secondary,
                       custom_id="p_vup", row=2)
    async def btn_vup(self, interaction: discord.Interaction, btn: Button):
        if not await _check_vc(interaction, self.player): return
        self.player.set_volume(self.player.volume + 0.1, by=str(interaction.user))
        await self._refresh(interaction)

    async def on_error(self, interaction, error, item):
        log.error(f"Button error [{item.custom_id}]: {error}")
        try:
            await interaction.response.send_message(f"❌ `{error}`", ephemeral=True)
        except Exception:
            pass


# ── Queue Manager View ────────────────────────────────────────────────────────
class QueueManagerView(View):
    def __init__(self, player, page: int = 0):
        super().__init__(timeout=60)
        self.player = player
        self.page   = page

    async def _refresh(self, interaction: discord.Interaction):
        embed = build_queue_embed(self.player, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀️", style=ButtonStyle.secondary, custom_id="q_prev", row=0)
    async def btn_prev(self, interaction: discord.Interaction, btn: Button):
        if self.page > 0: self.page -= 1
        await self._refresh(interaction)

    @discord.ui.button(label="▶️", style=ButtonStyle.secondary, custom_id="q_next", row=0)
    async def btn_next(self, interaction: discord.Interaction, btn: Button):
        max_p = max(0, (len(self.player.queue) - 1) // 10)
        if self.page < max_p: self.page += 1
        await self._refresh(interaction)

    @discord.ui.button(label="↕️  ย้ายเพลง", style=ButtonStyle.primary,
                       custom_id="q_move", row=1)
    async def btn_move(self, interaction: discord.Interaction, btn: Button):
        await interaction.response.send_modal(MoveSongModal(self.player, self))

    @discord.ui.button(label="🗑️  ลบเพลง", style=ButtonStyle.danger,
                       custom_id="q_remove", row=1)
    async def btn_remove(self, interaction: discord.Interaction, btn: Button):
        await interaction.response.send_modal(RemoveSongModal(self.player, self))

    @discord.ui.button(label="⏩  ข้ามไปเพลงที่", style=ButtonStyle.primary,
                       custom_id="q_skipto", row=2)
    async def btn_skipto(self, interaction: discord.Interaction, btn: Button):
        await interaction.response.send_modal(SkipToModal(self.player, self))

    @discord.ui.button(label="🧹  ล้างคิว", style=ButtonStyle.danger,
                       custom_id="q_clear", row=2)
    async def btn_clear(self, interaction: discord.Interaction, btn: Button):
        self.player.queue.clear()
        log.info(f"[{self.player.guild.name}] 🧹 ล้างคิว  โดย {interaction.user}")
        await self.player.update_panel()
        await self._refresh(interaction)

    async def on_timeout(self):
        for c in self.children: c.disabled = True


# ── Modals ────────────────────────────────────────────────────────────────────
class MoveSongModal(discord.ui.Modal, title="↕️  ย้ายเพลงในคิว"):
    from_f = discord.ui.TextInput(label="จากตำแหน่งที่", placeholder="เช่น 3", min_length=1, max_length=3)
    to_f   = discord.ui.TextInput(label="ไปยังตำแหน่งที่", placeholder="เช่น 1", min_length=1, max_length=3)

    def __init__(self, player, qv):
        super().__init__()
        self.player, self.qv = player, qv

    async def on_submit(self, interaction: discord.Interaction):
        try: f, t = int(self.from_f.value), int(self.to_f.value)
        except ValueError:
            return await interaction.response.send_message("❌ กรอกตัวเลข", ephemeral=True)
        if not self.player.move_song(f, t):
            return await interaction.response.send_message(
                f"❌ ตำแหน่งไม่ถูกต้อง (คิวมี {len(self.player.queue)} เพลง)", ephemeral=True)
        await self.player.update_panel()
        await interaction.response.edit_message(
            embed=build_queue_embed(self.player, self.qv.page), view=self.qv)


class RemoveSongModal(discord.ui.Modal, title="🗑️  ลบเพลงออกจากคิว"):
    idx_f = discord.ui.TextInput(label="ตำแหน่งที่ลบ", placeholder="เช่น 2", min_length=1, max_length=3)

    def __init__(self, player, qv):
        super().__init__()
        self.player, self.qv = player, qv

    async def on_submit(self, interaction: discord.Interaction):
        try: idx = int(self.idx_f.value)
        except ValueError:
            return await interaction.response.send_message("❌ กรอกตัวเลข", ephemeral=True)
        song = self.player.remove_song(idx)
        if not song:
            return await interaction.response.send_message(f"❌ ไม่พบ #{idx}", ephemeral=True)
        await self.player.update_panel()
        await interaction.response.edit_message(
            embed=build_queue_embed(self.player, self.qv.page), view=self.qv)


class SkipToModal(discord.ui.Modal, title="⏩  ข้ามไปเพลงที่"):
    idx_f = discord.ui.TextInput(label="ตำแหน่งที่ข้าม", placeholder="เช่น 5", min_length=1, max_length=3)

    def __init__(self, player, qv):
        super().__init__()
        self.player, self.qv = player, qv

    async def on_submit(self, interaction: discord.Interaction):
        try: idx = int(self.idx_f.value)
        except ValueError:
            return await interaction.response.send_message("❌ กรอกตัวเลข", ephemeral=True)
        i = idx - 1
        if not (0 <= i < len(self.player.queue)):
            return await interaction.response.send_message(f"❌ ไม่พบ #{idx}", ephemeral=True)
        target = self.player.queue.pop(i)
        self.player.queue.insert(0, target)
        self.player.skip(by=str(interaction.user))
        await interaction.response.send_message(f"⏩ ข้ามไปเพลง #{idx} แล้ว!", ephemeral=True)


# ── Search Select View ────────────────────────────────────────────────────────
class SearchSelectView(View):
    def __init__(self, songs: list):
        super().__init__(timeout=30)
        self.songs    = songs
        self.selected = None
        opts = [
            discord.SelectOption(
                label=s.title[:100],
                description=f"{s.uploader[:40]}  •  {s.duration_str}",
                value=str(i), emoji="🎵",
            ) for i, s in enumerate(songs[:5])
        ]
        sel = Select(placeholder="🔍 เลือกเพลงที่ต้องการ...", options=opts, custom_id="s_sel")
        sel.callback = self._pick
        self.add_item(sel)
        cancel = Button(label="❌ ยกเลิก", style=ButtonStyle.danger, custom_id="s_cancel")
        cancel.callback = self._cancel
        self.add_item(cancel)

    async def _pick(self, interaction: discord.Interaction):
        self.selected = self.songs[int(interaction.data["values"][0])]
        self.stop()
        await interaction.response.defer()

    async def _cancel(self, interaction: discord.Interaction):
        self.stop()
        await interaction.response.edit_message(
            embed=discord.Embed(title="❌ ยกเลิก", color=C_RED), view=None)

    async def on_timeout(self):
        for c in self.children: c.disabled = True


# ── Guard ─────────────────────────────────────────────────────────────────────
async def _check_vc(interaction: discord.Interaction, player) -> bool:
    vc      = interaction.guild.voice_client
    user_vc = interaction.user.voice
    if not vc or not user_vc:
        await interaction.response.send_message("❌ คุณต้องอยู่ในห้องเสียงก่อน", ephemeral=True)
        return False
    if user_vc.channel.id != vc.channel.id:
        await interaction.response.send_message(
            f"❌ ต้องอยู่ใน **{vc.channel.name}** เพื่อควบคุมบอท", ephemeral=True)
        return False
    return True
