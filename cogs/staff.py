import json

import discord
from discord import app_commands
from discord.ext import commands

from services.database import delete_link, get_link_by_discord
from services.helpers import get_package_for_member, is_staff
from services.rewards import handle_reward_trigger


class StaffCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def allowed(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False

        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ Staff only.", ephemeral=True)
            return False

        return True

    @app_commands.command(name="lookup", description="Staff: look up a linked account.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def lookup(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not await self.allowed(interaction):
            return

        row = await get_link_by_discord(member.id)

        if not row:
            await interaction.response.send_message(
                f"❌ {member.mention} is not linked.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                f"**Member:** {member.mention}\n"
                f"**Gamertag:** `{row['gamertag']}`\n"
                f"**Platform:** `{row['platform'].title()}`\n"
                f"**VIP:** `{get_package_for_member(member) or 'None'}`"
            ),
            ephemeral=True,
        )

    @app_commands.command(name="forceunlink", description="Staff: remove a linked account.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def forceunlink(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not await self.allowed(interaction):
            return

        deleted = await delete_link(member.id)

        if deleted:
            try:
                await member.edit(nick=None, reason=f"Unlinked by {interaction.user}")
            except discord.HTTPException:
                pass

        await interaction.response.send_message(
            "✅ Link removed." if deleted else "❌ Member was not linked.",
            ephemeral=True,
        )

    @app_commands.command(name="testreward", description="Staff: test a VIP reward.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def testreward(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        if not await self.allowed(interaction):
            return

        row = await get_link_by_discord(member.id)

        if not row:
            await interaction.response.send_message(
                "❌ That member is not linked.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        result = await handle_reward_trigger(
            self.bot,
            self.bot.rcon_service,
            row["gamertag"],
            "I Need Wood",
        )

        await interaction.followup.send(
            f"```json\n{json.dumps(result, indent=2)[:1800]}\n```",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(StaffCog(bot))
