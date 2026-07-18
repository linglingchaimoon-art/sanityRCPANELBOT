# Sanity2X Bot Clean Build

This is a clean standalone version with:

- `/link`
- `/linked`
- `/lookup`
- `/forceunlink`
- `/testreward`
- `/boosterpanel`
- `/loa`
- `/loastatus`
- `/botstatus`
- SQLite database
- RCON mock mode
- Railway support

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 main.py
```

## Important

Do not copy files from your old bot into this folder.

Fill in `.env` from scratch.

Enable Server Members Intent in Discord Developer Portal.

Bot permissions:

- Manage Roles
- Manage Nicknames
- View Channels
- Send Messages
- Embed Links
- Use Application Commands

Keep this while testing:

```env
RCON_MOCK_COMMANDS=true
```

## Railway

Use:

```text
python main.py
```

as the start command.

For persistent SQLite storage, attach a Railway volume to `/app/data` and set:

```env
DATABASE_PATH=/app/data/sanity2x.db
```
