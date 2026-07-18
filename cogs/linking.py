import discord
from discord import app_commands
from discord.ext import commands

from config import LINKED_NICKNAME_PREFIX
from services.database import (
    delete_link,
    get_link_by_discord,
    get_link_by_gamertag,
    save_link,
)
from services.helpers import set_nickname


class LinkModal(discord.ui.Modal):
    def __init__(self, cog: "LinkingCog") -> None:
        super().__init__(
            title="Link PlayStation or Xbox account",
            timeout=300,
        )

        self.cog = cog

        self.gamertag = discord.ui.TextInput(
            label="Exact PSN or Xbox gamertag",
            placeholder="Example: Mxlky_TJ",
            required=True,
            min_length=2,
            max_length=32,
        )

        self.add_item(self.gamertag)

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ This command can only be used inside the server.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ Your Discord member information could not be read.",
                ephemeral=True,
            )
            return

        gamertag = " ".join(
            str(self.gamertag.value).strip().split()
        )

        if not gamertag:
            await interaction.response.send_message(
                "❌ Enter a valid PSN or Xbox gamertag.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        existing_discord_link = await get_link_by_discord(
            interaction.user.id
        )

        existing_gamertag_link = await get_link_by_gamertag(
            gamertag
        )

        if existing_gamertag_link:
            linked_discord_id = int(
                existing_gamertag_link["discord_id"]
            )

            if linked_discord_id != interaction.user.id:
                await interaction.followup.send(
                    (
                        "❌ That gamertag is already linked to "
                        "another Discord account.\n"
                        "Contact staff if you believe this is incorrect."
                    ),
                    ephemeral=True,
                )
                return

        try:
            await save_link(
                interaction.user.id,
                gamertag,
            )
        except Exception as exc:
            self.cog.bot.logger.exception(
                "Failed to save account link"
            ) if hasattr(self.cog.bot, "logger") else None

            await interaction.followup.send(
                (
                    "❌ The bot could not save your gamertag.\n"
                    f"Error: `{type(exc).__name__}`"
                ),
                ephemeral=True,
            )
            return

        nickname_changed, nickname_result = await set_nickname(
            interaction.user,
            LINKED_NICKNAME_PREFIX,
            gamertag,
            "Linked Rust Console gamertag",
        )

        if existing_discord_link:
            message = (
                f"✅ Your linked gamertag was updated to "
                f"`{gamertag}`."
            )
        else:
            message = (
                f"✅ Your Discord account is now linked to "
                f"`{gamertag}`."
            )

        if nickname_changed:
            message += (
                f"\nYour server nickname is now "
                f"`{nickname_result}`."
            )
        else:
            message += (
                "\n⚠️ The gamertag was saved, but your nickname "
                f"could not be changed:\n{nickname_result}"
            )

        await interaction.followup.send(
            message,
            ephemeral=True,
        )

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        message = (
            "❌ Something went wrong while saving your gamertag. "
            "Please try again or contact staff."
        )

        if interaction.response.is_done():
            await interaction.followup.send(
                message,
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True,
            )


class LinkingCog(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="link",
        description="Link your Discord account to your PSN or Xbox gamertag.",
    )
    @app_commands.guild_only()
    async def link(
        self,
        interaction: discord.Interaction,
    ) -> None:
        existing_link = await get_link_by_discord(
            interaction.user.id
        )

        if existing_link:
            gamertag = existing_link["gamertag"]

            embed = discord.Embed(
                title="🔗 Account already linked",
                description=(
                    f"Your saved gamertag is `{gamertag}`.\n\n"
                    "Use `/updatelink` to change it or "
                    "`/unlink` to remove it."
                ),
                color=discord.Color.green(),
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            LinkModal(self)
        )

    @app_commands.command(
        name="updatelink",
        description="Change your saved PSN or Xbox gamertag.",
    )
    @app_commands.guild_only()
    async def updatelink(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await interaction.response.send_modal(
            LinkModal(self)
        )

    @app_commands.command(
        name="linkedaccount",
        description="View your currently linked gamertag.",
    )
    @app_commands.guild_only()
    async def linkedaccount(
        self,
        interaction: discord.Interaction,
    ) -> None:
        link = await get_link_by_discord(
            interaction.user.id
        )

        if not link:
            await interaction.response.send_message(
                "❌ You have not linked a gamertag yet. Use `/link`.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                f"🔗 Your linked PSN or Xbox gamertag is "
                f"`{link['gamertag']}`."
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="unlink",
        description="Remove your linked PSN or Xbox gamertag.",
    )
    @app_commands.guild_only()
    async def unlink(
        self,
        interaction: discord.Interaction,
    ) -> None:
        link = await get_link_by_discord(
            interaction.user.id
        )

        if not link:
            await interaction.response.send_message(
                "❌ You do not currently have a linked gamertag.",
                ephemeral=True,
            )
            return

        deleted = await delete_link(
            interaction.user.id
        )

        if deleted:
            await interaction.response.send_message(
                (
                    f"✅ Removed the link to "
                    f"`{link['gamertag']}`."
                ),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "❌ The linked account could not be removed.",
                ephemeral=True,
            )


async def setup(bot) -> None:
    await bot.add_cog(
        LinkingCog(bot)
    )