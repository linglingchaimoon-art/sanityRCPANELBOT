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
            try:
                await self.load_extension(extension)
                logging.info("Loaded extension: %s", extension)
            except Exception:
                logging.exception(
                    "Failed to load extension: %s",
                    extension,
                )
                raise

        guild = discord.Object(id=self.guild_id)

        try:
            synced = await self.tree.sync(guild=guild)
            logging.info(
                "Synced %s guild slash command(s).",
                len(synced),
            )
        except Exception:
            logging.exception("Failed to sync slash commands.")
            raise

        self.rcon_service.start()

    async def on_ready(self) -> None:
        logging.info(
            "Logged in as %s (%s)",
            self.user,
            self.user.id if self.user else "unknown",
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