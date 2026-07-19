import logging
import os

import discord
from discord.ext import commands

from config import DISCORD_TOKEN, GUILD_ID, validate_config
from services.database import init_database
from services.rcon import RconService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

database_path = os.getenv(
    "DATABASE_PATH",
    "/data/sanity2x.db",
)

logger.info(
    "Using SQLite database: %s",
    database_path,
)


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
            "cogs.shop",
        ]

        for extension in extensions:
            try:
                await self.load_extension(extension)

                logging.info(
                    "Loaded extension: %s",
                    extension,
                )

            except Exception:
                logging.exception(
                    "Failed to load extension: %s",
                    extension,
                )
                raise

        guild = discord.Object(
            id=self.guild_id
        )

        # Copy global slash commands into your server.
        self.tree.copy_global_to(
            guild=guild
        )

        try:
            synced = await self.tree.sync(
                guild=guild
            )

            logging.info(
                "Synced %s slash command(s) to guild %s.",
                len(synced),
                self.guild_id,
            )

            for command in synced:
                logging.info(
                    "Synced slash command: /%s",
                    command.name,
                )

        except Exception:
            logging.exception(
                "Failed to sync slash commands."
            )
            raise

        self.rcon_service.start()

    async def on_ready(self) -> None:
        if self.user is None:
            return

        logging.info(
            "Logged in as %s (%s)",
            self.user,
            self.user.id,
        )

        logging.info(
            "Bot is connected to %s server(s).",
            len(self.guilds),
        )

        for guild in self.guilds:
            logging.info(
                "Connected server: %s (%s)",
                guild.name,
                guild.id,
            )

    async def close(self) -> None:
        await self.rcon_service.stop()
        await super().close()


def main() -> None:
    validate_config()

    bot = Sanity2XBot()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()