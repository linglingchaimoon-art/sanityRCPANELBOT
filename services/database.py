import os
from datetime import datetime, timezone

import aiosqlite

from config import DATABASE_PATH


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def init_database() -> None:
    directory = os.path.dirname(DATABASE_PATH)

    if directory:
        os.makedirs(directory, exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH) as database:
        await database.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                discord_id INTEGER PRIMARY KEY,
                gamertag TEXT NOT NULL UNIQUE COLLATE NOCASE,
                linked_at TEXT NOT NULL
            )
            """
        )

        await database.execute(
            """
            CREATE TABLE IF NOT EXISTS vip_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                gamertag TEXT NOT NULL COLLATE NOCASE,
                package TEXT NOT NULL,
                trigger_phrase TEXT NOT NULL,
                success INTEGER NOT NULL,
                detail TEXT,
                claimed_at TEXT NOT NULL
            )
            """
        )

        await database.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_vip_claims_gamertag_package
            ON vip_claims(gamertag, package, claimed_at)
            """
        )

        await database.execute(
            """
            CREATE TABLE IF NOT EXISTS loa_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                review_message_id INTEGER,
                reviewed_by INTEGER,
                reviewed_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        await database.commit()


async def save_link(
    discord_id: int,
    gamertag: str,
) -> None:
    clean_gamertag = " ".join(
        gamertag.strip().split()
    )

    async with aiosqlite.connect(DATABASE_PATH) as database:
        await database.execute(
            """
            DELETE FROM links
            WHERE discord_id = ?
               OR gamertag = ? COLLATE NOCASE
            """,
            (
                discord_id,
                clean_gamertag,
            ),
        )

        await database.execute(
            """
            INSERT INTO links (
                discord_id,
                gamertag,
                linked_at
            )
            VALUES (?, ?, ?)
            """,
            (
                discord_id,
                clean_gamertag,
                utcnow_iso(),
            ),
        )

        await database.commit()


async def get_link_by_discord(
    discord_id: int,
) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        database.row_factory = aiosqlite.Row

        cursor = await database.execute(
            """
            SELECT discord_id, gamertag, linked_at
            FROM links
            WHERE discord_id = ?
            """,
            (discord_id,),
        )

        row = await cursor.fetchone()

        return dict(row) if row else None


async def get_link_by_gamertag(
    gamertag: str,
) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        database.row_factory = aiosqlite.Row

        cursor = await database.execute(
            """
            SELECT discord_id, gamertag, linked_at
            FROM links
            WHERE gamertag = ? COLLATE NOCASE
            """,
            (gamertag.strip(),),
        )

        row = await cursor.fetchone()

        return dict(row) if row else None


async def delete_link(
    discord_id: int,
) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        cursor = await database.execute(
            """
            DELETE FROM links
            WHERE discord_id = ?
            """,
            (discord_id,),
        )

        await database.commit()

        return cursor.rowcount


async def get_action_cooldown_remaining(
    gamertag: str,
    action: str,
    cooldown_seconds: int,
) -> int:
    if cooldown_seconds <= 0:
        return 0

    async with aiosqlite.connect(DATABASE_PATH) as database:
        cursor = await database.execute(
            """
            SELECT claimed_at
            FROM vip_claims
            WHERE gamertag = ? COLLATE NOCASE
              AND package = ?
              AND success = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                gamertag.strip(),
                action,
            ),
        )

        row = await cursor.fetchone()

    if not row:
        return 0

    try:
        claimed_at = datetime.fromisoformat(row[0])

        if claimed_at.tzinfo is None:
            claimed_at = claimed_at.replace(
                tzinfo=timezone.utc
            )
    except (TypeError, ValueError):
        return 0

    elapsed = (
        datetime.now(timezone.utc) - claimed_at
    ).total_seconds()

    remaining = cooldown_seconds - int(elapsed)

    return max(0, remaining)


async def reset_action_cooldown(
    gamertag: str,
    action: str | None = None,
) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        if action is None:
            cursor = await database.execute(
                """
                DELETE FROM vip_claims
                WHERE gamertag = ? COLLATE NOCASE
                """,
                (gamertag.strip(),),
            )
        else:
            cursor = await database.execute(
                """
                DELETE FROM vip_claims
                WHERE gamertag = ? COLLATE NOCASE
                  AND package = ?
                """,
                (
                    gamertag.strip(),
                    action,
                ),
            )

        await database.commit()

        return cursor.rowcount


async def store_vip_claim(
    discord_id: int,
    gamertag: str,
    package: str,
    trigger_phrase: str,
    success: bool,
    detail: str,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        await database.execute(
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
                gamertag.strip(),
                package,
                trigger_phrase,
                1 if success else 0,
                detail,
                utcnow_iso(),
            ),
        )

        await database.commit()


async def create_loa_request(
    discord_id: int,
    reason: str,
    start_date: str,
    end_date: str,
) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        cursor = await database.execute(
            """
            INSERT INTO loa_requests (
                discord_id,
                reason,
                start_date,
                end_date,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (
                discord_id,
                reason,
                start_date,
                end_date,
                utcnow_iso(),
            ),
        )

        await database.commit()

        return cursor.lastrowid


async def get_loa_request(
    request_id: int,
) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        database.row_factory = aiosqlite.Row

        cursor = await database.execute(
            """
            SELECT *
            FROM loa_requests
            WHERE id = ?
            """,
            (request_id,),
        )

        row = await cursor.fetchone()

        return dict(row) if row else None


async def get_active_loa_request(
    discord_id: int,
) -> dict | None:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        database.row_factory = aiosqlite.Row

        cursor = await database.execute(
            """
            SELECT *
            FROM loa_requests
            WHERE discord_id = ?
              AND status IN ('pending', 'approved')
            ORDER BY id DESC
            LIMIT 1
            """,
            (discord_id,),
        )

        row = await cursor.fetchone()

        return dict(row) if row else None


async def get_pending_loa_requests() -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        database.row_factory = aiosqlite.Row

        cursor = await database.execute(
            """
            SELECT *
            FROM loa_requests
            WHERE status = 'pending'
            ORDER BY id ASC
            """
        )

        rows = await cursor.fetchall()

        return [dict(row) for row in rows]


async def update_loa_request_message(
    request_id: int,
    message_id: int,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        await database.execute(
            """
            UPDATE loa_requests
            SET review_message_id = ?
            WHERE id = ?
            """,
            (
                message_id,
                request_id,
            ),
        )

        await database.commit()


async def update_loa_status(
    request_id: int,
    status: str,
    reviewed_by: int,
) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as database:
        await database.execute(
            """
            UPDATE loa_requests
            SET status = ?,
                reviewed_by = ?,
                reviewed_at = ?
            WHERE id = ?
            """,
            (
                status,
                reviewed_by,
                utcnow_iso(),
                request_id,
            ),
        )

        await database.commit()