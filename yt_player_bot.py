from json import load
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import re
from dotenv import load_dotenv
import os

load_dotenv()

# Load opus library - let discord.py auto-detect or use env variable
opus_path = os.getenv('OPUS_PATH')
if opus_path:
    discord.opus.load_opus(opus_path)

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# yt-dlp options for audio extraction
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
        'preferredquality': '320',
    }],
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 320k'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)


@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} slash command(s)')
    except Exception as e:
        print(f'Failed to sync commands: {e}')


@bot.event
async def on_message(message):
    # Ignore bot's own messages
    if message.author == bot.user:
        return

    # Check if bot is mentioned and message contains YouTube link
    if bot.user in message.mentions:
        youtube_regex = r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+'
        youtube_links = re.findall(youtube_regex, message.content)

        if youtube_links:
            # Use the matched URL directly
            youtube_url = youtube_links[0]
            
            # Check if user is in a voice channel
            if message.author.voice is None:
                await message.channel.send("❌ You need to be in a voice channel!")
                return

            voice_channel = message.author.voice.channel

            # Join voice channel if not already connected
            if message.guild.voice_client is None:
                await voice_channel.connect()
                await message.channel.send(f"🎵 Joined {voice_channel.name}")
            elif message.guild.voice_client.channel != voice_channel:
                await message.guild.voice_client.move_to(voice_channel)

            voice_client = message.guild.voice_client

            # Stop current playback if any
            if voice_client.is_playing():
                voice_client.stop()

            try:
                await message.channel.send("⏳ Loading audio from YouTube...")
                player = await YTDLSource.from_url(youtube_url, loop=bot.loop, stream=True)
                
                def after_playing(error):
                    if error:
                        print(f'Player error: {error}')
                        asyncio.run_coroutine_threadsafe(
                            message.channel.send(f"❌ Playback error: {error}"),
                            bot.loop
                        )
                    # Disconnect after playback finishes
                    asyncio.run_coroutine_threadsafe(
                        voice_client.disconnect(),
                        bot.loop
                    )
                
                voice_client.play(player, after=after_playing)
                await message.channel.send(f"🎶 Now playing: **{player.title}**")
            except Exception as e:
                print(f"Error details: {type(e).__name__}: {str(e)}")
                await message.channel.send(f"❌ Error playing audio: {type(e).__name__}: {str(e)}")

    # Process other commands
    await bot.process_commands(message)


@bot.command(name='leave')
async def leave(ctx):
    """Make the bot leave the voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Left the voice channel")
    else:
        await ctx.send("❌ I'm not in a voice channel")


@bot.command(name='pause')
async def pause(ctx):
    """Pause the current audio"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused")
    else:
        await ctx.send("❌ Nothing is playing")


@bot.command(name='resume')
async def resume(ctx):
    """Resume paused audio"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed")
    else:
        await ctx.send("❌ Nothing is paused")


@bot.command(name='stop')
async def stop(ctx):
    """Stop the current audio"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏹️ Stopped")
    else:
        await ctx.send("❌ Nothing is playing")


# Slash commands
@bot.tree.command(name='leave', description='Make the bot leave the voice channel')
async def leave_slash(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 Left the voice channel")
    else:
        await interaction.response.send_message("❌ I'm not in a voice channel")


@bot.tree.command(name='pause', description='Pause the current audio')
async def pause_slash(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.pause()
        await interaction.response.send_message("⏸️ Paused")
    else:
        await interaction.response.send_message("❌ Nothing is playing")


@bot.tree.command(name='resume', description='Resume paused audio')
async def resume_slash(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
        interaction.guild.voice_client.resume()
        await interaction.response.send_message("▶️ Resumed")
    else:
        await interaction.response.send_message("❌ Nothing is paused")


@bot.tree.command(name='stop', description='Stop the current audio')
async def stop_slash(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏹️ Stopped")
    else:
        await interaction.response.send_message("❌ Nothing is playing")


# Replace 'YOUR_BOT_TOKEN_HERE' with your actual bot token
if __name__ == '__main__':
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    
    if not DISCORD_BOT_TOKEN:
        print("Error: DISCORD_BOT_TOKEN environment variable not set")
        print("\nTo set your token:")
        print("  export DISCORD_BOT_TOKEN='your-token-here'")
        print("\nOr create a .env file with:")
        print("  DISCORD_BOT_TOKEN=your-token-here")
        sys.exit(1)
    
    bot.run(DISCORD_BOT_TOKEN)
