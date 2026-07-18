from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from config import DATABASE_PATH


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_database() -> None:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS links (
                discord_id INTEGER PRIMARY KEY,
                discord_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                gamertag TEXT NOT NULL COLLATE NOCASE UNIQUE,
                linked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vip_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                gamertag TEXT NOT NULL,
                package TEXT NOT NULL,
                trigger_phrase TEXT NOT NULL,
                success INTEGER NOT NULL,
                detail TEXT,
                claimed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS loa_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                discord_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                extra_information TEXT,
                status TEXT NOT NULL,
                review_channel_id INTEGER,
                review_message_id INTEGER,
                reviewed_by_id INTEGER,
                reviewed_by_name TEXT,
                review_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_vip_claims_player_time
            ON vip_claims(gamertag, claimed_at);

            CREATE INDEX IF NOT EXISTS idx_loa_user_status
            ON loa_requests(discord_id, status);
            """
        )

        await db.commit()


async def save_link(
    discord_id: int,
    discord_name: str,
    platform: str,
    gamertag: str,
) -> None:
    gamertag = " ".join(gamertag.strip().split())

    if not gamertag:
        raise ValueError("Enter a valid gamertag.")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT gamertag FROM links WHERE discord_id = ?",
            (discord_id,),
        )
        existing_user = await cursor.fetchone()

        if existing_user:
            raise ValueError(f"You are already linked to {existing_user[0]}.")

        cursor = await db.execute(
            "SELECT discord_id FROM links WHERE gamertag = ? COLLATE NOCASE",
            (gamertag,),
        )
        existing_gamertag = await cursor.fetchone()

        if existing_gamertag:
            raise ValueError("That gamertag is already linked to another Discord account.")

        await db.execute(
            """
            INSERT INTO links (
                discord_id,
                discord_name,
                platform,
                gamertag,
                linked_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                discord_id,
                discord_name,
                platform,
                gamertag,
                utcnow_iso(),
            ),
        )

        await db.commit()


async def get_link_by_discord(discord_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM links WHERE discord_id = ?",
            (discord_id,),
        )
        return await cursor.fetchone()


async def get_link_by_gamertag(gamertag: str):
    gamertag = " ".join(gamertag.strip().split())

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM links WHERE gamertag = ? COLLATE NOCASE",
            (gamertag,),
        )
        return await cursor.fetchone()


async def delete_link(discord_id: int) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM links WHERE discord_id = ?",
            (discord_id,),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_action_cooldown_remaining(
    gamertag: str,
    action: str,
    cooldown_seconds: int,
) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT claimed_at
            FROM vip_claims
            WHERE gamertag = ? COLLATE NOCASE
              AND package = ?
              AND success = 1
            ORDER BY claimed_at DESC
            LIMIT 1
            """,
            (gamertag, action),
        )
        row = await cursor.fetchone()

    if not row:
        return 0

    last_claim = datetime.fromisoformat(row[0])
    available_at = last_claim + timedelta(seconds=cooldown_seconds)
    remaining = int((available_at - datetime.now(timezone.utc)).total_seconds())
    return max(0, remaining)


async def reset_action_cooldown(gamertag: str, action: str | None = None) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if action:
            cursor = await db.execute(
                "DELETE FROM vip_claims WHERE gamertag = ? COLLATE NOCASE AND package = ?",
                (gamertag, action),
            )
        else:
            cursor = await db.execute(
                "DELETE FROM vip_claims WHERE gamertag = ? COLLATE NOCASE",
                (gamertag,),
            )
        await db.commit()
        return cursor.rowcount


async def store_vip_claim(
    discord_id: int,
    gamertag: str,
    package: str,
    trigger_phrase: str,
    success: bool,
    detail: str,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO vip_claims (
                discord_id,
                gamertag,
                package,
                trigger_phrase,
                success,
                detail,
                claimed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                discord_id,
                gamertag,
                package,
                trigger_phrase,
                int(success),
                detail,
                utcnow_iso(),
            ),
        )
        await db.commit()


async def create_loa_request(
    discord_id: int,
    discord_name: str,
    reason: str,
    start_date: str,
    end_date: str,
    extra_information: str,
) -> int:
    now = utcnow_iso()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO loa_requests (
                discord_id,
                discord_name,
                reason,
                start_date,
                end_date,
                extra_information,
                status,
                review_channel_id,
                review_message_id,
                reviewed_by_id,
                reviewed_by_name,
                review_reason,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending',
                    NULL, NULL, NULL, NULL, NULL, ?, ?)
            """,
            (
                discord_id,
                discord_name,
                reason,
                start_date,
                end_date,
                extra_information,
                now,
                now,
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def get_loa_request(request_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM loa_requests WHERE id = ?",
            (request_id,),
        )
        return await cursor.fetchone()


async def get_active_loa_request(discord_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT *
            FROM loa_requests
            WHERE discord_id = ?
              AND status IN ('pending', 'approved')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (discord_id,),
        )
        return await cursor.fetchone()


async def get_pending_loa_requests():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM loa_requests WHERE status = 'pending'"
        )
        return await cursor.fetchall()


async def update_loa_request_message(
    request_id: int,
    review_message_id: int,
    review_channel_id: int,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE loa_requests
            SET review_message_id = ?,
                review_channel_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                review_message_id,
                review_channel_id,
                utcnow_iso(),
                request_id,
            ),
        )
        await db.commit()


async def update_loa_status(
    request_id: int,
    status: str,
    reviewed_by_id: int,
    reviewed_by_name: str,
    review_reason: str,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE loa_requests
            SET status = ?,
                reviewed_by_id = ?,
                reviewed_by_name = ?,
                review_reason = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                reviewed_by_id,
                reviewed_by_name,
                review_reason,
                utcnow_iso(),
                request_id,
            ),
        )
        await db.commit()
