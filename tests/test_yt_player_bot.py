"""
tests/test_yt_player_bot.py

Comprehensive test suite for yt_player_bot.py.

All Discord API calls, voice-channel operations, and yt-dlp network calls are
mocked – no bot token or internet connection is required.

Quick reference
---------------
Run all tests:
    pytest

Verbose output:
    pytest -v

Single class:
    pytest tests/test_yt_player_bot.py::TestConfiguration -v

Keyword filter:
    pytest -k "regex or pause"

Coverage report (requires pytest-cov):
    pytest --cov=yt_player_bot --cov-report=term-missing
"""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# conftest.py has already injected the mock modules into sys.modules;
# importing the bot here will use those mocks instead of real Discord / yt-dlp.
import yt_player_bot as bot_module  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Shared helper factories
# ─────────────────────────────────────────────────────────────────────────────

def make_context(
    *,
    in_voice: bool = True,
    is_playing: bool = False,
    is_paused: bool = False,
) -> MagicMock:
    """Return a mock commands.Context configured for the requested state."""
    ctx = MagicMock()
    ctx.send = AsyncMock()
    if in_voice:
        vc = MagicMock()
        vc.is_playing.return_value = is_playing
        vc.is_paused.return_value = is_paused
        vc.disconnect = AsyncMock()
        ctx.voice_client = vc
    else:
        ctx.voice_client = None
    return ctx


def make_interaction(
    *,
    in_voice: bool = True,
    is_playing: bool = False,
    is_paused: bool = False,
) -> MagicMock:
    """Return a mock discord.Interaction configured for the requested state."""
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    if in_voice:
        vc = MagicMock()
        vc.is_playing.return_value = is_playing
        vc.is_paused.return_value = is_paused
        vc.disconnect = AsyncMock()
        interaction.guild.voice_client = vc
    else:
        interaction.guild.voice_client = None
    return interaction


# ─────────────────────────────────────────────────────────────────────────────
# 1. Configuration
# ─────────────────────────────────────────────────────────────────────────────

class TestConfiguration:
    """Validate YTDL_OPTIONS and FFMPEG_OPTIONS constants."""

    def test_ytdl_format_is_best_audio(self):
        assert bot_module.YTDL_OPTIONS["format"] == "bestaudio/best"

    def test_ytdl_quiet_mode_enabled(self):
        assert bot_module.YTDL_OPTIONS["quiet"] is True

    def test_ytdl_playlist_disabled(self):
        assert bot_module.YTDL_OPTIONS["noplaylist"] is True

    def test_ytdl_has_user_agent_header(self):
        assert "User-Agent" in bot_module.YTDL_OPTIONS["http_headers"]

    def test_ytdl_postprocessor_codec_is_opus(self):
        codecs = [
            pp.get("preferredcodec")
            for pp in bot_module.YTDL_OPTIONS.get("postprocessors", [])
        ]
        assert "opus" in codecs

    def test_ytdl_default_search_is_auto(self):
        assert bot_module.YTDL_OPTIONS["default_search"] == "auto"

    def test_ffmpeg_reconnect_flag_present(self):
        assert "-reconnect 1" in bot_module.FFMPEG_OPTIONS["before_options"]

    def test_ffmpeg_video_stream_disabled(self):
        assert "-vn" in bot_module.FFMPEG_OPTIONS["options"]

    def test_ffmpeg_bitrate_set_to_320k(self):
        assert "320k" in bot_module.FFMPEG_OPTIONS["options"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. YouTube URL regex
# ─────────────────────────────────────────────────────────────────────────────

# Mirror of the regex used in on_message
_YT_REGEX = r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+"


class TestYouTubeRegex:
    """Verify the regex pattern that detects YouTube URLs in messages."""

    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "http://www.youtube.com/watch?v=abc123",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtu.be/abc-123_XYZ",
    ])
    def test_valid_youtube_url_matches(self, url):
        assert re.findall(_YT_REGEX, url), f"Expected match for: {url}"

    @pytest.mark.parametrize("text", [
        "https://www.google.com",
        "https://vimeo.com/123456789",
        "not a url at all",
        "@Bot play some music",
        "https://youtu.be",          # missing video ID
    ])
    def test_non_youtube_text_does_not_match(self, text):
        assert not re.findall(_YT_REGEX, text), f"Unexpected match for: {text}"

    def test_extracts_url_embedded_in_mention_message(self):
        msg = "@Bot check this out https://www.youtube.com/watch?v=dQw4w9WgXcQ nice"
        matches = re.findall(_YT_REGEX, msg)
        assert len(matches) == 1
        assert "dQw4w9WgXcQ" in matches[0]

    def test_extracts_multiple_urls_from_one_message(self):
        msg = "https://www.youtube.com/watch?v=abc https://youtu.be/xyz"
        assert len(re.findall(_YT_REGEX, msg)) == 2

    def test_first_url_takes_priority(self):
        msg = "https://www.youtube.com/watch?v=FIRST https://youtu.be/SECOND"
        assert re.findall(_YT_REGEX, msg)[0] == "https://www.youtube.com/watch?v=FIRST"

    def test_youtu_be_short_link_matched(self):
        assert re.findall(_YT_REGEX, "https://youtu.be/shortCode123")

    def test_url_with_hyphens_and_underscores(self):
        assert re.findall(_YT_REGEX, "https://youtu.be/abc-DEF_123")


# ─────────────────────────────────────────────────────────────────────────────
# 3. YTDLSource
# ─────────────────────────────────────────────────────────────────────────────

class TestYTDLSource:
    """Unit tests for the YTDLSource audio-source wrapper."""

    def test_init_stores_title(self):
        src = bot_module.YTDLSource(MagicMock(), data={"title": "My Track", "url": "http://x"})
        assert src.title == "My Track"

    def test_init_stores_url(self):
        src = bot_module.YTDLSource(MagicMock(), data={"title": "T", "url": "http://audio"})
        assert src.url == "http://audio"

    def test_init_stores_full_data_dict(self):
        data = {"title": "T", "url": "U", "duration": 240}
        src = bot_module.YTDLSource(MagicMock(), data=data)
        assert src.data is data

    def test_default_volume_is_0_5(self):
        src = bot_module.YTDLSource(MagicMock(), data={})
        assert src.volume == 0.5

    def test_custom_volume_is_respected(self):
        src = bot_module.YTDLSource(MagicMock(), data={}, volume=0.8)
        assert src.volume == 0.8

    def test_missing_keys_default_to_none(self):
        src = bot_module.YTDLSource(MagicMock(), data={})
        assert src.title is None
        assert src.url is None

    async def test_from_url_returns_ytdlsource_instance(self):
        fake_data = {"title": "Stream Track", "url": "https://stream.example.com/audio.opus"}
        bot_module.ytdl.extract_info.return_value = fake_data

        result = await bot_module.YTDLSource.from_url("https://youtube.com/watch?v=test123")

        assert isinstance(result, bot_module.YTDLSource)
        assert result.title == "Stream Track"

    async def test_from_url_uses_first_playlist_entry(self):
        first = {"title": "First Video", "url": "https://stream.example.com/first"}
        fake_data = {"entries": [first, {"title": "Second", "url": "https://stream.example.com/second"}]}
        bot_module.ytdl.extract_info.return_value = fake_data

        result = await bot_module.YTDLSource.from_url("https://youtube.com/watch?v=pl123")

        assert result.title == "First Video"

    async def test_from_url_calls_extract_info_with_stream_false_download(self):
        fake_data = {"title": "T", "url": "http://u"}
        bot_module.ytdl.extract_info.return_value = fake_data

        await bot_module.YTDLSource.from_url("https://youtube.com/watch?v=x", stream=True)

        bot_module.ytdl.extract_info.assert_called_with(
            "https://youtube.com/watch?v=x", download=False
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. on_ready
# ─────────────────────────────────────────────────────────────────────────────

class TestOnReady:
    async def test_syncs_slash_commands_on_startup(self):
        bot_module.bot.tree.sync = AsyncMock(return_value=[MagicMock()] * 4)
        bot_module.bot.user = MagicMock()

        await bot_module.on_ready()

        bot_module.bot.tree.sync.assert_awaited_once()

    async def test_does_not_raise_when_sync_fails(self):
        bot_module.bot.tree.sync = AsyncMock(side_effect=Exception("Discord outage"))
        bot_module.bot.user = MagicMock()

        # Must complete without propagating the exception
        await bot_module.on_ready()


# ─────────────────────────────────────────────────────────────────────────────
# 5. on_message
# ─────────────────────────────────────────────────────────────────────────────

class TestOnMessage:
    """Tests for the core message handler that drives YouTube playback."""

    # ── shared setup helpers ──────────────────────────────────────────────────

    def _setup_bot(self):
        """Configure bot.user and return it; also wires up process_commands."""
        user = MagicMock(name="BotUser")
        bot_module.bot.user = user
        bot_module.bot.process_commands = AsyncMock()
        bot_module.bot.loop = asyncio.get_event_loop()
        return user

    def _make_message(
        self,
        bot_user,
        *,
        content: str = "",
        in_voice: bool = True,
        guild_vc=None,
        mentions_bot: bool = True,
        author_is_bot: bool = False,
    ):
        """
        Return (msg, user_voice_channel).
        guild_vc  – what message.guild.voice_client starts as (None = not connected).
        """
        vc_channel = MagicMock(name="UserVoiceChannel")
        author = bot_user if author_is_bot else MagicMock(name="HumanAuthor")
        author.voice = MagicMock(channel=vc_channel) if in_voice else None

        msg = MagicMock()
        msg.author = author
        msg.content = content
        msg.mentions = [bot_user] if mentions_bot else []
        msg.guild = MagicMock()
        msg.guild.voice_client = guild_vc
        msg.channel.send = AsyncMock()
        return msg, vc_channel

    # ── identity / guard tests ────────────────────────────────────────────────

    async def test_ignores_own_messages(self):
        bot_user = self._setup_bot()
        msg, _ = self._make_message(bot_user, author_is_bot=True)

        await bot_module.on_message(msg)

        msg.channel.send.assert_not_called()

    async def test_no_action_when_bot_is_not_mentioned(self):
        bot_user = self._setup_bot()
        msg, _ = self._make_message(
            bot_user,
            content="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mentions_bot=False,
        )

        with patch.object(bot_module.YTDLSource, "from_url", new_callable=AsyncMock) as m:
            await bot_module.on_message(msg)
            m.assert_not_called()

    async def test_no_action_for_non_youtube_link(self):
        bot_user = self._setup_bot()
        msg, _ = self._make_message(bot_user, content="https://vimeo.com/12345")

        with patch.object(bot_module.YTDLSource, "from_url", new_callable=AsyncMock) as m:
            await bot_module.on_message(msg)
            m.assert_not_called()

    async def test_process_commands_always_called(self):
        """prefix commands must still work when the bot is not triggered by a YT link."""
        bot_user = self._setup_bot()
        msg, _ = self._make_message(bot_user, mentions_bot=False)

        await bot_module.on_message(msg)

        bot_module.bot.process_commands.assert_awaited_once_with(msg)

    # ── voice-channel guard ───────────────────────────────────────────────────

    async def test_error_when_user_not_in_voice_channel(self):
        bot_user = self._setup_bot()
        msg, _ = self._make_message(
            bot_user,
            content="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            in_voice=False,
        )

        await bot_module.on_message(msg)

        sends = [str(c.args[0]) for c in msg.channel.send.call_args_list if c.args]
        assert any("❌" in s for s in sends)

    # ── bot joins / moves ─────────────────────────────────────────────────────

    async def test_connects_to_voice_channel_when_not_yet_joined(self):
        bot_user = self._setup_bot()

        # Prepare a voice client that gets "attached" once connect() is awaited.
        mock_vc = MagicMock(name="NewVC")
        mock_vc.is_playing.return_value = False
        mock_vc.play = MagicMock()

        msg, vc_channel = self._make_message(
            bot_user,
            content="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            guild_vc=None,
        )

        async def _connect():
            msg.guild.voice_client = mock_vc

        vc_channel.connect = AsyncMock(side_effect=_connect)

        fake_player = MagicMock(title="Joined Track")
        with patch.object(bot_module.YTDLSource, "from_url", AsyncMock(return_value=fake_player)):
            await bot_module.on_message(msg)

        vc_channel.connect.assert_awaited_once()

    async def test_moves_to_users_voice_channel_when_in_different_one(self):
        bot_user = self._setup_bot()

        other_channel = MagicMock(name="OtherChannel")
        existing_vc = MagicMock(name="ExistingVC")
        existing_vc.channel = other_channel   # bot is in a DIFFERENT channel
        existing_vc.is_playing.return_value = False
        existing_vc.move_to = AsyncMock()
        existing_vc.play = MagicMock()

        msg, user_vc_channel = self._make_message(
            bot_user,
            content="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            guild_vc=existing_vc,
        )

        fake_player = MagicMock(title="Moved Track")
        with patch.object(bot_module.YTDLSource, "from_url", AsyncMock(return_value=fake_player)):
            await bot_module.on_message(msg)

        existing_vc.move_to.assert_awaited_once_with(user_vc_channel)

    # ── playback control ──────────────────────────────────────────────────────

    async def test_stops_current_audio_before_starting_new_track(self):
        bot_user = self._setup_bot()

        voice_channel = MagicMock(name="VC")
        existing_vc = MagicMock(name="PlayingVC")
        existing_vc.channel = voice_channel
        existing_vc.is_playing.return_value = True   # already playing
        existing_vc.stop = MagicMock()
        existing_vc.play = MagicMock()

        msg, _ = self._make_message(
            bot_user,
            content="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            guild_vc=existing_vc,
        )
        msg.author.voice.channel = voice_channel

        fake_player = MagicMock(title="New Track")
        with patch.object(bot_module.YTDLSource, "from_url", AsyncMock(return_value=fake_player)):
            await bot_module.on_message(msg)

        existing_vc.stop.assert_called_once()

    async def test_sends_now_playing_message_with_track_title(self):
        bot_user = self._setup_bot()

        voice_channel = MagicMock(name="VC")
        existing_vc = MagicMock()
        existing_vc.channel = voice_channel
        existing_vc.is_playing.return_value = False
        existing_vc.play = MagicMock()

        msg, _ = self._make_message(
            bot_user,
            content="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            guild_vc=existing_vc,
        )
        msg.author.voice.channel = voice_channel

        fake_player = MagicMock(title="Never Gonna Give You Up")
        with patch.object(bot_module.YTDLSource, "from_url", AsyncMock(return_value=fake_player)):
            await bot_module.on_message(msg)

        sends = [str(c.args[0]) for c in msg.channel.send.call_args_list if c.args]
        assert any("Never Gonna Give You Up" in s for s in sends)

    async def test_sends_error_message_when_ytdl_extraction_fails(self):
        bot_user = self._setup_bot()

        voice_channel = MagicMock(name="VC")
        existing_vc = MagicMock()
        existing_vc.channel = voice_channel
        existing_vc.is_playing.return_value = False

        msg, _ = self._make_message(
            bot_user,
            content="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            guild_vc=existing_vc,
        )
        msg.author.voice.channel = voice_channel

        with patch.object(
            bot_module.YTDLSource, "from_url",
            AsyncMock(side_effect=Exception("Extraction failed")),
        ):
            await bot_module.on_message(msg)

        sends = [str(c.args[0]) for c in msg.channel.send.call_args_list if c.args]
        assert any("❌" in s for s in sends)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Prefix commands
# ─────────────────────────────────────────────────────────────────────────────

class TestLeaveCommand:
    async def test_disconnects_from_voice_channel(self):
        ctx = make_context(in_voice=True)
        await bot_module.leave(ctx)
        ctx.voice_client.disconnect.assert_awaited_once()

    async def test_sends_confirmation_message(self):
        ctx = make_context(in_voice=True)
        await bot_module.leave(ctx)
        sent = ctx.send.call_args[0][0]
        assert "👋" in sent or "left" in sent.lower()

    async def test_sends_error_when_not_in_voice_channel(self):
        ctx = make_context(in_voice=False)
        await bot_module.leave(ctx)
        sent = ctx.send.call_args[0][0]
        assert "❌" in sent


class TestPauseCommand:
    async def test_pauses_audio_when_playing(self):
        ctx = make_context(in_voice=True, is_playing=True)
        await bot_module.pause(ctx)
        ctx.voice_client.pause.assert_called_once()

    async def test_sends_confirmation_on_pause(self):
        ctx = make_context(in_voice=True, is_playing=True)
        await bot_module.pause(ctx)
        sent = ctx.send.call_args[0][0]
        assert "⏸️" in sent or "paused" in sent.lower()

    async def test_sends_error_when_nothing_is_playing(self):
        ctx = make_context(in_voice=True, is_playing=False)
        await bot_module.pause(ctx)
        ctx.voice_client.pause.assert_not_called()
        sent = ctx.send.call_args[0][0]
        assert "❌" in sent

    async def test_sends_error_when_not_in_voice_channel(self):
        ctx = make_context(in_voice=False)
        await bot_module.pause(ctx)
        sent = ctx.send.call_args[0][0]
        assert "❌" in sent


class TestResumeCommand:
    async def test_resumes_audio_when_paused(self):
        ctx = make_context(in_voice=True, is_paused=True)
        await bot_module.resume(ctx)
        ctx.voice_client.resume.assert_called_once()

    async def test_sends_confirmation_on_resume(self):
        ctx = make_context(in_voice=True, is_paused=True)
        await bot_module.resume(ctx)
        sent = ctx.send.call_args[0][0]
        assert "▶️" in sent or "resumed" in sent.lower()

    async def test_sends_error_when_nothing_is_paused(self):
        ctx = make_context(in_voice=True, is_paused=False)
        await bot_module.resume(ctx)
        ctx.voice_client.resume.assert_not_called()
        sent = ctx.send.call_args[0][0]
        assert "❌" in sent

    async def test_sends_error_when_not_in_voice_channel(self):
        ctx = make_context(in_voice=False)
        await bot_module.resume(ctx)
        sent = ctx.send.call_args[0][0]
        assert "❌" in sent


class TestStopCommand:
    async def test_stops_audio_when_playing(self):
        ctx = make_context(in_voice=True, is_playing=True)
        await bot_module.stop(ctx)
        ctx.voice_client.stop.assert_called_once()

    async def test_sends_confirmation_on_stop(self):
        ctx = make_context(in_voice=True, is_playing=True)
        await bot_module.stop(ctx)
        sent = ctx.send.call_args[0][0]
        assert "⏹️" in sent or "stopped" in sent.lower()

    async def test_sends_error_when_nothing_is_playing(self):
        ctx = make_context(in_voice=True, is_playing=False)
        await bot_module.stop(ctx)
        ctx.voice_client.stop.assert_not_called()
        sent = ctx.send.call_args[0][0]
        assert "❌" in sent

    async def test_sends_error_when_not_in_voice_channel(self):
        ctx = make_context(in_voice=False)
        await bot_module.stop(ctx)
        sent = ctx.send.call_args[0][0]
        assert "❌" in sent


# ─────────────────────────────────────────────────────────────────────────────
# 7. Slash commands
# ─────────────────────────────────────────────────────────────────────────────

class TestLeaveSlash:
    async def test_disconnects_from_voice_channel(self):
        interaction = make_interaction(in_voice=True)
        await bot_module.leave_slash(interaction)
        interaction.guild.voice_client.disconnect.assert_awaited_once()

    async def test_sends_confirmation_message(self):
        interaction = make_interaction(in_voice=True)
        await bot_module.leave_slash(interaction)
        sent = interaction.response.send_message.call_args[0][0]
        assert "👋" in sent or "left" in sent.lower()

    async def test_sends_error_when_not_in_voice_channel(self):
        interaction = make_interaction(in_voice=False)
        await bot_module.leave_slash(interaction)
        sent = interaction.response.send_message.call_args[0][0]
        assert "❌" in sent


class TestPauseSlash:
    async def test_pauses_audio_when_playing(self):
        interaction = make_interaction(in_voice=True, is_playing=True)
        await bot_module.pause_slash(interaction)
        interaction.guild.voice_client.pause.assert_called_once()

    async def test_sends_confirmation_on_pause(self):
        interaction = make_interaction(in_voice=True, is_playing=True)
        await bot_module.pause_slash(interaction)
        sent = interaction.response.send_message.call_args[0][0]
        assert "⏸️" in sent or "paused" in sent.lower()

    async def test_sends_error_when_nothing_is_playing(self):
        interaction = make_interaction(in_voice=True, is_playing=False)
        await bot_module.pause_slash(interaction)
        interaction.guild.voice_client.pause.assert_not_called()
        sent = interaction.response.send_message.call_args[0][0]
        assert "❌" in sent

    async def test_sends_error_when_not_in_voice_channel(self):
        interaction = make_interaction(in_voice=False)
        await bot_module.pause_slash(interaction)
        sent = interaction.response.send_message.call_args[0][0]
        assert "❌" in sent


class TestResumeSlash:
    async def test_resumes_audio_when_paused(self):
        interaction = make_interaction(in_voice=True, is_paused=True)
        await bot_module.resume_slash(interaction)
        interaction.guild.voice_client.resume.assert_called_once()

    async def test_sends_confirmation_on_resume(self):
        interaction = make_interaction(in_voice=True, is_paused=True)
        await bot_module.resume_slash(interaction)
        sent = interaction.response.send_message.call_args[0][0]
        assert "▶️" in sent or "resumed" in sent.lower()

    async def test_sends_error_when_nothing_is_paused(self):
        interaction = make_interaction(in_voice=True, is_paused=False)
        await bot_module.resume_slash(interaction)
        interaction.guild.voice_client.resume.assert_not_called()
        sent = interaction.response.send_message.call_args[0][0]
        assert "❌" in sent

    async def test_sends_error_when_not_in_voice_channel(self):
        interaction = make_interaction(in_voice=False)
        await bot_module.resume_slash(interaction)
        sent = interaction.response.send_message.call_args[0][0]
        assert "❌" in sent


class TestStopSlash:
    async def test_stops_audio_when_playing(self):
        interaction = make_interaction(in_voice=True, is_playing=True)
        await bot_module.stop_slash(interaction)
        interaction.guild.voice_client.stop.assert_called_once()

    async def test_sends_confirmation_on_stop(self):
        interaction = make_interaction(in_voice=True, is_playing=True)
        await bot_module.stop_slash(interaction)
        sent = interaction.response.send_message.call_args[0][0]
        assert "⏹️" in sent or "stopped" in sent.lower()

    async def test_sends_error_when_nothing_is_playing(self):
        interaction = make_interaction(in_voice=True, is_playing=False)
        await bot_module.stop_slash(interaction)
        interaction.guild.voice_client.stop.assert_not_called()
        sent = interaction.response.send_message.call_args[0][0]
        assert "❌" in sent

    async def test_sends_error_when_not_in_voice_channel(self):
        interaction = make_interaction(in_voice=False)
        await bot_module.stop_slash(interaction)
        sent = interaction.response.send_message.call_args[0][0]
        assert "❌" in sent
