import asyncio
import logging

import discord
from discord.ext import commands

from config import DISCORD_TOKEN, GUILD_ID, validate_config
from services.database import init_database
from services.rcon import RconService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("sanity2x.main")


class Sanity2XBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

        self.guild_id = GUILD_ID
        self.rcon_service = RconService(self)

    async def setup_hook(self) -> None:
        await init_database()

        extensions = [
            "cogs.linking",
            "cogs.staff",
            "cogs.booster",
            "cogs.loa",
            "cogs.admin",
        ]

        for extension in extensions:
            await self.load_extension(extension)
            logger.info("Loaded extension: %s", extension)

        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)

        logger.info("Synced %s slash commands", len(synced))

        self.rcon_service.start()

    async def close(self) -> None:
        await self.rcon_service.stop()
        await super().close()


bot = Sanity2XBot()


@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s", bot.user)


async def main() -> None:
    validate_config()

    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
