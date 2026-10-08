"""
conftest.py – pytest session-wide setup.

Injects lightweight mocks for `discord` and `yt_dlp` into sys.modules *before*
any test file imports yt_player_bot.  This prevents the bot from attempting a
real Discord connection or network call during tests.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Provide a dummy token so the bot module doesn't sys.exit() at import time.
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token-placeholder")


# ── discord.PCMVolumeTransformer substitute ───────────────────────────────────

class _FakePCMVolumeTransformer:
    """Minimal stand-in for discord.PCMVolumeTransformer (YTDLSource base class)."""

    def __init__(self, source, volume: float = 0.5):
        self.source = source
        self.volume = volume


# ── Identity decorator factory ────────────────────────────────────────────────

def _identity_decorator(*args, **kwargs):
    """
    Works as both a bare decorator (@bot.event) and a factory decorator
    (@bot.command(name='leave')), returning the original coroutine unchanged
    so that bot_module.leave / on_message / etc. remain callable functions.
    """
    if len(args) == 1 and callable(args[0]):
        return args[0]

    def _wrap(func):
        return func

    return _wrap


# ── discord mock ──────────────────────────────────────────────────────────────

_discord_mock = MagicMock(name="discord")
_discord_mock.PCMVolumeTransformer = _FakePCMVolumeTransformer
_discord_mock.Intents.default.return_value = MagicMock()
_discord_mock.opus = MagicMock()
_discord_mock.FFmpegPCMAudio = MagicMock()

# ── discord.ext.commands mock ─────────────────────────────────────────────────

_mock_bot = MagicMock(name="bot_instance")
_mock_bot.event = _identity_decorator
_mock_bot.command = _identity_decorator
_mock_bot.tree = MagicMock()
_mock_bot.tree.command = _identity_decorator

_commands_mock = MagicMock(name="commands")
_commands_mock.Bot.return_value = _mock_bot

# ── yt_dlp mock ───────────────────────────────────────────────────────────────

ytdl_mock_instance = MagicMock(name="ytdl")
_yt_dlp_mock = MagicMock(name="yt_dlp")
_yt_dlp_mock.YoutubeDL.return_value = ytdl_mock_instance

# ── discord.ext mock (must expose .commands so `from discord.ext import commands` resolves) ──

_discord_ext_mock = MagicMock(name="discord.ext")
_discord_ext_mock.commands = _commands_mock   # critical: attribute lookup path

# ── Inject all mocks before any test module can import the bot ────────────────
# Use direct assignment (not setdefault) so these take precedence even if
# something else already touched sys.modules during collection.

sys.modules["discord"] = _discord_mock
sys.modules["discord.ext"] = _discord_ext_mock
sys.modules["discord.ext.commands"] = _commands_mock
sys.modules["discord.app_commands"] = MagicMock(name="discord.app_commands")
sys.modules["yt_dlp"] = _yt_dlp_mock
