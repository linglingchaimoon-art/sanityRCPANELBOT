import discord
from discord import app_commands
from discord.ext import commands

from config import RCON_MOCK_COMMANDS
from services.database import (
    get_link_by_discord,
    reset_action_cooldown,
)


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="botstatus",
        description="Administrator: view bot and RCON status.",
    )
    @app_commands.default_permissions(
        administrator=True
    )
    @app_commands.guild_only()
    async def botstatus(
        self,
        interaction: discord.Interaction,
    ) -> None:
        rcon_connected = (
            self.bot.rcon_service.websocket is not None
        )

        if RCON_MOCK_COMMANDS:
            rcon_status = "🧪 Mock mode"
        elif rcon_connected:
            rcon_status = "✅ Connected"
        else:
            rcon_status = "❌ Disconnected"

        embed = discord.Embed(
            title="🛠️ Sanity2X Bot Status",
            color=(
                discord.Color.green()
                if rcon_connected or RCON_MOCK_COMMANDS
                else discord.Color.red()
            ),
        )

        embed.add_field(
            name="Discord",
            value="✅ Connected",
            inline=True,
        )

        embed.add_field(
            name="RCON",
            value=rcon_status,
            inline=True,
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

        selected_action = (
            None
            if action.value == "all"
            else action.value
        )

        deleted = await reset_action_cooldown(
            link["gamertag"],
            selected_action,
        )

        await interaction.response.send_message(
            (
                f"✅ Reset **{action.name}** for "
                f"`{link['gamertag']}`. "
                f"Removed {deleted} stored claim(s)."
            ),
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(
        AdminCog(bot)
    )