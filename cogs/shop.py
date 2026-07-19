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

log = logging.getLogger("sanity2x.shop")
COLOR = 0xE53935
DAILY_REWARD = int(os.getenv("SHOP_DAILY_REWARD", "350"))
GIVE_TEMPLATE = os.getenv(
    "SHOP_GIVE_COMMAND_TEMPLATE",
    'inventory.giveto "{player}" "{item}" {amount}',
)


@dataclass(frozen=True, slots=True)
class Item:
    key: str
    name: str
    emoji: str
    category: str
    description: str
    price: int
    rewards: tuple[tuple[str, int], ...]
    stock: int | None = None
    cooldown: int = 0
    featured: bool = False
    rep_required: int = 0


CATEGORIES = {
    "featured": ("⭐", "Featured"),
    "starter": ("🎒", "Starter"),
    "resources": ("⛏️", "Resources"),
    "building": ("🏠", "Building"),
    "components": ("⚙️", "Components"),
    "electricity": ("⚡", "Electricity"),
    "medical": ("💉", "Medical"),
    "farming": ("🌾", "Farming"),
    "utility": ("🧰", "Utility"),
    "bundles": ("🎁", "Bundles"),
    "black_market": ("🕶️", "Black Market"),
}

ITEMS = {
    "wood_5k": Item("wood_5k", "Wood Pack", "🪵", "resources", "5,000 wood.", 350, (("wood", 5000),), featured=True),
    "stone_5k": Item("stone_5k", "Stone Pack", "🪨", "resources", "5,000 stone.", 500, (("stones", 5000),)),
    "metal_2k": Item("metal_2k", "Metal Fragments", "🔩", "resources", "2,000 metal fragments.", 700, (("metal.fragments", 2000),)),
    "cloth_500": Item("cloth_500", "Cloth Pack", "🧵", "resources", "500 cloth.", 250, (("cloth", 500),)),
    "lowgrade_250": Item("lowgrade_250", "Low Grade Fuel", "🛢️", "resources", "250 low grade fuel.", 450, (("lowgradefuel", 250),)),
    "charcoal_2k": Item("charcoal_2k", "Charcoal Pack", "⚫", "resources", "2,000 charcoal.", 650, (("charcoal", 2000),)),

    "primitive": Item("primitive", "Primitive Starter", "🏹", "starter", "Crossbow, arrows and tools. 24-hour cooldown.", 700, (("crossbow", 1), ("arrow.wooden", 40), ("stonehatchet", 1), ("stone.pickaxe", 1)), cooldown=86400, featured=True),
    "builder_start": Item("builder_start", "Builder Starter", "🔨", "starter", "Small building starter.", 650, (("hammer", 1), ("building.planner", 1), ("wood", 2500), ("stones", 2500)), cooldown=43200),
    "farmer_start": Item("farmer_start", "Farmer Starter", "🌱", "starter", "Seeds and farming supplies.", 450, (("corn.seed", 6), ("pumpkin.seed", 6), ("fertilizer", 50)), cooldown=43200),

    "garage_door": Item("garage_door", "Garage Door", "🚪", "building", "One garage door.", 950, (("wall.frame.garagedoor", 1),), stock=40, featured=True),
    "code_lock": Item("code_lock", "Code Lock", "🔐", "building", "One code lock.", 180, (("lock.code", 1),)),
    "ladders": Item("ladders", "Ladder Pack", "🪜", "building", "Three ladders.", 260, (("ladder.wooden.wall", 3),)),
    "windows": Item("windows", "Window Pack", "🪟", "building", "Two metal window bars.", 400, (("wall.window.bars.metal", 2),)),

    "gears": Item("gears", "Gears", "⚙️", "components", "Three gears.", 480, (("gears", 3),)),
    "pipes": Item("pipes", "Metal Pipes", "🧯", "components", "Four metal pipes.", 400, (("metalpipe", 4),)),
    "springs": Item("springs", "Metal Springs", "🌀", "components", "Three metal springs.", 520, (("metalspring", 3),)),
    "tech": Item("tech", "Tech Trash", "🖥️", "components", "Two tech trash.", 650, (("techparts", 2),), stock=30),
    "fuses": Item("fuses", "Electric Fuses", "🔌", "components", "Two fuses.", 300, (("fuse", 2),)),

    "solar": Item("solar", "Solar Panel", "☀️", "electricity", "One large solar panel.", 500, (("electric.solarpanel.large", 1),)),
    "battery": Item("battery", "Medium Battery", "🔋", "electricity", "One medium battery.", 650, (("electric.battery.rechargable.medium", 1),)),
    "switch": Item("switch", "Electrical Switch", "🎚️", "electricity", "One switch.", 140, (("electric.switch", 1),)),
    "combiner": Item("combiner", "Root Combiner", "🔀", "electricity", "One root combiner.", 180, (("electrical.combiner", 1),)),

    "syringes": Item("syringes", "Medical Syringes", "💉", "medical", "Five syringes.", 420, (("syringe.medical", 5),)),
    "bandages": Item("bandages", "Bandages", "🩹", "medical", "Ten bandages.", 220, (("bandage", 10),)),
    "medkit": Item("medkit", "Large Medkit", "❤️‍🩹", "medical", "One large medkit.", 350, (("largemedkit", 1),)),

    "pumpkins": Item("pumpkins", "Pumpkin Pack", "🎃", "farming", "Ten pumpkins.", 180, (("pumpkin", 10),)),
    "corn": Item("corn", "Corn Pack", "🌽", "farming", "Ten corn.", 180, (("corn", 10),)),
    "fertilizer": Item("fertilizer", "Fertilizer", "💩", "farming", "One hundred fertilizer.", 280, (("fertilizer", 100),)),

    "jackhammer": Item("jackhammer", "Jackhammer", "⛏️", "utility", "Limited stock and 24-hour cooldown.", 1800, (("jackhammer", 1),), stock=15, cooldown=86400, featured=True, rep_required=2),
    "chainsaw": Item("chainsaw", "Chainsaw", "🪚", "utility", "One chainsaw.", 1400, (("chainsaw", 1),), stock=20, cooldown=43200, rep_required=1),
    "repair": Item("repair", "Repair Bench", "🛠️", "utility", "One repair bench.", 500, (("box.repair.bench", 1),)),
    "research": Item("research", "Research Table", "🔬", "utility", "One research table.", 650, (("research.table", 1),)),

    "builder_bundle": Item("builder_bundle", "Builder Bundle", "🏗️", "bundles", "Balanced building convenience bundle.", 2200, (("wood", 5000), ("stones", 5000), ("metal.fragments", 1500), ("hammer", 1), ("building.planner", 1), ("lock.code", 2)), stock=20, cooldown=43200, featured=True),
    "electric_bundle": Item("electric_bundle", "Electric Bundle", "⚡", "bundles", "Starter electricity bundle.", 1800, (("electric.solarpanel.large", 1), ("electric.battery.rechargable.medium", 1), ("electric.switch", 2), ("electrical.combiner", 1)), stock=20, cooldown=43200),
    "medical_bundle": Item("medical_bundle", "Medical Bundle", "❤️‍🩹", "bundles", "Modest medical restock.", 1200, (("syringe.medical", 8), ("bandage", 10), ("largemedkit", 2)), cooldown=21600),

    "utility_cache": Item("utility_cache", "Utility Cache", "❓", "black_market", "One random utility reward.", 1500, (("__random_utility__", 1),), stock=10, cooldown=86400, rep_required=3),
}

RANDOM_UTILITY = (
    ("jackhammer", 1),
    ("chainsaw", 1),
    ("wall.frame.garagedoor", 2),
    ("techparts", 4),
    ("lowgradefuel", 500),
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def fmt(seconds: int) -> str:
    days, rem = divmod(max(0, seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if not parts: parts.append(f"{secs}s")
    return " ".join(parts[:2])


def category_items(category: str) -> list[Item]:
    if category == "featured":
        return [x for x in ITEMS.values() if x.featured]
    return [x for x in ITEMS.values() if x.category == category]


def rep_level(xp: int) -> tuple[int, str]:
    levels = [(0, "Bronze"), (25, "Silver"), (75, "Gold"), (175, "Diamond"), (350, "Legend")]
    level, name = 0, "Bronze"
    for i, (required, title) in enumerate(levels):
        if xp >= required:
            level, name = i, title
    return level, f"{name} Merchant"


async def init_db():
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS shop_wallets(
            discord_id INTEGER PRIMARY KEY,
            balance INTEGER NOT NULL DEFAULT 0,
            lifetime_earned INTEGER NOT NULL DEFAULT 0,
            lifetime_spent INTEGER NOT NULL DEFAULT 0,
            reputation_xp INTEGER NOT NULL DEFAULT 0,
            daily_claimed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS shop_purchases(
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
        CREATE TABLE IF NOT EXISTS shop_stock(
            item_key TEXT PRIMARY KEY,
            remaining INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS shop_cooldowns(
            discord_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            used_at TEXT NOT NULL,
            PRIMARY KEY(discord_id,item_key)
        );
        CREATE TABLE IF NOT EXISTS shop_wishlist(
            discord_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY(discord_id,item_key)
        );
        """)
        await db.commit()


async def wallet(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO shop_wallets(discord_id) VALUES(?)", (user_id,))
        await db.commit()
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("SELECT * FROM shop_wallets WHERE discord_id=?", (user_id,))).fetchone()
        return dict(row)


async def change_coins(user_id: int, amount: int):
    await wallet(user_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
        UPDATE shop_wallets
        SET balance=MAX(0,balance+?),
            lifetime_earned=lifetime_earned+CASE WHEN ?>0 THEN ? ELSE 0 END
        WHERE discord_id=?
        """, (amount, amount, amount, user_id))
        await db.commit()
    return (await wallet(user_id))["balance"]


async def stock_for(item: Item):
    if item.stock is None:
        return None
    async with aiosqlite.connect(DATABASE_PATH) as db:
        row = await (await db.execute("SELECT remaining FROM shop_stock WHERE item_key=?", (item.key,))).fetchone()
        if row:
            return int(row[0])
        await db.execute("INSERT INTO shop_stock VALUES(?,?,?)", (item.key, item.stock, now_iso()))
        await db.commit()
        return item.stock


async def cooldown_left(user_id: int, item: Item):
    if not item.cooldown:
        return 0
    async with aiosqlite.connect(DATABASE_PATH) as db:
        row = await (await db.execute("SELECT used_at FROM shop_cooldowns WHERE discord_id=? AND item_key=?", (user_id, item.key))).fetchone()
    if not row:
        return 0
    return max(0, int((datetime.fromisoformat(row[0]) + timedelta(seconds=item.cooldown) - now()).total_seconds()))


def get_rcon(bot):
    for name in ("rcon_service", "rcon"):
        service = getattr(bot, name, None)
        if service and hasattr(service, "send_command"):
            return service
    return None


async def deliver(bot, gamertag: str, item: Item):
    service = get_rcon(bot)
    if service is None:
        return False, "RCON service not found on bot.rcon_service or bot.rcon"
    rewards = list(item.rewards)
    if rewards and rewards[0][0] == "__random_utility__":
        rewards = [random.choice(RANDOM_UTILITY)]
    details = []
    player = gamertag.replace('"', "").replace("\n", " ").strip()
    for rust_item, amount in rewards:
        command = GIVE_TEMPLATE.format(player=player, item=rust_item, amount=amount)
        ok, response = await service.send_command(command)
        details.append(f"{command} -> {response}")
        if not ok:
            return False, "\n".join(details)
        await asyncio.sleep(.25)
    return True, "\n".join(details)


async def checkout(user_id: int, gamertag: str, item: Item, delivered: bool, detail: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("BEGIN IMMEDIATE")
        row = await (await db.execute("SELECT balance FROM shop_wallets WHERE discord_id=?", (user_id,))).fetchone()
        if not row or int(row[0]) < item.price:
            await db.rollback()
            return False, "balance"
        if item.stock is not None:
            row = await (await db.execute("SELECT remaining FROM shop_stock WHERE item_key=?", (item.key,))).fetchone()
            if not row or int(row[0]) <= 0:
                await db.rollback()
                return False, "stock"
        if delivered:
            await db.execute("""
            UPDATE shop_wallets
            SET balance=balance-?, lifetime_spent=lifetime_spent+?,
                reputation_xp=reputation_xp+MAX(1,?/100)
            WHERE discord_id=?
            """, (item.price, item.price, item.price, user_id))
            if item.stock is not None:
                await db.execute("UPDATE shop_stock SET remaining=remaining-1,updated_at=? WHERE item_key=?", (now_iso(), item.key))
            await db.execute("""
            INSERT INTO shop_cooldowns VALUES(?,?,?)
            ON CONFLICT(discord_id,item_key) DO UPDATE SET used_at=excluded.used_at
            """, (user_id, item.key, now_iso()))
        await db.execute("""
        INSERT INTO shop_purchases(discord_id,gamertag,item_key,item_name,price,success,detail,purchased_at)
        VALUES(?,?,?,?,?,?,?,?)
        """, (user_id, gamertag, item.key, item.name, item.price, int(delivered), detail[:1800], now_iso()))
        await db.commit()
    return True, "ok"


async def make_item_embed(user_id: int, item: Item):
    data = await wallet(user_id)
    stock = await stock_for(item)
    left = await cooldown_left(user_id, item)
    level, title = rep_level(data["reputation_xp"])
    e = discord.Embed(title=f"{item.emoji} {item.name}", description=item.description, color=COLOR)
    e.add_field(name="Price", value=f"🪙 **{item.price:,} SC**")
    e.add_field(name="Stock", value="∞" if stock is None else f"**{stock}** left")
    e.add_field(name="Cooldown", value="None" if not item.cooldown else ("Ready" if left <= 0 else fmt(left)))
    e.add_field(name="Wallet", value=f"🪙 **{data['balance']:,} SC**")
    e.add_field(name="Reputation", value=f"**{title}** · Level {level}")
    if item.rep_required:
        e.add_field(name="Required", value=f"Merchant level **{item.rep_required}**")
    e.set_footer(text="Sanity2X Market • Earned currency • Vanilla 2x friendly")
    return e


class ItemSelect(discord.ui.Select):
    def __init__(self, view: "MarketView", category: str):
        self.market = view
        options = [
            discord.SelectOption(label=x.name, value=x.key, emoji=x.emoji, description=f"{x.price:,} SC • {x.description}"[:100])
            for x in category_items(category)[:25]
        ] or [discord.SelectOption(label="No items", value="none")]
        super().__init__(placeholder="Choose an item", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.defer()
            return
        self.market.selected = self.values[0]
        await interaction.response.edit_message(embed=await make_item_embed(interaction.user.id, ITEMS[self.values[0]]), view=self.market)


class CategorySelect(discord.ui.Select):
    def __init__(self, view: "MarketView"):
        self.market = view
        super().__init__(
            placeholder="Browse departments",
            options=[discord.SelectOption(label=name, value=key, emoji=emoji) for key, (emoji, name) in CATEGORIES.items()],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        self.market.selected = None
        for child in list(self.market.children):
            if isinstance(child, ItemSelect):
                self.market.remove_item(child)
        self.market.add_item(ItemSelect(self.market, category))
        emoji, name = CATEGORIES[category]
        text = "\n".join(f"{x.emoji} **{x.name}** — 🪙 {x.price:,} SC" for x in category_items(category))
        await interaction.response.edit_message(embed=discord.Embed(title=f"{emoji} {name}", description=text or "Empty", color=COLOR), view=self.market)


class MarketView(discord.ui.View):
    def __init__(self, bot, owner_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.owner_id = owner_id
        self.selected = None
        self.add_item(CategorySelect(self))
        self.add_item(ItemSelect(self, "featured"))

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Use `/shop` to open your own menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Buy now", emoji="🛒", style=discord.ButtonStyle.success, row=2)
    async def buy(self, interaction, button):
        if not self.selected:
            await interaction.response.send_message("Select an item first.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        item = ITEMS[self.selected]
        link = await get_link_by_discord(interaction.user.id)
        if not link:
            await interaction.followup.send("Use `/link` before buying.", ephemeral=True)
            return
        data = await wallet(interaction.user.id)
        level, _ = rep_level(data["reputation_xp"])
        if data["balance"] < item.price:
            await interaction.followup.send(f"You need **{item.price-data['balance']:,} more SC**.", ephemeral=True)
            return
        if level < item.rep_required:
            await interaction.followup.send(f"Requires merchant level **{item.rep_required}**.", ephemeral=True)
            return
        current_stock = await stock_for(item)
        if current_stock is not None and current_stock <= 0:
            await interaction.followup.send("Sold out.", ephemeral=True)
            return
        left = await cooldown_left(interaction.user.id, item)
        if left > 0:
            await interaction.followup.send(f"Cooldown: **{fmt(left)}**.", ephemeral=True)
            return
        gamertag = str(link["gamertag"])
        delivered, detail = await deliver(self.bot, gamertag, item)
        committed, reason = await checkout(interaction.user.id, gamertag, item, delivered, detail)
        if not committed:
            await interaction.followup.send("Checkout changed. No SC was taken. Retry.", ephemeral=True)
        elif not delivered:
            log.error("Delivery failed: %s", detail)
            await interaction.followup.send("Delivery failed and **no SC was taken**.", ephemeral=True)
        else:
            balance = (await wallet(interaction.user.id))["balance"]
            await interaction.followup.send(f"✅ Delivered **{item.name}** to `{gamertag}`.\n🪙 Balance: **{balance:,} SC**", ephemeral=True)

    @discord.ui.button(label="Wishlist", emoji="❤️", style=discord.ButtonStyle.secondary, row=2)
    async def wish(self, interaction, button):
        if not self.selected:
            await interaction.response.send_message("Select an item first.", ephemeral=True)
            return
        async with aiosqlite.connect(DATABASE_PATH) as db:
            row = await (await db.execute("SELECT 1 FROM shop_wishlist WHERE discord_id=? AND item_key=?", (interaction.user.id, self.selected))).fetchone()
            if row:
                await db.execute("DELETE FROM shop_wishlist WHERE discord_id=? AND item_key=?", (interaction.user.id, self.selected))
                message = "Removed from wishlist."
            else:
                await db.execute("INSERT INTO shop_wishlist VALUES(?,?,?)", (interaction.user.id, self.selected, now_iso()))
                message = "Added to wishlist."
            await db.commit()
        await interaction.response.send_message(message, ephemeral=True)


class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        await init_db()

    @app_commands.command(name="shop", description="Open the Sanity2X coin market.")
    async def shop(self, interaction: discord.Interaction):
        data = await wallet(interaction.user.id)
        text = "\n".join(f"{x.emoji} **{x.name}** — 🪙 {x.price:,} SC" for x in category_items("featured"))
        e = discord.Embed(
            title="🏪 Sanity2X Market",
            description=f"Earned currency only. No real-money checkout.\n\n**Balance:** 🪙 {data['balance']:,} SC\n\n**Featured**\n{text}",
            color=COLOR,
        )
        await interaction.response.send_message(embed=e, view=MarketView(self.bot, interaction.user.id), ephemeral=True)

    @app_commands.command(name="wallet", description="View your Sanity Coin wallet.")
    async def wallet_cmd(self, interaction: discord.Interaction):
        data = await wallet(interaction.user.id)
        level, title = rep_level(data["reputation_xp"])
        e = discord.Embed(title="🪙 Sanity Wallet", color=COLOR)
        e.add_field(name="Balance", value=f"**{data['balance']:,} SC**")
        e.add_field(name="Earned", value=f"{data['lifetime_earned']:,} SC")
        e.add_field(name="Spent", value=f"{data['lifetime_spent']:,} SC")
        e.add_field(name="Rank", value=f"{title} · Level {level}", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="daily", description="Claim daily Sanity Coins.")
    async def daily(self, interaction: discord.Interaction):
        data = await wallet(interaction.user.id)
        raw = data.get("daily_claimed_at")
        if raw:
            left = int((datetime.fromisoformat(raw) + timedelta(hours=24) - now()).total_seconds())
            if left > 0:
                await interaction.response.send_message(f"Daily available in **{fmt(left)}**.", ephemeral=True)
                return
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
            UPDATE shop_wallets SET balance=balance+?,lifetime_earned=lifetime_earned+?,daily_claimed_at=?
            WHERE discord_id=?
            """, (DAILY_REWARD, DAILY_REWARD, now_iso(), interaction.user.id))
            await db.commit()
        balance = (await wallet(interaction.user.id))["balance"]
        await interaction.response.send_message(f"✅ Claimed **{DAILY_REWARD:,} SC**.\n🪙 Balance: **{balance:,} SC**", ephemeral=True)

    @app_commands.command(name="history", description="View recent shop purchases.")
    async def history(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("""
            SELECT item_name,price,success FROM shop_purchases
            WHERE discord_id=? ORDER BY purchased_at DESC LIMIT 10
            """, (interaction.user.id,))).fetchall()
        text = "\n".join(f"{'✅' if r['success'] else '❌'} **{r['item_name']}** — {r['price']:,} SC" for r in rows) or "No purchases yet."
        await interaction.response.send_message(embed=discord.Embed(title="📜 Purchase History", description=text, color=COLOR), ephemeral=True)

    @app_commands.command(name="wishlist", description="View your wishlist.")
    async def wishlist(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DATABASE_PATH) as db:
            rows = await (await db.execute("SELECT item_key FROM shop_wishlist WHERE discord_id=? ORDER BY added_at DESC", (interaction.user.id,))).fetchall()
        saved = [ITEMS[r[0]] for r in rows if r[0] in ITEMS]
        text = "\n".join(f"{x.emoji} **{x.name}** — {x.price:,} SC" for x in saved) or "Wishlist is empty."
        await interaction.response.send_message(embed=discord.Embed(title="❤️ Wishlist", description=text, color=COLOR), ephemeral=True)

    @app_commands.command(name="givecoins", description="Admin: give or remove Sanity Coins.")
    @app_commands.default_permissions(administrator=True)
    async def givecoins(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, -1000000, 1000000]):
        balance = await change_coins(member.id, amount)
        await interaction.response.send_message(f"{member.mention}: **{amount:+,} SC**. Balance: **{balance:,} SC**", ephemeral=True)

    @app_commands.command(name="restock", description="Admin: reset limited stock.")
    @app_commands.default_permissions(administrator=True)
    async def restock(self, interaction: discord.Interaction, item_key: str, amount: app_commands.Range[int, 0, 10000]):
        if item_key not in ITEMS:
            await interaction.response.send_message("Unknown item key.", ephemeral=True)
            return
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("""
            INSERT INTO shop_stock VALUES(?,?,?)
            ON CONFLICT(item_key) DO UPDATE SET remaining=excluded.remaining,updated_at=excluded.updated_at
            """, (item_key, amount, now_iso()))
            await db.commit()
        await interaction.response.send_message(f"Restocked `{item_key}` to **{amount}**.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Shop(bot))
