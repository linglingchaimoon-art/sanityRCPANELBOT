from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from config import RCON_MOCK_COMMANDS
from services.database import (
    get_link_by_discord,
    reset_action_cooldown,
)


class AdminCog(commands.Cog):
    """
    Discord admin commands.

    Every response is ephemeral, and this cog never sends
    global.say messages to Rust chat.
    """

    def __init__(
        self,
        bot,
    ):
        self.bot = bot

    @app_commands.command(
        name="botstatus",
        description=(
            "Administrator: view bot and RCON status."
        ),
    )
    @app_commands.default_permissions(
        administrator=True
    )
    @app_commands.guild_only()
    async def botstatus(
        self,
        interaction: discord.Interaction,
    ) -> None:
        rcon_connected = bool(
            getattr(
                self.bot.rcon_service,
                "websocket",
                None,
            )
        )

        embed = discord.Embed(
            title="🛠️ Sanity2X Bot Status",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="Discord",
            value="✅ Connected",
            inline=True,
        )

        embed.add_field(
            name="RCON",
            value=(
                "🧪 Mock mode"
                if RCON_MOCK_COMMANDS
                else (
                    "✅ Connected"
                    if rcon_connected
                    else "❌ Disconnected"
                )
            ),
            inline=True,
        )

        embed.add_field(
            name="Privacy",
            value=(
                "🔒 Admin actions are hidden "
                "from public Rust chat."
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="resetcooldown",
        description=(
            "Administrator: reset a player's "
            "reward or teleport cooldown."
        ),
    )
    @app_commands.describe(
        member="Linked Discord member",
        action="Cooldown to reset",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="All cooldowns",
                value="all",
            ),
            app_commands.Choice(
                name="VIP",
                value="vip",
            ),
            app_commands.Choice(
                name="Diamond VIP",
                value="diamond",
            ),
            app_commands.Choice(
                name="Ultimate VIP",
                value="ultimate",
            ),
            app_commands.Choice(
                name="Outpost teleport",
                value="outpost",
            ),
        ]
    )
    @app_commands.default_permissions(
        administrator=True
    )
    @app_commands.guild_only()
    async def resetcooldown(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        action: app_commands.Choice[str],
    ) -> None:
        link = await get_link_by_discord(
            member.id
        )

        if not link:
            await interaction.response.send_message(
                "❌ That member is not linked.",
                ephemeral=True,
            )

            return

        selected = (
            None
            if action.value == "all"
            else action.value
        )

        deleted = await reset_action_cooldown(
            link["gamertag"],
            selected,
        )

        await interaction.response.send_message(
            (
                f"✅ Reset **{action.name}** for "
                f"`{link['gamertag']}`.\n"
                f"Removed **{deleted}** stored "
                "claim(s).\n\n"
                "🔒 This admin action was hidden "
                "from public Rust chat."
            ),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(
        AdminCog(bot)
    )
