# Instachatico

AI-powered Instagram comment management: automatic classification, media analysis and intelligent responses.

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env  # Edit with your credentials

# 2. Start services
cd docker && docker compose up -d
```

## System Setup

To avoid Redis warnings:
```bash
echo "vm.overcommit_memory = 1" | sudo tee -a /etc/sysctl.conf && sudo sysctl -p
cat /proc/sys/vm/overcommit_memory  # Should output: 1
```

## Required Credentials

Edit `.env` with:
- `OPENAI_API_KEY` - OpenAI API key
- `INSTA_TOKEN` - Instagram Graph API token
- `APP_SECRET` - Instagram app secret
- `TG_TOKEN`, `TG_CHAT_ID` - Telegram bot credentials
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` - S3 storage

