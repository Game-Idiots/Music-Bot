import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import os
import asyncio
import json
import tempfile
import shutil
from datetime import datetime
import platform
import random

# Load Opus for voice encoding
if not discord.opus.is_loaded():
    arch = platform.machine()
    if arch == 'x86_64':
        opus_path = '/usr/lib/x86_64-linux-gnu/libopus.so.0'
    elif arch == 'aarch64':
        opus_path = '/usr/lib/aarch64-linux-gnu/libopus.so.0'
    else:
        opus_path = None
    if opus_path:
        try:
            discord.opus.load_opus(opus_path)
            print("Opus loaded successfully.")
        except (OSError, discord.opus.OpusNotLoaded):
            print("Warning: Opus library not loaded. Voice features may not work.")
    else:
        print("Warning: Unsupported architecture. Opus library not loaded. Voice features may not work.")


intents = discord.Intents.default()
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)

connections = {}
# players = {}  # Removed as it's not needed
queues = {}

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA_DIR, exist_ok=True)

class PlaylistDB:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(DATA_DIR, 'playlists.json')
        self.db_path = db_path
        self.data = {"playlists": [], "songs": {}, "next_id": 1}
        self.load_data()

    def load_data(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r') as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading JSON data: {e}. Starting with empty data.")
                self.data = {"playlists": [], "songs": {}, "next_id": 1}

    def save_data(self):
        try:
            with open(self.db_path, 'w') as f:
                json.dump(self.data, f, indent=4)
        except IOError as e:
            print(f"Error saving JSON data: {e}")

    def get_next_id(self):
        id_ = self.data["next_id"]
        self.data["next_id"] += 1
        self.save_data()
        return id_

    def create_new_playlist(self, name, user_id, guild_id):
        for p in self.data["playlists"]:
            if p["name"] == name and p["user_id"] == user_id and p["guild_id"] == guild_id:
                return {'success': False, 'error': 'Playlist name already exists'}
        playlist = {
            "id": self.get_next_id(),
            "name": name,
            "user_id": user_id,
            "guild_id": guild_id,
            "is_public": False,
            "created_at": datetime.now().isoformat()
        }
        self.data["playlists"].append(playlist)
        self.data["songs"][str(playlist["id"])] = []
        self.save_data()
        return {'success': True}

    def create_new_public_playlist(self, name, user_id, guild_id):
        for p in self.data["playlists"]:
            if p["name"] == name and p["guild_id"] == guild_id and p["is_public"]:
                return {'success': False, 'error': 'Public playlist name already exists'}
        playlist = {
            "id": self.get_next_id(),
            "name": name,
            "user_id": user_id,
            "guild_id": guild_id,
            "is_public": True,
            "created_at": datetime.now().isoformat()
        }
        self.data["playlists"].append(playlist)
        self.data["songs"][str(playlist["id"])] = []
        self.save_data()
        return {'success': True}

    def get_playlist_by_name(self, name, user_id, guild_id):
        for p in self.data["playlists"]:
            if p["name"] == name and p["user_id"] == user_id and p["guild_id"] == guild_id and not p["is_public"]:
                return p
        return None

    def get_public_playlist_by_name(self, name, guild_id):
        for p in self.data["playlists"]:
            if p["name"] == name and p["guild_id"] == guild_id and p["is_public"]:
                return p
        return None

    def get_user_playlists_in_guild(self, user_id, guild_id):
        return [p for p in self.data["playlists"] if p["user_id"] == user_id and p["guild_id"] == guild_id and not p["is_public"]]

    def get_public_playlists_in_guild(self, guild_id):
        return [p for p in self.data["playlists"] if p["guild_id"] == guild_id and p["is_public"]]

    def add_song(self, playlist_id, url, title, duration):
        if str(playlist_id) not in self.data["songs"]:
            return {'success': False, 'error': 'Playlist not found'}
        songs = self.data["songs"][str(playlist_id)]
        position = len(songs) + 1
        song = {
            "id": self.get_next_id(),
            "playlist_id": playlist_id,
            "url": url,
            "title": title,
            "duration": duration,
            "position": position
        }
        songs.append(song)
        self.save_data()
        return {'success': True}

    def get_songs(self, playlist_id):
        return sorted(self.data["songs"].get(str(playlist_id), []), key=lambda s: s["position"])

    def remove_playlist(self, playlist_id, user_id):
        for p in self.data["playlists"]:
            if p["id"] == playlist_id and p["user_id"] == user_id:
                self.data["playlists"].remove(p)
                self.data["songs"].pop(str(playlist_id), None)
                self.save_data()
                return {'success': True, 'deleted': True}
        return {'success': False}

    def remove_song_from_playlist(self, playlist_id, song_id):
        songs = self.data["songs"].get(str(playlist_id), [])
        for s in songs:
            if s["id"] == song_id:
                songs.remove(s)
                # Reassign positions
                for i, s in enumerate(songs):
                    s["position"] = i + 1
                self.save_data()
                return {'success': True}
        return {'success': False}

    def move_song_in_playlist(self, playlist_id, from_pos, to_pos):
        songs = self.data["songs"].get(str(playlist_id), [])
        if from_pos < 1 or from_pos > len(songs) or to_pos < 1 or to_pos > len(songs):
            return {'success': False}
        song = songs[from_pos - 1]
        songs.remove(song)
        songs.insert(to_pos - 1, song)
        # Reassign positions
        for i, s in enumerate(songs):
            s["position"] = i + 1
        self.save_data()
        return {'success': True}

    def shuffle_playlist(self, playlist_id):
        import random
        songs = self.data["songs"].get(str(playlist_id), [])
        random.shuffle(songs)
        for i, s in enumerate(songs):
            s["position"] = i + 1
        self.save_data()
        return {'success': True}

db = PlaylistDB()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='music :3'))
    await bot.tree.sync()  # Sync slash commands

@bot.tree.command(name='join', description='Join your voice channel')
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message('You need to be in a voice channel!')
        return
    vc = await interaction.user.voice.channel.connect()
    connections[interaction.guild.id] = vc
    await interaction.response.send_message(f'Joined {interaction.user.voice.channel.name}!')

@bot.tree.command(name='leave', description='Leave the voice channel')
async def leave(interaction: discord.Interaction):
    vc = connections.get(interaction.guild.id)
    if not vc:
        await interaction.response.send_message('I am not connected to any voice channel!')
        return
    # player = players.get(interaction.guild.id)  # Removed
    # if player:  # Removed
    #     player.stop()  # Removed
    #     players.pop(interaction.guild.id, None)  # Removed
    if vc.is_playing() or vc.is_paused():
        vc.stop()
    queues.pop(interaction.guild.id, None)
    await vc.disconnect()
    connections.pop(interaction.guild.id, None)
    await interaction.response.send_message('👋 Left the voice channel!')

@bot.tree.command(name='play', description='Play a YouTube video')
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    vc = connections.get(interaction.guild.id)
    if not vc:
        if not interaction.user.voice:
            await interaction.followup.send('You need to be in a voice channel!')
            return
        vc = await interaction.user.voice.channel.connect()
        connections[interaction.guild.id] = vc
    if vc.is_playing() or vc.is_paused():
        vc.stop()
    ydl_opts = {
        'format': 'bestaudio/best',
        'no_warnings': True,
        'noplaylist': True,
        'ffmpeg_location': 'ffmpeg',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = await asyncio.to_thread(ydl.extract_info, url, download=False)
            if info['duration'] > 600:
                await interaction.followup.send('Song is too long!')
                return
            audio_url = info['url']
        except Exception as e:
            await interaction.followup.send(f'Error processing video: {str(e)}')
            return
    # Stream directly instead of downloading
    source = discord.FFmpegPCMAudio(
        audio_url,
        before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        options='-vn'
    )
    vc.play(source)
    await interaction.followup.send(f'Now playing: {info["title"]}')

@bot.tree.command(name='pause', description='Pause the current audio')
async def pause(interaction: discord.Interaction):
    vc = connections.get(interaction.guild.id)
    if not vc or not vc.is_playing():
        await interaction.response.send_message('No audio is currently playing!')
        return
    vc.pause()
    await interaction.response.send_message('⏸️ Audio paused!')

@bot.tree.command(name='resume', description='Resume the paused audio')
async def resume(interaction: discord.Interaction):
    vc = connections.get(interaction.guild.id)
    if not vc or not vc.is_paused():
        await interaction.response.send_message('No audio is currently paused!')
        return
    vc.resume()
    await interaction.response.send_message('▶️ Audio resumed!')

@bot.tree.command(name='stop', description='Stop the current audio and disconnect')
async def stop(interaction: discord.Interaction):
    vc = connections.get(interaction.guild.id)
    # player = players.get(interaction.guild.id)  # Removed
    # if player:  # Removed
    #     player.stop()  # Removed
    #     players.pop(interaction.guild.id, None)  # Removed
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
    queues.pop(interaction.guild.id, None)
    if vc:
        await vc.disconnect()
        connections.pop(interaction.guild.id, None)
    await interaction.response.send_message('⏹️ Stopped audio and disconnected from voice channel!')

@bot.tree.command(name='queue', description='Show the current queue')
async def queue_cmd(interaction: discord.Interaction):
    queue = queues.get(interaction.guild.id)
    if not queue or len(queue) == 0:
        await interaction.response.send_message('No songs in queue!')
        return
    queue_list = '\n'.join([f'{i+1}. **{song["title"]}** ({song.get("duration", "")})' for i, song in enumerate(queue[:10])])
    more = f'\n... and {len(queue) - 10} more songs' if len(queue) > 10 else ''
    await interaction.response.send_message(f'🎵 **Current Queue** ({len(queue)} songs):\n{queue_list}{more}')

@bot.tree.command(name='playlist-create', description='Create a new playlist')
async def playlist_create(interaction: discord.Interaction, name: str):
    result = db.create_new_playlist(name, str(interaction.user.id), str(interaction.guild.id))
    if result['success']:
        await interaction.response.send_message(f'✅ Created playlist: **{name}**', ephemeral=True)
    else:
        await interaction.response.send_message(f'❌ Failed to create playlist: {result["error"]}', ephemeral=True)

@bot.tree.command(name='playlist-add', description='Add a song to your playlist')
async def playlist_add(interaction: discord.Interaction, playlist: str, url: str):
    await interaction.response.defer(ephemeral=True)
    playlist_obj = db.get_playlist_by_name(playlist, str(interaction.user.id), str(interaction.guild.id))
    if not playlist_obj:
        await interaction.followup.send(f'❌ Playlist "{playlist}" not found!')
        return
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True}) as ydl:
        info = await asyncio.to_thread(ydl.extract_info, url, download=False)
        if info['duration'] > 600:
            await interaction.followup.send('Song is too long!')
            return
        result = db.add_song(playlist_obj["id"], url, info['title'], str(info.get('duration_string', '')))
        if result['success']:
            await interaction.followup.send(f'✅ Added **{info["title"]}** to playlist **{playlist}**')
        else:
            await interaction.followup.send(f'❌ Failed to add song: {result["error"]}')

@bot.tree.command(name='playlist-play', description='Play a playlist')
async def playlist_play(interaction: discord.Interaction, name: str, shuffle: bool = False):
    await interaction.response.defer()
    playlist = db.get_playlist_by_name(name, str(interaction.user.id), str(interaction.guild.id))
    if not playlist:
        playlist = db.get_public_playlist_by_name(name, str(interaction.guild.id))
    if not playlist:
        await interaction.followup.send(f'❌ Playlist "{name}" not found!')
        return
    if shuffle:
        db.shuffle_playlist(playlist["id"])
    songs = db.get_songs(playlist["id"])
    if len(songs) == 0:
        await interaction.followup.send(f'❌ Playlist "{name}" is empty!')
        return
    vc = connections.get(interaction.guild.id)
    if not vc:
        if not interaction.user.voice:
            await interaction.followup.send('You need to be in a voice channel!')
            return
        vc = await interaction.user.voice.channel.connect()
        connections[interaction.guild.id] = vc
    if vc.is_playing() or vc.is_paused():
        vc.stop()
    queues[interaction.guild.id] = [{'title': s["title"], 'url': s["url"], 'duration': s["duration"]} for s in songs]
    await play_next_song(interaction.guild.id, vc)
    await interaction.followup.send(f'🎵 Playing playlist **{name}** ({len(songs)} songs)')

@bot.tree.command(name='playlist-list', description='List your playlists')
async def playlist_list(interaction: discord.Interaction):
    playlists = db.get_user_playlists_in_guild(str(interaction.user.id), str(interaction.guild.id))
    if len(playlists) == 0:
        await interaction.response.send_message('You have no personal playlists in this server!', ephemeral=True)
        return
    list_str = '\n'.join([f'• **{p["name"]}** (Created: {p["created_at"]})' for p in playlists])
    await interaction.response.send_message(f'📋 Your personal playlists:\n{list_str}', ephemeral=True)

@bot.tree.command(name='playlist-show', description='Show songs in a playlist')
async def playlist_show(interaction: discord.Interaction, name: str):
    playlist = db.get_playlist_by_name(name, str(interaction.user.id), str(interaction.guild.id))
    if not playlist:
        playlist = db.get_public_playlist_by_name(name, str(interaction.guild.id))
    if not playlist:
        await interaction.response.send_message(f'❌ Playlist "{name}" not found!', ephemeral=True)
        return
    songs = db.get_songs(playlist["id"])
    if len(songs) == 0:
        await interaction.response.send_message(f'📋 Playlist **{name}** is empty!', ephemeral=True)
        return
    song_list = '\n'.join([f'{i+1}. **{s["title"]}** ({s["duration"] or ""})' for i, s in enumerate(songs[:10])])
    more = f'\n... and {len(songs) - 10} more songs' if len(songs) > 10 else ''
    await interaction.response.send_message(f'📋 Playlist **{name}** ({len(songs)} songs):\n{song_list}{more}', ephemeral=True)

@bot.tree.command(name='playlist-delete', description='Delete a playlist')
async def playlist_delete(interaction: discord.Interaction, name: str):
    playlist = db.get_playlist_by_name(name, str(interaction.user.id), str(interaction.guild.id))
    if not playlist:
        await interaction.response.send_message(f'❌ Playlist "{name}" not found!', ephemeral=True)
        return
    result = db.remove_playlist(playlist["id"], str(interaction.user.id))
    if result['success'] and result['deleted']:
        await interaction.response.send_message(f'✅ Deleted playlist **{name}**', ephemeral=True)
    else:
        await interaction.response.send_message('❌ Failed to delete playlist', ephemeral=True)

@bot.tree.command(name='public-playlist-create', description='Create a new public playlist (Music Guy only)')
async def public_playlist_create(interaction: discord.Interaction, name: str):
    if not has_music_guy_role(interaction.user):
        await interaction.response.send_message('❌ Only users with the "Music Guy" role can create public playlists!')
        return
    result = db.create_new_public_playlist(name, str(interaction.user.id), str(interaction.guild.id))
    if result['success']:
        await interaction.response.send_message(f'✅ Created public playlist: **{name}**')
    else:
        await interaction.response.send_message(f'❌ Failed to create public playlist: {result["error"]}')

@bot.tree.command(name='public-playlist-add', description='Add a song to a public playlist (Music Guy only)')
async def public_playlist_add(interaction: discord.Interaction, playlist: str, url: str):
    if not has_music_guy_role(interaction.user):
        await interaction.response.send_message('❌ Only users with the "Music Guy" role can edit public playlists!')
        return
    await interaction.response.defer()
    playlist_obj = db.get_public_playlist_by_name(playlist, str(interaction.guild.id))
    if not playlist_obj:
        await interaction.followup.send(f'❌ Public playlist "{playlist}" not found!')
        return
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'noplaylist': True}) as ydl:
        info = await asyncio.to_thread(ydl.extract_info, url, download=False)
        if info['duration'] > 600:
            await interaction.followup.send('Song is too long!')
            return
        result = db.add_song(playlist_obj["id"], url, info['title'], str(info.get('duration_string', '')))
        if result['success']:
            await interaction.followup.send(f'✅ Added **{info["title"]}** to public playlist **{playlist}**')
        else:
            await interaction.followup.send(f'❌ Failed to add song: {result["error"]}')

@bot.tree.command(name='public-playlist-delete', description='Delete a public playlist (Music Guy only)')
async def public_playlist_delete(interaction: discord.Interaction, name: str):
    if not has_music_guy_role(interaction.user):
        await interaction.response.send_message('❌ Only users with the "Music Guy" role can delete public playlists!')
        return
    playlist = db.get_public_playlist_by_name(name, str(interaction.guild.id))
    if not playlist:
        await interaction.response.send_message(f'❌ Public playlist "{name}" not found!')
        return
    result = db.remove_playlist(playlist["id"], str(interaction.user.id))
    if result['success'] and result['deleted']:
        await interaction.response.send_message(f'✅ Deleted public playlist **{name}**')
    else:
        await interaction.response.send_message('❌ Failed to delete public playlist')

@bot.tree.command(name='playlists-all', description='Show all available playlists (personal and public)')
async def playlists_all(interaction: discord.Interaction):
    personal = db.get_user_playlists_in_guild(str(interaction.user.id), str(interaction.guild.id))
    public = db.get_public_playlists_in_guild(str(interaction.guild.id))
    response = ''
    if personal:
        response += '📋 **Your Personal Playlists:**\n' + '\n'.join([f'• **{p["name"]}**' for p in personal]) + '\n\n'
    if public:
        response += '🌐 **Public Playlists:**\n' + '\n'.join([f'• **{p["name"]}**' for p in public])
    if not response:
        response = 'No playlists available in this server!'
    await interaction.response.send_message(response, ephemeral=True)

@bot.tree.command(name='playlist-remove', description='Remove a song from your playlist')
async def playlist_remove(interaction: discord.Interaction, playlist: str, position: int):
    playlist_obj = db.get_playlist_by_name(playlist, str(interaction.user.id), str(interaction.guild.id))
    if not playlist_obj:
        await interaction.response.send_message(f'❌ Playlist "{playlist}" not found!', ephemeral=True)
        return
    songs = db.get_songs(playlist_obj["id"])
    if position < 1 or position > len(songs):
        await interaction.response.send_message(f'❌ Invalid position! Choose between 1 and {len(songs)}.', ephemeral=True)
        return
    song = songs[position - 1]
    result = db.remove_song_from_playlist(playlist_obj["id"], song["id"])
    if result['success']:
        await interaction.response.send_message(f'✅ Removed **{song["title"]}** from playlist **{playlist}**', ephemeral=True)
    else:
        await interaction.response.send_message('❌ Failed to remove song from playlist', ephemeral=True)

@bot.tree.command(name='playlist-move', description='Move a song to a different position in your playlist')
async def playlist_move(interaction: discord.Interaction, playlist: str, from_pos: int, to_pos: int):
    playlist_obj = db.get_playlist_by_name(playlist, str(interaction.user.id), str(interaction.guild.id))
    if not playlist_obj:
        await interaction.response.send_message(f'❌ Playlist "{playlist}" not found!', ephemeral=True)
        return
    songs = db.get_songs(playlist_obj["id"])
    if from_pos < 1 or from_pos > len(songs) or to_pos < 1 or to_pos > len(songs):
        await interaction.response.send_message(f'❌ Invalid position! Choose between 1 and {len(songs)}.', ephemeral=True)
        return
    if from_pos == to_pos:
        await interaction.response.send_message('❌ Song is already at that position!', ephemeral=True)
        return
    result = db.move_song_in_playlist(playlist_obj["id"], from_pos, to_pos)
    if result['success']:
        await interaction.response.send_message(f'✅ Moved song from position {from_pos} to {to_pos} in playlist **{playlist}**', ephemeral=True)
    else:
        await interaction.response.send_message('❌ Failed to move song in playlist', ephemeral=True)

@bot.tree.command(name='public-playlist-remove', description='Remove a song from a public playlist (Music Guy only)')
async def public_playlist_remove(interaction: discord.Interaction, playlist: str, position: int):
    if not has_music_guy_role(interaction.user):
        await interaction.response.send_message('❌ Only users with the "Music Guy" role can edit public playlists!')
        return
    playlist_obj = db.get_public_playlist_by_name(playlist, str(interaction.guild.id))
    if not playlist_obj:
        await interaction.response.send_message(f'❌ Public playlist "{playlist}" not found!')
        return
    songs = db.get_songs(playlist_obj["id"])
    if position < 1 or position > len(songs):
        await interaction.response.send_message(f'❌ Invalid position! Choose between 1 and {len(songs)}.')
        return
    song = songs[position - 1]
    result = db.remove_song_from_playlist(playlist_obj["id"], song["id"])
    if result['success']:
        await interaction.response.send_message(f'✅ Removed **{song["title"]}** from public playlist **{playlist}**')
    else:
        await interaction.response.send_message('❌ Failed to remove song from public playlist')

@bot.tree.command(name='public-playlist-move', description='Move a song in a public playlist (Music Guy only)')
async def public_playlist_move(interaction: discord.Interaction, playlist: str, from_pos: int, to_pos: int):
    if not has_music_guy_role(interaction.user):
        await interaction.response.send_message('❌ Only users with the "Music Guy" role can edit public playlists!')
        return
    playlist_obj = db.get_public_playlist_by_name(playlist, str(interaction.guild.id))
    if not playlist_obj:
        await interaction.response.send_message(f'❌ Public playlist "{playlist}" not found!')
        return
    songs = db.get_songs(playlist_obj["id"])
    if from_pos < 1 or from_pos > len(songs) or to_pos < 1 or to_pos > len(songs):
        await interaction.response.send_message(f'❌ Invalid position! Choose between 1 and {len(songs)}.')
        return
    if from_pos == to_pos:
        await interaction.response.send_message('❌ Song is already at that position!')
        return
    result = db.move_song_in_playlist(playlist_obj["id"], from_pos, to_pos)
    if result['success']:
        await interaction.response.send_message(f'✅ Moved song from position {from_pos} to {to_pos} in public playlist **{playlist}**')
    else:
        await interaction.response.send_message('❌ Failed to move song in public playlist')

@bot.tree.command(name='playlist-shuffle', description='Shuffle the order of songs in your playlist')
async def playlist_shuffle(interaction: discord.Interaction, playlist: str):
    playlist_obj = db.get_playlist_by_name(playlist, str(interaction.user.id), str(interaction.guild.id))
    if not playlist_obj:
        await interaction.response.send_message(f'❌ Playlist "{playlist}" not found!', ephemeral=True)
        return
    songs = db.get_songs(playlist_obj["id"])
    if len(songs) < 2:
        await interaction.response.send_message('❌ Playlist needs at least 2 songs to shuffle!', ephemeral=True)
        return
    result = db.shuffle_playlist(playlist_obj["id"])
    if result['success']:
        await interaction.response.send_message(f'✅ Shuffled playlist **{playlist}** ({len(songs)} songs)', ephemeral=True)
    else:
        await interaction.response.send_message('❌ Failed to shuffle playlist', ephemeral=True)

@bot.tree.command(name='public-playlist-shuffle', description='Shuffle the order of songs in a public playlist (Music Guy only)')
async def public_playlist_shuffle(interaction: discord.Interaction, playlist: str):
    if not has_music_guy_role(interaction.user):
        await interaction.response.send_message('❌ Only users with the "Music Guy" role can edit public playlists!')
        return
    playlist_obj = db.get_public_playlist_by_name(playlist, str(interaction.guild.id))
    if not playlist_obj:
        await interaction.response.send_message(f'❌ Public playlist "{playlist}" not found!')
        return
    songs = db.get_songs(playlist_obj["id"])
    if len(songs) < 2:
        await interaction.response.send_message('❌ Playlist needs at least 2 songs to shuffle!')
        return
    result = db.shuffle_playlist(playlist_obj["id"])
    if result['success']:
        await interaction.response.send_message(f'✅ Shuffled public playlist **{playlist}** ({len(songs)} songs)')
    else:
        await interaction.response.send_message('❌ Failed to shuffle public playlist')

async def play_next_song(guild_id, vc):
    queue = queues.get(guild_id)
    if not queue:
        return
    song = queue.pop(0)
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'ffmpeg_location': 'ffmpeg',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = await asyncio.to_thread(ydl.extract_info, song['url'], download=False)
            audio_url = info['url']
        except Exception as e:
            print(f"Failed to extract audio URL for {song['url']}: {e}")
            if queues.get(guild_id):
                await play_next_song(guild_id, vc)
            return
    # Stream directly instead of downloading to temp file
    source = discord.FFmpegPCMAudio(audio_url)
    vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(guild_id, vc), bot.loop) if queues.get(guild_id) else None)

@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user and before.channel and not after.channel:
        # Bot was disconnected, attempt to reconnect after 5 seconds
        await asyncio.sleep(5)
        guild = member.guild
        if guild.id in connections:
            try:
                vc = await before.channel.connect()
                connections[guild.id] = vc
                print(f"Reconnected to {before.channel.name} in {guild.name}")
            except Exception as e:
                print(f"Failed to reconnect: {e}")

def has_music_guy_role(member):
    return any(role.name == 'Music Guy' for role in member.roles)

bot.run(os.getenv('DISCORD_TOKEN'))