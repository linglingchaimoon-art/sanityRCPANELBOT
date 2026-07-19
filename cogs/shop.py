from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from config import DATABASE_PATH
from services.database import get_link_by_discord
from services.helpers import announce_shop_purchase


log = logging.getLogger("sanity2x.shop")

BRAND_COLOR = 0xE53935
SUCCESS_COLOR = 0x2ECC71
WARNING_COLOR = 0xF1C40F
DANGER_COLOR = 0xE74C3C

DAILY_REWARD = int(os.getenv("SHOP_DAILY_REWARD", "350"))
GIVE_TEMPLATE = os.getenv(
    "SHOP_GIVE_COMMAND_TEMPLATE",
    'inventory.giveto "{player}" "{item}" {amount}',
)


@dataclass(frozen=True, slots=True)
class Item:
    key: str
    name: str
    icon: str
    category: str
    description: str
    price: int
    rewards: tuple[tuple[str, int], ...]
    stock: int | None = None
    cooldown: int = 0
    featured: bool = False
    rep_required: int = 0


CATEGORIES: dict[str, tuple[str, str, str]] = {
    "featured": ("Featured", "Top picks and limited offers.", "⭐"),
    "starter": ("Starter Kits", "Useful early-wipe starter supplies.", "🎒"),
    "resources": ("Resources", "Building and crafting materials.", "⛏️"),
    "building": ("Building", "Doors, locks, ladders and base utility.", "🏠"),
    "components": ("Components", "Useful road and crafting components.", "⚙️"),
    "electricity": ("Electricity", "Power and electrical starter items.", "⚡"),
    "medical": ("Medical", "Healing supplies and recovery items.", "💉"),
    "farming": ("Farming", "Food, seeds and farming supplies.", "🌾"),
    "utility": ("Utility", "Tools and useful deployables.", "🧰"),
    "bundles": ("Bundles", "Discounted multi-item packages.", "🎁"),
    "black_market": ("Black Market", "Limited stock and reputation items.", "🕶️"),
}


ITEMS: dict[str, Item] = {
    "wood_5k": Item(
        "wood_5k", "Wood Pack", "🌲", "resources",
        "5,000 wood for building and upkeep.",
        350, (("wood", 5000),), featured=True,
    ),
    "stone_5k": Item(
        "stone_5k", "Stone Pack", "⛏️", "resources",
        "5,000 stone for a small base upgrade.",
        500, (("stones", 5000),),
    ),
    "metal_2k": Item(
        "metal_2k", "Metal Fragments", "🔩", "resources",
        "2,000 metal fragments.",
        700, (("metal.fragments", 2000),),
    ),
    "cloth_500": Item(
        "cloth_500", "Cloth Pack", "🧵", "resources",
        "500 cloth for bags, bows and medical crafting.",
        250, (("cloth", 500),),
    ),
    "lowgrade_250": Item(
        "lowgrade_250", "Low Grade Fuel", "🛢️", "resources",
        "250 low grade fuel.",
        450, (("lowgradefuel", 250),),
    ),
    "charcoal_2k": Item(
        "charcoal_2k", "Charcoal Pack", "⚫", "resources",
        "2,000 charcoal. Sulfur is not included.",
        650, (("charcoal", 2000),),
    ),

    "primitive": Item(
        "primitive", "Primitive Starter", "🏹", "starter",
        "Crossbow, arrows and basic gathering tools.",
        700,
        (
            ("crossbow", 1),
            ("arrow.wooden", 40),
            ("stonehatchet", 1),
            ("stone.pickaxe", 1),
        ),
        cooldown=86400,
        featured=True,
    ),
    "builder_start": Item(
        "builder_start", "Builder Starter", "🔨", "starter",
        "A small building starter for a fresh spawn.",
        650,
        (
            ("hammer", 1),
            ("building.planner", 1),
            ("wood", 2500),
            ("stones", 2500),
        ),
        cooldown=43200,
    ),
    "farmer_start": Item(
        "farmer_start", "Farmer Starter", "🌱", "starter",
        "Seeds and basic farming supplies.",
        450,
        (
            ("corn.seed", 6),
            ("pumpkin.seed", 6),
            ("fertilizer", 50),
        ),
        cooldown=43200,
    ),

    "garage_door": Item(
        "garage_door", "Garage Door", "🚪", "building",
        "One garage door.",
        950, (("wall.frame.garagedoor", 1),),
        stock=40,
        featured=True,
    ),
    "code_lock": Item(
        "code_lock", "Code Lock", "🔐", "building",
        "One code lock.",
        180, (("lock.code", 1),),
    ),
    "ladders": Item(
        "ladders", "Ladder Pack", "🪜", "building",
        "Three wooden ladders.",
        260, (("ladder.wooden.wall", 3),),
    ),
    "windows": Item(
        "windows", "Window Pack", "🏠", "building",
        "Two metal window bars.",
        400, (("wall.window.bars.metal", 2),),
    ),

    "gears": Item(
        "gears", "Gears", "⚙️", "components",
        "Three gears.",
        480, (("gears", 3),),
    ),
    "pipes": Item(
        "pipes", "Metal Pipes", "🔧", "components",
        "Four metal pipes.",
        400, (("metalpipe", 4),),
    ),
    "springs": Item(
        "springs", "Metal Springs", "🌀", "components",
        "Three metal springs.",
        520, (("metalspring", 3),),
    ),
    "tech": Item(
        "tech", "Tech Trash", "🖥️", "components",
        "Two tech trash.",
        650, (("techparts", 2),),
        stock=30,
    ),
    "fuses": Item(
        "fuses", "Electric Fuses", "🔌", "components",
        "Two electric fuses.",
        300, (("fuse", 2),),
    ),

    "solar": Item(
        "solar", "Solar Panel", "☀️", "electricity",
        "One large solar panel.",
        500, (("electric.solarpanel.large", 1),),
    ),
    "battery": Item(
        "battery", "Medium Battery", "🔋", "electricity",
        "One medium rechargeable battery.",
        650, (("electric.battery.rechargable.medium", 1),),
    ),
    "switch": Item(
        "switch", "Electrical Switch", "⚡", "electricity",
        "One electrical switch.",
        140, (("electric.switch", 1),),
    ),
    "combiner": Item(
        "combiner", "Root Combiner", "🔀", "electricity",
        "One root combiner.",
        180, (("electrical.combiner", 1),),
    ),

    "syringes": Item(
        "syringes", "Medical Syringes", "💉", "medical",
        "Five medical syringes.",
        420, (("syringe.medical", 5),),
    ),
    "bandages": Item(
        "bandages", "Bandages", "🩹", "medical",
        "Ten bandages.",
        220, (("bandage", 10),),
    ),
    "medkit": Item(
        "medkit", "Large Medkit", "❤️", "medical",
        "One large medkit.",
        350, (("largemedkit", 1),),
    ),

    "pumpkins": Item(
        "pumpkins", "Pumpkin Pack", "🎃", "farming",
        "Ten pumpkins.",
        180, (("pumpkin", 10),),
    ),
    "corn": Item(
        "corn", "Corn Pack", "🌽", "farming",
        "Ten corn.",
        180, (("corn", 10),),
    ),
    "fertilizer": Item(
        "fertilizer", "Fertilizer", "🌾", "farming",
        "One hundred fertilizer.",
        280, (("fertilizer", 100),),
    ),

    "jackhammer": Item(
        "jackhammer", "Jackhammer", "⛏️", "utility",
        "One jackhammer with limited stock and a long cooldown.",
        1800, (("jackhammer", 1),),
        stock=15,
        cooldown=86400,
        featured=True,
        rep_required=2,
    ),
    "chainsaw": Item(
        "chainsaw", "Chainsaw", "🪓", "utility",
        "One chainsaw.",
        1400, (("chainsaw", 1),),
        stock=20,
        cooldown=43200,
        rep_required=1,
    ),
    "repair": Item(
        "repair", "Repair Bench", "🛠️", "utility",
        "One repair bench.",
        500, (("box.repair.bench", 1),),
    ),
    "research": Item(
        "research", "Research Table", "🔬", "utility",
        "One research table.",
        650, (("research.table", 1),),
    ),

    "builder_bundle": Item(
        "builder_bundle", "Builder Bundle", "🏗️", "bundles",
        "A balanced bundle for building and upgrading.",
        2200,
        (
            ("wood", 5000),
            ("stones", 5000),
            ("metal.fragments", 1500),
            ("hammer", 1),
            ("building.planner", 1),
            ("lock.code", 2),
        ),
        stock=20,
        cooldown=43200,
        featured=True,
    ),
    "electric_bundle": Item(
        "electric_bundle", "Electric Bundle", "⚡", "bundles",
        "A simple starter electricity package.",
        1800,
        (
            ("electric.solarpanel.large", 1),
            ("electric.battery.rechargable.medium", 1),
            ("electric.switch", 2),
            ("electrical.combiner", 1),
        ),
        stock=20,
        cooldown=43200,
    ),
    "medical_bundle": Item(
        "medical_bundle", "Medical Bundle", "❤️", "bundles",
        "A modest medical restock.",
        1200,
        (
            ("syringe.medical", 8),
            ("bandage", 10),
            ("largemedkit", 2),
        ),
        cooldown=21600,
    ),

    "utility_cache": Item(
        "utility_cache", "Utility Cache", "❓", "black_market",
        "Receive one random utility reward.",
        1500,
        (("__random_utility__", 1),),
        stock=10,
        cooldown=86400,
        rep_required=3,
    ),
}


RANDOM_UTILITY: tuple[tuple[str, int], ...] = (
    ("jackhammer", 1),
    ("chainsaw", 1),
    ("wall.frame.garagedoor", 2),
    ("techparts", 4),
    ("lowgradefuel", 500),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []

    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{secs}s")

    return " ".join(parts[:2])


def category_items(category: str) -> list[Item]:
    if category == "featured":
        return [item for item in ITEMS.values() if item.featured]

    return [
        item
        for item in ITEMS.values()
        if item.category == category
    ]


def reputation_level(xp: int) -> tuple[int, str, int | None]:
    levels = [
        (0, "Bronze Merchant"),
        (25, "Silver Merchant"),
        (75, "Gold Merchant"),
        (175, "Diamond Merchant"),
        (350, "Legend Merchant"),
    ]

    current_level = 0
    current_name = levels[0][1]
    next_required: int | None = levels[1][0]

    for index, (required, name) in enumerate(levels):
        if xp >= required:
            current_level = index
            current_name = name
            next_required = (
                levels[index + 1][0]
                if index + 1 < len(levels)
                else None
            )

    return current_level, current_name, next_required


async def init_shop_database() -> None:
    Path(DATABASE_PATH).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS shop_wallets (
                discord_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                lifetime_earned INTEGER NOT NULL DEFAULT 0,
                lifetime_spent INTEGER NOT NULL DEFAULT 0,
                reputation_xp INTEGER NOT NULL DEFAULT 0,
                daily_claimed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS shop_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id INTEGER NOT NULL,
                gamertag TEXT NOT NULL,
                item_key TEXT NOT NULL,
                item_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                success INTEGER NOT NULL,
                detail TEXT,
                purchased_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS shop_stock (
                item_key TEXT PRIMARY KEY,
                remaining INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS shop_cooldowns (
                discord_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                used_at TEXT NOT NULL,
                PRIMARY KEY (discord_id, item_key)
            );

            CREATE TABLE IF NOT EXISTS shop_wishlist (
                discord_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY (discord_id, item_key)
            );

            CREATE INDEX IF NOT EXISTS idx_shop_history_user
            ON shop_purchases (discord_id, purchased_at DESC);
            """
        )

        await db.commit()


async def get_wallet(discord_id: int) -> dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO shop_wallets (discord_id)
            VALUES (?)
            """,
            (discord_id,),
        )

        await db.commit()

        db.row_factory = aiosqlite.Row

        row = await (
            await db.execute(
                """
                SELECT *
                FROM shop_wallets
                WHERE discord_id = ?
                """,
                (discord_id,),
            )
        ).fetchone()

        return dict(row)


async def change_coins(
    discord_id: int,
    amount: int,
) -> int:
    await get_wallet(discord_id)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE shop_wallets
            SET
                balance = MAX(0, balance + ?),
                lifetime_earned =
                    lifetime_earned
                    + CASE WHEN ? > 0 THEN ? ELSE 0 END
            WHERE discord_id = ?
            """,
            (
                amount,
                amount,
                amount,
                discord_id,
            ),
        )

        await db.commit()

    return int(
        (await get_wallet(discord_id))["balance"]
    )


async def get_stock(item: Item) -> int | None:
    if item.stock is None:
        return None

    async with aiosqlite.connect(DATABASE_PATH) as db:
        row = await (
            await db.execute(
                """
                SELECT remaining
                FROM shop_stock
                WHERE item_key = ?
                """,
                (item.key,),
            )
        ).fetchone()

        if row:
            return int(row[0])

        await db.execute(
            """
            INSERT INTO shop_stock (
                item_key,
                remaining,
                updated_at
            )
            VALUES (?, ?, ?)
            """,
            (
                item.key,
                item.stock,
                utcnow_iso(),
            ),
        )

        await db.commit()

        return item.stock


async def get_cooldown_remaining(
    discord_id: int,
    item: Item,
) -> int:
    if item.cooldown <= 0:
        return 0

    async with aiosqlite.connect(DATABASE_PATH) as db:
        row = await (
            await db.execute(
                """
                SELECT used_at
                FROM shop_cooldowns
                WHERE discord_id = ?
                  AND item_key = ?
                """,
                (
                    discord_id,
                    item.key,
                ),
            )
        ).fetchone()

    if not row:
        return 0

    used_at = datetime.fromisoformat(row[0])
    available_at = used_at + timedelta(
        seconds=item.cooldown
    )

    return max(
        0,
        int(
            (
                available_at
                - utcnow()
            ).total_seconds()
        ),
    )


def get_rcon_service(bot):
    for attribute in (
        "rcon_service",
        "rcon",
    ):
        service = getattr(
            bot,
            attribute,
            None,
        )

        if (
            service
            and hasattr(
                service,
                "send_command",
            )
        ):
            return service

    return None


async def deliver_item(
    bot,
    gamertag: str,
    item: Item,
) -> tuple[bool, str]:
    service = get_rcon_service(bot)

    if service is None:
        return (
            False,
            (
                "RCON service was not found. "
                "Expected bot.rcon_service or bot.rcon."
            ),
        )

    rewards = list(item.rewards)

    if (
        rewards
        and rewards[0][0] == "__random_utility__"
    ):
        rewards = [
            random.choice(RANDOM_UTILITY)
        ]

    safe_player = (
        gamertag
        .replace('"', "")
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )

    details: list[str] = []

    for rust_item, amount in rewards:
        command = GIVE_TEMPLATE.format(
            player=safe_player,
            item=rust_item,
            amount=int(amount),
        )

        success, response = (
            await service.send_command(command)
        )

        details.append(
            f"{command} -> {response}"
        )

        if not success:
            return (
                False,
                "\n".join(details),
            )

        await asyncio.sleep(0.25)

    return (
        True,
        "\n".join(details),
    )


async def complete_checkout(
    *,
    discord_id: int,
    gamertag: str,
    item: Item,
    delivered: bool,
    detail: str,
) -> tuple[bool, str]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")

        wallet_row = await (
            await db.execute(
                """
                SELECT balance
                FROM shop_wallets
                WHERE discord_id = ?
                """,
                (discord_id,),
            )
        ).fetchone()

        if (
            not wallet_row
            or int(wallet_row[0]) < item.price
        ):
            await db.rollback()

            return (
                False,
                "insufficient_balance",
            )

        if item.stock is not None:
            stock_row = await (
                await db.execute(
                    """
                    SELECT remaining
                    FROM shop_stock
                    WHERE item_key = ?
                    """,
                    (item.key,),
                )
            ).fetchone()

            if (
                not stock_row
                or int(stock_row[0]) <= 0
            ):
                await db.rollback()

                return (
                    False,
                    "out_of_stock",
                )

        if delivered:
            await db.execute(
                """
                UPDATE shop_wallets
                SET
                    balance = balance - ?,
                    lifetime_spent =
                        lifetime_spent + ?,
                    reputation_xp =
                        reputation_xp + MAX(1, ? / 100)
                WHERE discord_id = ?
                """,
                (
                    item.price,
                    item.price,
                    item.price,
                    discord_id,
                ),
            )

            if item.stock is not None:
                await db.execute(
                    """
                    UPDATE shop_stock
                    SET
                        remaining = remaining - 1,
                        updated_at = ?
                    WHERE item_key = ?
                    """,
                    (
                        utcnow_iso(),
                        item.key,
                    ),
                )

            await db.execute(
                """
                INSERT INTO shop_cooldowns (
                    discord_id,
                    item_key,
                    used_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT (
                    discord_id,
                    item_key
                )
                DO UPDATE SET
                    used_at = excluded.used_at
                """,
                (
                    discord_id,
                    item.key,
                    utcnow_iso(),
                ),
            )

        await db.execute(
            """
            INSERT INTO shop_purchases (
                discord_id,
                gamertag,
                item_key,
                item_name,
                price,
                success,
                detail,
                purchased_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                discord_id,
                gamertag,
                item.key,
                item.name,
                item.price,
                int(delivered),
                detail[:1800],
                utcnow_iso(),
            ),
        )

        await db.commit()

    return (
        True,
        "ok",
    )


async def is_wishlisted(
    discord_id: int,
    item_key: str,
) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        row = await (
            await db.execute(
                """
                SELECT 1
                FROM shop_wishlist
                WHERE discord_id = ?
                  AND item_key = ?
                """,
                (
                    discord_id,
                    item_key,
                ),
            )
        ).fetchone()

        return row is not None


async def toggle_wishlist(
    discord_id: int,
    item_key: str,
) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        exists = await (
            await db.execute(
                """
                SELECT 1
                FROM shop_wishlist
                WHERE discord_id = ?
                  AND item_key = ?
                """,
                (
                    discord_id,
                    item_key,
                ),
            )
        ).fetchone()

        if exists:
            await db.execute(
                """
                DELETE FROM shop_wishlist
                WHERE discord_id = ?
                  AND item_key = ?
                """,
                (
                    discord_id,
                    item_key,
                ),
            )

            added = False
        else:
            await db.execute(
                """
                INSERT INTO shop_wishlist (
                    discord_id,
                    item_key,
                    added_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    discord_id,
                    item_key,
                    utcnow_iso(),
                ),
            )

            added = True

        await db.commit()

        return added


def progress_bar(
    current: int,
    target: int,
    *,
    size: int = 10,
) -> str:
    if target <= 0:
        return "■" * size

    ratio = min(
        1.0,
        max(
            0.0,
            current / target,
        ),
    )

    filled = round(ratio * size)

    return (
        "■" * filled
        + "□" * (size - filled)
    )


async def make_home_embed(
    discord_id: int,
) -> discord.Embed:
    wallet = await get_wallet(discord_id)

    level, rank, next_required = (
        reputation_level(
            int(wallet["reputation_xp"])
        )
    )

    embed = discord.Embed(
        title="SANITY MARKET",
        description=(
            "### Fair rewards. Clean delivery. No real-money checkout.\n"
            "Use the menus below to browse a department and inspect an item."
        ),
        color=BRAND_COLOR,
    )

    embed.add_field(
        name="WALLET",
        value=(
            f"🪙 **{wallet['balance']:,} SC**\n"
            f"Earned: `{wallet['lifetime_earned']:,}`\n"
            f"Spent: `{wallet['lifetime_spent']:,}`"
        ),
        inline=True,
    )

    if next_required is None:
        rank_progress = (
            "■■■■■■■■■■\n"
            "**Maximum rank reached**"
        )
    else:
        rank_progress = (
            f"{progress_bar(int(wallet['reputation_xp']), next_required)}\n"
            f"`{wallet['reputation_xp']}/{next_required} XP`"
        )

    embed.add_field(
        name="MERCHANT RANK",
        value=(
            f"🏅 **{rank}**\n"
            f"{rank_progress}"
        ),
        inline=True,
    )

    embed.add_field(
        name="HOW IT WORKS",
        value=(
            "`1.` Choose a department\n"
            "`2.` Select an item\n"
            "`3.` Press **Buy Now**\n"
            "`4.` Receive it on your linked Rust account"
        ),
        inline=False,
    )

    featured = category_items("featured")

    featured_lines = []

    for item in featured[:5]:
        featured_lines.append(
            f"{item.icon} **{item.name}**"
            f"  •  `{item.price:,} SC`"
        )

    embed.add_field(
        name="FEATURED THIS ROTATION",
        value=(
            "\n".join(featured_lines)
            or "No featured items are available."
        ),
        inline=False,
    )

    embed.set_footer(
        text=(
            "Sanity2X • Vanilla 2x • "
            "Select a department below"
        )
    )

    return embed


async def make_category_embed(
    discord_id: int,
    category: str,
) -> discord.Embed:
    wallet = await get_wallet(discord_id)

    category_name, category_description, icon = (
        CATEGORIES[category]
    )

    items = category_items(category)

    embed = discord.Embed(
        title=f"{icon} {category_name.upper()}",
        description=category_description,
        color=BRAND_COLOR,
    )

    embed.add_field(
        name="AVAILABLE",
        value=f"**{len(items)} items**",
        inline=True,
    )

    embed.add_field(
        name="YOUR BALANCE",
        value=f"🪙 **{wallet['balance']:,} SC**",
        inline=True,
    )

    preview_lines = []

    for item in items[:8]:
        preview_lines.append(
            f"{item.icon} **{item.name}**"
            f"  •  `{item.price:,} SC`"
        )

    embed.add_field(
        name="DEPARTMENT PREVIEW",
        value=(
            "\n".join(preview_lines)
            or "No items are currently available."
        ),
        inline=False,
    )

    embed.set_footer(
        text=(
            "Use the second menu to inspect "
            "an item"
        )
    )

    return embed


async def make_item_embed(
    discord_id: int,
    item: Item,
) -> discord.Embed:
    wallet = await get_wallet(discord_id)

    stock = await get_stock(item)

    cooldown = await get_cooldown_remaining(
        discord_id,
        item,
    )

    level, rank, _ = reputation_level(
        int(wallet["reputation_xp"])
    )

    saved = await is_wishlisted(
        discord_id,
        item.key,
    )

    status = "READY"

    color = SUCCESS_COLOR

    if (
        stock is not None
        and stock <= 0
    ):
        status = "SOLD OUT"
        color = DANGER_COLOR

    elif cooldown > 0:
        status = (
            f"COOLDOWN • "
            f"{format_duration(cooldown)}"
        )
        color = WARNING_COLOR

    elif level < item.rep_required:
        status = (
            f"LOCKED • "
            f"MERCHANT LEVEL "
            f"{item.rep_required}"
        )
        color = WARNING_COLOR

    elif int(wallet["balance"]) < item.price:
        missing = (
            item.price
            - int(wallet["balance"])
        )

        status = (
            f"NEED {missing:,} MORE SC"
        )

        color = WARNING_COLOR

    embed = discord.Embed(
        title=f"{item.icon} {item.name}",
        description=(
            f"{item.description}\n\n"
            f"**STATUS**\n"
            f"`{status}`"
        ),
        color=color,
    )

    embed.add_field(
        name="PRICE",
        value=f"🪙 **{item.price:,} SC**",
        inline=True,
    )

    embed.add_field(
        name="BALANCE",
        value=f"🪙 **{wallet['balance']:,} SC**",
        inline=True,
    )

    embed.add_field(
        name="STOCK",
        value=(
            "**Unlimited**"
            if stock is None
            else f"**{stock} left**"
        ),
        inline=True,
    )

    if item.cooldown > 0:
        embed.add_field(
            name="COOLDOWN",
            value=(
                "**Ready now**"
                if cooldown <= 0
                else f"**{format_duration(cooldown)}**"
            ),
            inline=True,
        )

    if item.rep_required > 0:
        embed.add_field(
            name="REQUIRED RANK",
            value=(
                f"**Merchant Level "
                f"{item.rep_required}**"
            ),
            inline=True,
        )

    embed.add_field(
        name="SAVED",
        value=(
            "**Yes**"
            if saved
            else "**No**"
        ),
        inline=True,
    )

    reward_lines = []

    for reward_name, amount in item.rewards:
        if reward_name == "__random_utility__":
            reward_lines.append(
                "• One random utility reward"
            )
        else:
            reward_lines.append(
                f"• `{amount}x {reward_name}`"
            )

    embed.add_field(
        name="PACKAGE CONTENTS",
        value="\n".join(reward_lines),
        inline=False,
    )

    embed.set_footer(
        text=(
            f"{rank} • "
            "Press Buy Now for instant delivery"
        )
    )

    return embed


class ItemSelect(discord.ui.Select):
    def __init__(
        self,
        market_view: "MarketView",
        category: str,
    ):
        self.market_view = market_view

        items = category_items(category)

        options = [
            discord.SelectOption(
                label=item.name[:100],
                value=item.key,
                description=(
                    f"{item.price:,} SC"
                    + (
                        f" • Stock {item.stock}"
                        if item.stock is not None
                        else ""
                    )
                )[:100],
            )
            for item in items[:25]
        ]

        if not options:
            options = [
                discord.SelectOption(
                    label="No items available",
                    value="none",
                )
            ]

        super().__init__(
            placeholder="2. Choose an item",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        selected = self.values[0]

        if selected == "none":
            await interaction.response.defer()
            return

        self.market_view.selected_item_key = (
            selected
        )

        await interaction.response.edit_message(
            embed=await make_item_embed(
                interaction.user.id,
                ITEMS[selected],
            ),
            view=self.market_view,
        )


class CategorySelect(discord.ui.Select):
    def __init__(
        self,
        market_view: "MarketView",
    ):
        self.market_view = market_view

        options = [
            discord.SelectOption(
                label=category_name,
                value=category_key,
                description=category_description[:100],
            )
            for (
                category_key,
                (
                    category_name,
                    category_description,
                    _,
                ),
            ) in CATEGORIES.items()
        ]

        super().__init__(
            placeholder="1. Choose a department",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        category = self.values[0]

        self.market_view.category = category
        self.market_view.selected_item_key = None

        self.market_view.replace_item_select(
            category
        )

        await interaction.response.edit_message(
            embed=await make_category_embed(
                interaction.user.id,
                category,
            ),
            view=self.market_view,
        )


class MarketView(discord.ui.View):
    def __init__(
        self,
        bot,
        owner_id: int,
    ):
        super().__init__(timeout=300)

        self.bot = bot
        self.owner_id = owner_id
        self.category = "featured"
        self.selected_item_key: str | None = None

        self.add_item(
            CategorySelect(self)
        )

        self.add_item(
            ItemSelect(
                self,
                "featured",
            )
        )

    def replace_item_select(
        self,
        category: str,
    ) -> None:
        for child in list(self.children):
            if isinstance(
                child,
                ItemSelect,
            ):
                self.remove_item(child)

        self.add_item(
            ItemSelect(
                self,
                category,
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if (
            interaction.user.id
            != self.owner_id
        ):
            await interaction.response.send_message(
                (
                    "This shop menu belongs to "
                    "another user. Use `/shop` "
                    "to open your own."
                ),
                ephemeral=True,
            )

            return False

        return True

    @discord.ui.button(
        label="Buy Now",
        style=discord.ButtonStyle.success,
        row=2,
    )
    async def buy_now(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not self.selected_item_key:
            await interaction.response.send_message(
                "Select an item first.",
                ephemeral=True,
            )

            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        item = ITEMS[
            self.selected_item_key
        ]

        link = await get_link_by_discord(
            interaction.user.id
        )

        if not link:
            await interaction.followup.send(
                (
                    "Your Discord account is not "
                    "linked to Rust. Use `/link` "
                    "before buying."
                ),
                ephemeral=True,
            )

            return

        gamertag = str(
            link["gamertag"]
        )

        wallet = await get_wallet(
            interaction.user.id
        )

        level, _, _ = reputation_level(
            int(wallet["reputation_xp"])
        )

        if int(wallet["balance"]) < item.price:
            missing = (
                item.price
                - int(wallet["balance"])
            )

            await interaction.followup.send(
                (
                    f"You need **{missing:,} more SC** "
                    f"to purchase **{item.name}**."
                ),
                ephemeral=True,
            )

            return

        if level < item.rep_required:
            await interaction.followup.send(
                (
                    f"**{item.name}** requires "
                    f"Merchant Level "
                    f"**{item.rep_required}**."
                ),
                ephemeral=True,
            )

            return

        stock = await get_stock(item)

        if (
            stock is not None
            and stock <= 0
        ):
            await interaction.followup.send(
                "This item is sold out.",
                ephemeral=True,
            )

            return

        cooldown = await get_cooldown_remaining(
            interaction.user.id,
            item,
        )

        if cooldown > 0:
            await interaction.followup.send(
                (
                    f"This item is available again in "
                    f"**{format_duration(cooldown)}**."
                ),
                ephemeral=True,
            )

            return

        delivered, detail = await deliver_item(
            self.bot,
            gamertag,
            item,
        )

        committed, reason = (
            await complete_checkout(
                discord_id=interaction.user.id,
                gamertag=gamertag,
                item=item,
                delivered=delivered,
                detail=detail,
            )
        )

        if not committed:
            await interaction.followup.send(
                (
                    "The checkout changed while your "
                    "purchase was being processed. "
                    "No coins were taken. Try again."
                ),
                ephemeral=True,
            )

            return

        if not delivered:
            log.error(
                (
                    "Shop delivery failed for "
                    "%s: %s"
                ),
                gamertag,
                detail,
            )

            await interaction.followup.send(
                (
                    "Delivery failed and "
                    "**no Sanity Coins were taken**. "
                    "Please contact staff."
                ),
                ephemeral=True,
            )

            return

        new_wallet = await get_wallet(
            interaction.user.id
        )

        try:
            announced, announce_response = (
                await announce_shop_purchase(
                    self.bot.rcon_service,
                    gamertag,
                    item.name,
                )
            )

            if not announced:
                log.warning(
                    "Purchase delivered but announcement failed: %s",
                    announce_response,
                )

        except Exception:
            log.exception(
                "Purchase delivered but announcement raised an error"
            )

        success_embed = discord.Embed(
            title="PURCHASE COMPLETE",
            description=(
                f"**{item.name}** was delivered "
                f"to `{gamertag}`."
            ),
            color=SUCCESS_COLOR,
        )

        success_embed.add_field(
            name="PAID",
            value=f"🪙 **{item.price:,} SC**",
            inline=True,
        )

        success_embed.add_field(
            name="NEW BALANCE",
            value=(
                f"🪙 **"
                f"{new_wallet['balance']:,} SC**"
            ),
            inline=True,
        )

        success_embed.set_footer(
            text="Sanity2X Market • Delivery successful"
        )

        await interaction.followup.send(
            embed=success_embed,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Save Item",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def save_item(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if not self.selected_item_key:
            await interaction.response.send_message(
                "Select an item first.",
                ephemeral=True,
            )

            return

        added = await toggle_wishlist(
            interaction.user.id,
            self.selected_item_key,
        )

        await interaction.response.send_message(
            (
                "Item saved to your wishlist."
                if added
                else "Item removed from your wishlist."
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Wallet",
        style=discord.ButtonStyle.primary,
        row=2,
    )
    async def wallet_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_message(
            embed=await make_wallet_embed(
                interaction.user.id
            ),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Home",
        style=discord.ButtonStyle.secondary,
        row=2,
    )
    async def home_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        self.category = "featured"
        self.selected_item_key = None

        self.replace_item_select(
            "featured"
        )

        await interaction.response.edit_message(
            embed=await make_home_embed(
                interaction.user.id
            ),
            view=self,
        )


async def make_wallet_embed(
    discord_id: int,
) -> discord.Embed:
    wallet = await get_wallet(discord_id)

    level, rank, next_required = (
        reputation_level(
            int(wallet["reputation_xp"])
        )
    )

    embed = discord.Embed(
        title="SANITY WALLET",
        color=BRAND_COLOR,
    )

    embed.add_field(
        name="CURRENT BALANCE",
        value=f"🪙 **{wallet['balance']:,} SC**",
        inline=False,
    )

    embed.add_field(
        name="LIFETIME EARNED",
        value=f"`{wallet['lifetime_earned']:,} SC`",
        inline=True,
    )

    embed.add_field(
        name="LIFETIME SPENT",
        value=f"`{wallet['lifetime_spent']:,} SC`",
        inline=True,
    )

    embed.add_field(
        name="MERCHANT RANK",
        value=f"🏅 **{rank}** • Level {level}",
        inline=False,
    )

    if next_required is None:
        progress = (
            "■■■■■■■■■■\n"
            "**Maximum rank reached**"
        )
    else:
        progress = (
            f"{progress_bar(int(wallet['reputation_xp']), next_required)}\n"
            f"`{wallet['reputation_xp']}/{next_required} XP`"
        )

    embed.add_field(
        name="RANK PROGRESS",
        value=progress,
        inline=False,
    )

    embed.set_footer(
        text="Sanity2X • Earn coins through rewards and events"
    )

    return embed


class Shop(commands.Cog):
    def __init__(
        self,
        bot,
    ):
        self.bot = bot

    async def cog_load(self):
        await init_shop_database()

    @app_commands.command(
        name="shop",
        description="Open the Sanity2X coin market.",
    )
    async def shop(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            embed=await make_home_embed(
                interaction.user.id
            ),
            view=MarketView(
                self.bot,
                interaction.user.id,
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="wallet",
        description="View your Sanity Coin wallet.",
    )
    async def wallet(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.send_message(
            embed=await make_wallet_embed(
                interaction.user.id
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="daily",
        description="Claim your daily Sanity Coins.",
    )
    async def daily(
        self,
        interaction: discord.Interaction,
    ):
        wallet = await get_wallet(
            interaction.user.id
        )

        claimed_at = wallet.get(
            "daily_claimed_at"
        )

        if claimed_at:
            available_at = (
                datetime.fromisoformat(
                    claimed_at
                )
                + timedelta(hours=24)
            )

            remaining = int(
                (
                    available_at
                    - utcnow()
                ).total_seconds()
            )

            if remaining > 0:
                await interaction.response.send_message(
                    (
                        "Your daily reward is "
                        f"available in "
                        f"**{format_duration(remaining)}**."
                    ),
                    ephemeral=True,
                )

                return

        async with aiosqlite.connect(
            DATABASE_PATH
        ) as db:
            await db.execute(
                """
                UPDATE shop_wallets
                SET
                    balance = balance + ?,
                    lifetime_earned =
                        lifetime_earned + ?,
                    daily_claimed_at = ?
                WHERE discord_id = ?
                """,
                (
                    DAILY_REWARD,
                    DAILY_REWARD,
                    utcnow_iso(),
                    interaction.user.id,
                ),
            )

            await db.commit()

        new_wallet = await get_wallet(
            interaction.user.id
        )

        embed = discord.Embed(
            title="DAILY REWARD CLAIMED",
            description=(
                f"You received "
                f"**{DAILY_REWARD:,} SC**."
            ),
            color=SUCCESS_COLOR,
        )

        embed.add_field(
            name="NEW BALANCE",
            value=(
                f"🪙 **"
                f"{new_wallet['balance']:,} SC**"
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="history",
        description="View your recent shop purchases.",
    )
    async def history(
        self,
        interaction: discord.Interaction,
    ):
        async with aiosqlite.connect(
            DATABASE_PATH
        ) as db:
            db.row_factory = aiosqlite.Row

            rows = await (
                await db.execute(
                    """
                    SELECT
                        item_name,
                        price,
                        success,
                        purchased_at
                    FROM shop_purchases
                    WHERE discord_id = ?
                    ORDER BY purchased_at DESC
                    LIMIT 10
                    """,
                    (interaction.user.id,),
                )
            ).fetchall()

        if not rows:
            description = (
                "You have no purchase history yet."
            )
        else:
            lines = []

            for row in rows:
                status = (
                    "SUCCESS"
                    if row["success"]
                    else "FAILED"
                )

                lines.append(
                    f"`{status}` **{row['item_name']}**"
                    f" • {row['price']:,} SC"
                )

            description = "\n".join(lines)

        embed = discord.Embed(
            title="PURCHASE HISTORY",
            description=description,
            color=BRAND_COLOR,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="wishlist",
        description="View your saved shop items.",
    )
    async def wishlist(
        self,
        interaction: discord.Interaction,
    ):
        async with aiosqlite.connect(
            DATABASE_PATH
        ) as db:
            rows = await (
                await db.execute(
                    """
                    SELECT item_key
                    FROM shop_wishlist
                    WHERE discord_id = ?
                    ORDER BY added_at DESC
                    """,
                    (interaction.user.id,),
                )
            ).fetchall()

        saved_items = [
            ITEMS[row[0]]
            for row in rows
            if row[0] in ITEMS
        ]

        if saved_items:
            description = "\n".join(
                (
                    f"{item.icon} **{item.name}**"
                    f" • `{item.price:,} SC`"
                )
                for item in saved_items
            )
        else:
            description = (
                "Your wishlist is empty."
            )

        embed = discord.Embed(
            title="SAVED ITEMS",
            description=description,
            color=BRAND_COLOR,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="givecoins",
        description="Admin: give or remove Sanity Coins.",
    )
    @app_commands.default_permissions(
        administrator=True
    )
    async def givecoins(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[
            int,
            -1_000_000,
            1_000_000,
        ],
    ):
        new_balance = await change_coins(
            member.id,
            amount,
        )

        await interaction.response.send_message(
            (
                f"Updated {member.mention} by "
                f"**{amount:+,} SC**.\n"
                f"New balance: "
                f"**{new_balance:,} SC**"
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="restock",
        description="Admin: reset an item's limited stock.",
    )
    @app_commands.default_permissions(
        administrator=True
    )
    async def restock(
        self,
        interaction: discord.Interaction,
        item_key: str,
        amount: app_commands.Range[
            int,
            0,
            10_000,
        ],
    ):
        if item_key not in ITEMS:
            await interaction.response.send_message(
                "Unknown item key.",
                ephemeral=True,
            )

            return

        async with aiosqlite.connect(
            DATABASE_PATH
        ) as db:
            await db.execute(
                """
                INSERT INTO shop_stock (
                    item_key,
                    remaining,
                    updated_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT (item_key)
                DO UPDATE SET
                    remaining = excluded.remaining,
                    updated_at = excluded.updated_at
                """,
                (
                    item_key,
                    amount,
                    utcnow_iso(),
                ),
            )

            await db.commit()

        await interaction.response.send_message(
            (
                f"Restocked `{item_key}` "
                f"to **{amount}**."
            ),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(
        Shop(bot)
    )
