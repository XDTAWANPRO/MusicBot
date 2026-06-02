"""
cogs/music.py — v4
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging

from utils.player import MusicPlayer, search_songs, load_playlist
from utils.ui import (
    SearchSelectView, build_search_embed, build_queue_embed,
    QueueManagerView, C_RED, C_BLUE, C_GREEN,
)

log = logging.getLogger("MusicCog")


class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_player(self, guild, channel) -> MusicPlayer:
        if guild.id not in self.bot.music_players:
            self.bot.music_players[guild.id] = MusicPlayer(self.bot, guild, channel)
        return self.bot.music_players[guild.id]

    async def _join_vc(self, interaction: discord.Interaction):
        user_vc = interaction.user.voice
        if not user_vc:
            await interaction.followup.send(
                embed=discord.Embed(title="❌ คุณยังไม่ได้เข้าห้องเสียง", color=C_RED),
                ephemeral=True,
            )
            return None
        vc = interaction.guild.voice_client
        try:
            if not vc:
                vc = await user_vc.channel.connect()
                log.info(f"[{interaction.guild.name}] เข้าห้องเสียง: {user_vc.channel.name}  (เรียกโดย {interaction.user})")
            elif vc.channel.id != user_vc.channel.id:
                await vc.move_to(user_vc.channel)
                log.info(f"[{interaction.guild.name}] ย้ายไป: {user_vc.channel.name}")
        except Exception as e:
            log.error(f"[{interaction.guild.name}] เข้าห้องเสียงไม่ได้: {e}")
            await interaction.followup.send("❌ เข้าห้องเสียงไม่ได้", ephemeral=True)
            return None
        return vc

    async def _enqueue_or_play(self, player, song, interaction):
        vc = interaction.guild.voice_client
        playing = vc and (vc.is_playing() or vc.is_paused())
        if playing:
            player.queue.append(song)
            log.info(f"[{player.guild.name}] เพิ่มคิว #{len(player.queue)}: {song.title}  โดย {interaction.user}")
            embed = discord.Embed(
                title="✅  เพิ่มเข้าคิวแล้ว",
                description=f"**[{song.title}]({song.webpage_url})**",
                color=C_BLUE,
            )
            embed.add_field(name="ตำแหน่ง", value=f"`#{len(player.queue)}`", inline=True)
            embed.add_field(name="⏱️", value=f"`{song.duration_str}`",        inline=True)
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            await interaction.followup.send(embed=embed, ephemeral=True)
            await player.update_panel()
        else:
            await player.play(song)
            await interaction.followup.send(
                embed=discord.Embed(
                    title="▶️  เริ่มเล่นแล้ว",
                    description=f"**[{song.title}]({song.webpage_url})**",
                    color=C_GREEN,
                ),
                ephemeral=True,
            )

    # /panel ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="panel", description="📺 สร้าง/ย้าย Music Panel มาที่ห้องนี้")
    async def panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = self.bot.music_players.get(interaction.guild.id)
        log.info(f"[{interaction.guild.name}] /panel  โดย {interaction.user}  → #{interaction.channel.name}")
        if not player:
            player = self._get_player(interaction.guild, interaction.channel)
            await player._send_new_panel()
            await interaction.followup.send(
                f"✅ สร้าง Music Panel ที่ {interaction.channel.mention} แล้ว",
                ephemeral=True,
            )
        else:
            await player.set_panel_channel(interaction.channel)
            await interaction.followup.send(
                f"✅ ย้าย Music Panel มาที่ {interaction.channel.mention} แล้ว",
                ephemeral=True,
            )

    # /play ───────────────────────────────────────────────────────────────────
    @app_commands.command(name="play", description="🎵 เล่นเพลง (ชื่อ / URL / Playlist)")
    @app_commands.describe(query="ชื่อเพลง, YouTube URL, หรือ Playlist URL")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        log.info(f"[{interaction.guild.name}] /play '{query}'  โดย {interaction.user}")

        vc = await self._join_vc(interaction)
        if not vc:
            return

        existing = self.bot.music_players.get(interaction.guild.id)
        channel  = existing.panel_channel if existing else interaction.channel
        player   = self._get_player(interaction.guild, channel)
        is_url   = query.startswith(("http://", "https://", "www."))

        # Playlist
        if is_url and ("playlist" in query or "list=" in query):
            msg   = await interaction.followup.send(
                embed=discord.Embed(title="📜  กำลังโหลด Playlist...", color=C_BLUE)
            )
            songs = await load_playlist(query, requester=interaction.user)
            if not songs:
                await msg.edit(embed=discord.Embed(title="❌ โหลด Playlist ไม่ได้", color=C_RED))
                return
            first = songs[0]
            player.queue.extend(songs[1:])
            log.info(f"[{interaction.guild.name}] Playlist {len(songs)} เพลง  โดย {interaction.user}")
            await msg.edit(embed=discord.Embed(
                title=f"📜  โหลด Playlist แล้ว — {len(songs)} เพลง", color=C_GREEN,
            ))
            await self._enqueue_or_play(player, first, interaction)
            return

        # URL ตรง
        if is_url:
            songs = await search_songs(query)
            if not songs:
                await interaction.followup.send("❌ ไม่พบเพลงจาก URL", ephemeral=True)
                return
            songs[0].requester = interaction.user
            await self._enqueue_or_play(player, songs[0], interaction)
            return

        # ค้นหาด้วยชื่อ
        songs = await search_songs(query)
        if not songs:
            await interaction.followup.send(
                embed=discord.Embed(title="❌ ไม่พบเพลง", description=f"`{query}`", color=C_RED),
                ephemeral=True,
            )
            return

        embed  = build_search_embed(query, songs)
        sv     = SearchSelectView(songs)
        smsg   = await interaction.followup.send(embed=embed, view=sv)
        await sv.wait()
        try: await smsg.delete()
        except Exception: pass
        if not sv.selected:
            return
        sv.selected.requester = interaction.user
        log.info(f"[{interaction.guild.name}] เลือกเพลง: {sv.selected.title}  โดย {interaction.user}")
        await self._enqueue_or_play(player, sv.selected, interaction)

    # /queue ──────────────────────────────────────────────────────────────────
    @app_commands.command(name="queue", description="📋 ดูและจัดการคิวเพลง")
    async def queue_cmd(self, interaction: discord.Interaction):
        player = self.bot.music_players.get(interaction.guild.id)
        if not player or not player.current:
            await interaction.response.send_message(
                embed=discord.Embed(title="📋 ไม่มีเพลงเล่นอยู่", color=C_BLUE),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=build_queue_embed(player),
            view=QueueManagerView(player),
            ephemeral=True,
        )

    # /skip ───────────────────────────────────────────────────────────────────
    @app_commands.command(name="skip", description="⏭️ ข้ามเพลงปัจจุบัน")
    async def skip(self, interaction: discord.Interaction):
        player = self.bot.music_players.get(interaction.guild.id)
        if not player or not player.current:
            await interaction.response.send_message("❌ ไม่มีเพลงอยู่", ephemeral=True)
            return
        player.skip(by=str(interaction.user))
        await interaction.response.send_message("⏭️ ข้ามแล้ว!", ephemeral=True)

    # /volume ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="volume", description="🔊 ตั้ง Volume (0-100)")
    @app_commands.describe(level="ระดับเสียง 0-100")
    async def volume(self, interaction: discord.Interaction, level: int):
        player = self.bot.music_players.get(interaction.guild.id)
        if not player:
            await interaction.response.send_message("❌ ไม่มีเพลงเล่นอยู่", ephemeral=True)
            return
        level = max(0, min(100, level))
        player.set_volume(level / 100, by=str(interaction.user))
        await interaction.response.send_message(f"🔊 Volume = **{level}%**", ephemeral=True)
        await player.update_panel()

    # /move ───────────────────────────────────────────────────────────────────
    @app_commands.command(name="move", description="↕️ ย้ายเพลงในคิว")
    @app_commands.describe(from_pos="จากตำแหน่งที่", to_pos="ไปยังตำแหน่งที่")
    async def move(self, interaction: discord.Interaction, from_pos: int, to_pos: int):
        player = self.bot.music_players.get(interaction.guild.id)
        if not player:
            await interaction.response.send_message("❌ ไม่มีคิว", ephemeral=True)
            return
        if not player.move_song(from_pos, to_pos):
            await interaction.response.send_message(
                f"❌ ตำแหน่งไม่ถูกต้อง (คิวมี {len(player.queue)} เพลง)", ephemeral=True)
            return
        await interaction.response.send_message(
            f"↕️ ย้าย #{from_pos} → #{to_pos} แล้ว", ephemeral=True)
        await player.update_panel()

    # /remove ─────────────────────────────────────────────────────────────────
    @app_commands.command(name="remove", description="🗑️ ลบเพลงออกจากคิว")
    @app_commands.describe(position="ตำแหน่งที่ต้องการลบ")
    async def remove(self, interaction: discord.Interaction, position: int):
        player = self.bot.music_players.get(interaction.guild.id)
        if not player:
            await interaction.response.send_message("❌ ไม่มีคิว", ephemeral=True)
            return
        song = player.remove_song(position)
        if not song:
            await interaction.response.send_message(f"❌ ไม่พบ #{position}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"🗑️ ลบ **{song.title}** แล้ว", ephemeral=True)
        await player.update_panel()

    # /stop ───────────────────────────────────────────────────────────────────
    @app_commands.command(name="stop", description="⏹️ หยุดเพลงและออกจากห้องเสียง")
    async def stop(self, interaction: discord.Interaction):
        player = self.bot.music_players.get(interaction.guild.id)
        if not player:
            await interaction.response.send_message("❌ บอทไม่ได้เล่นเพลง", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await player.destroy()
        await interaction.followup.send("⏹️ หยุดและออกจากห้องเสียงแล้ว", ephemeral=True)


async def setup(bot):
    await bot.add_cog(MusicCog(bot))
