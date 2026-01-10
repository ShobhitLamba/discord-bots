# Discord YouTube Player Bot

> **Note:** This README currently documents the YouTube Player Bot. As more bots are added to this repository, this documentation will be updated to include setup and usage instructions for all bots.

A Discord bot that plays YouTube audio in voice channels. Simply mention the bot with a YouTube link, and it will join your voice channel and play the audio. Includes both traditional prefix commands and modern slash commands.

## Features

- 🎵 Play YouTube audio in voice channels by mentioning the bot with a link
- ⏸️ Pause, resume, and stop playback
- 👋 Leave voice channel on command
- 🔧 Support for both prefix commands (`!command`) and slash commands (`/command`)
- 🐳 Docker support for easy deployment
- ☸️ Kubernetes-ready with deployment manifests

## Bot Commands

### Playback Control

| Prefix Command | Slash Command | Description |
|----------------|---------------|-------------|
| `!pause` | `/pause` | Pause the current audio |
| `!resume` | `/resume` | Resume paused audio |
| `!stop` | `/stop` | Stop the current audio |
| `!leave` | `/leave` | Make the bot leave the voice channel |

### Playing Audio
Mention the bot with a YouTube URL to play audio:
```
@YourBot https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

## Prerequisites

### System Dependencies
- **Python 3.11+**
- **FFmpeg** - Audio processing
- **Opus** - Audio codec for Discord voice

### Python Libraries
- `discord.py==2.6.4` - Discord API wrapper
- `python-dotenv==1.2.1` - Environment variable management
- `yt-dlp==2025.12.8` - YouTube video/audio downloader
- `PyNaCl==1.6.2` - Voice support for Discord

## Installation & Setup

### 1. Install System Dependencies

#### macOS
```bash
brew install python@3.11 ffmpeg opus
```

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install python3.11 python3-pip ffmpeg libopus0 libopus-dev
```

#### Windows
1. Install Python from [python.org](https://www.python.org/downloads/)
2. Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
3. Download Opus from [opus-codec.org](https://opus-codec.org/downloads/)

### 2. Create Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to "Bot" section → Click "Add Bot"
4. Under "Privileged Gateway Intents", enable:
   - ✅ Message Content Intent
   - ✅ Server Members Intent (optional)
5. Click "Reset Token" and copy your bot token
6. Go to "OAuth2" → "URL Generator":
   - Select scopes: `bot`, `applications.commands`
   - Select bot permissions: `Send Messages`, `Connect`, `Speak`, `Use Voice Activity`
   - Copy the generated URL and invite the bot to your server

### 3. Clone Repository

```bash
git clone https://github.com/yourusername/discord-bots.git
cd discord-bots
```

### 4. Set Up Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# macOS/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### 5. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 6. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# .env
DISCORD_BOT_TOKEN='your-bot-token-here'
```

**Important:** Don't set `OPUS_PATH` - the bot will auto-detect it!

### 7. Run the Bot Locally

```bash
python yt_player_bot.py
```

You should see:
```
Bot is ready! Logged in as YourBot#1234
Synced 4 slash command(s)
```

## Docker Deployment

### Build Docker Image

```bash
docker build -t discord-yt-bot:latest .
```

### Run with Docker

```bash
docker run -d \
  --name discord-bot \
  -e DISCORD_BOT_TOKEN='your-bot-token-here' \
  discord-yt-bot:latest
```

### Check Logs

```bash
docker logs -f discord-bot
```

## Kubernetes Deployment

### Prerequisites
- Docker Desktop with Kubernetes enabled, OR
- Minikube installed: `brew install minikube`
- kubectl installed: `brew install kubectl`

### 1. Create Kubernetes Secret from .env

```bash
# Load token from .env file
source .env

# Create secret in Kubernetes
kubectl delete secret discord-bot-secrets 2>/dev/null || true
kubectl create secret generic discord-bot-secrets \
  --from-literal=DISCORD_BOT_TOKEN="$DISCORD_BOT_TOKEN"
```

### 2. Build and Load Docker Image

#### For Docker Desktop Kubernetes:
```bash
docker build -t discord-yt-bot:latest .
# Image is automatically available to Kubernetes
```

#### For Minikube:
```bash
# Start minikube
minikube start

# Build image
docker build -t discord-yt-bot:latest .

# Load image into minikube
minikube image load discord-yt-bot:latest
```

#### For kind:
```bash
# Create cluster
kind create cluster

# Build image
docker build -t discord-yt-bot:latest .

# Load image into kind
kind load docker-image discord-yt-bot:latest
```

### 3. Deploy to Kubernetes

```bash
kubectl apply -f kubernetes-deployment.yaml
```

### 4. Verify Deployment

```bash
# Check pod status
kubectl get pods

# View logs
kubectl logs -f -l app=discord-yt-bot

# Check deployment
kubectl get deployment discord-yt-bot
```

Expected output:
```
Bot is ready! Logged in as YourBot#1234
Synced 4 slash command(s)
```

### 5. Update Bot (after code changes)

```bash
# Rebuild image
docker build -t discord-yt-bot:latest .

# For minikube, reload image
minikube image load discord-yt-bot:latest

# Restart deployment
kubectl rollout restart deployment/discord-yt-bot
```

### 6. Manage Deployment

```bash
# Scale replicas (use 1 for Discord bot)
kubectl scale deployment discord-yt-bot --replicas=1

# Delete deployment
kubectl delete -f kubernetes-deployment.yaml

# Update secret
kubectl delete secret discord-bot-secrets
kubectl create secret generic discord-bot-secrets \
  --from-literal=DISCORD_BOT_TOKEN='your-new-token'
kubectl rollout restart deployment/discord-yt-bot
```

## Troubleshooting

### Bot Not Showing Online
- Verify bot token is correct
- Check logs: `kubectl logs -f -l app=discord-yt-bot`
- Ensure pod is running: `kubectl get pods`

### Slash Commands Not Appearing
- Wait 1-2 minutes after bot starts (Discord propagation delay)
- Try kicking and re-inviting the bot to your server
- Verify bot has `applications.commands` scope

### Voice Connection Issues
- Ensure FFmpeg and Opus are installed in the container
- Check bot has "Connect" and "Speak" permissions
- Verify you're in a voice channel when playing audio

### Build Failures
- Clean requirements.txt if you see local file path errors
- Only include essential packages: `discord.py`, `python-dotenv`, `yt-dlp`, `PyNaCl`

### Pod CrashLoopBackOff
```bash
# Check logs for error details
kubectl logs -l app=discord-yt-bot

# Common issues:
# - Invalid bot token
# - Missing dependencies
# - Network connectivity
```

## Project Structure

```
discord-bots/
├── yt_player_bot.py           # Main bot code
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker image configuration
├── .dockerignore              # Files to exclude from Docker image
├── kubernetes-deployment.yaml  # Kubernetes deployment manifest
├── .env                       # Local environment variables (not committed)
├── .gitignore                 # Git ignore rules
└── README.md                  # This file
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | ✅ Yes | Your Discord bot token from Developer Portal |
| `OPUS_PATH` | ❌ No | Path to opus library (auto-detected if not set) |

## Development

### Running Tests Locally

```bash
# Activate virtual environment
source venv/bin/activate

# Run bot
python yt_player_bot.py
```

### Updating Dependencies

```bash
pip install --upgrade discord.py yt-dlp PyNaCl
pip freeze > requirements.txt
```

## License

MIT License - See [LICENSE](LICENSE) file for details

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs: `kubectl logs -f -l app=discord-yt-bot`
3. Open an issue on GitHub

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

---

Made with ❤️ using discord.py
