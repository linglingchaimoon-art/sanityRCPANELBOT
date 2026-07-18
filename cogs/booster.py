import discord
from discord import app_commands
from discord.ext import commands

from config import BOOSTER_CUSTOM_ROLE_ID, BOOSTER_NICKNAME_PREFIX
from services.database import get_link_by_discord
from services.helpers import set_nickname


def is_server_booster(member: discord.Member) -> bool:
    return (
        member.premium_since is not None
        or any(role.is_premium_subscriber() for role in member.roles)
    )


class BoosterClaimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim Booster Perks",
        style=discord.ButtonStyle.primary,
        emoji="💎",
        custom_id="sanity2x:booster:claim:clean",
    )
    async def claim(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not isinstance(interaction.user, discord.Member):
            return

        member = interaction.user

        if not is_server_booster(member):
            await interaction.response.send_message(
                "❌ You are not currently boosting Sanity2X.",
                ephemeral=True,
            )
            return

        link = await get_link_by_discord(member.id)

        if not link:
            await interaction.response.send_message(
                "❌ Link your account first using `/link`.",
                ephemeral=True,
            )
            return

        role = member.guild.get_role(BOOSTER_CUSTOM_ROLE_ID)

        if role is None:
            await interaction.response.send_message(
                "❌ The custom booster role is not configured correctly.",
                ephemeral=True,
            )
            return

        try:
            if role not in member.roles:
                await member.add_roles(role, reason="Verified Sanity2X booster")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Give the bot Manage Roles and place its role above the booster role.",
                ephemeral=True,
            )
            return

        nick_success, nick_result = await set_nickname(
            member,
            BOOSTER_NICKNAME_PREFIX,
            link["gamertag"],
            "Verified Sanity2X booster",
        )

        embed = discord.Embed(
            title="💎 Booster Perks Activated",
            description="Thank you for boosting **Sanity2X**!",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Role", value=f"✅ {role.mention}", inline=False)
        embed.add_field(
            name="Nickname",
            value=f"✅ {nick_result}" if nick_success else f"⚠️ {nick_result}",
            inline=False,
        )
        embed.add_field(
            name="Benefits",
            value=(
                "• Booster Lounge access\n"
                "• Send images and attachments\n"
                "• Embed links\n"
                "• External emojis and stickers\n"
                "• GIFs and reactions\n"
                "• Booster giveaways and events\n"
                "• Priority support"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class BoosterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(BoosterClaimView())

    @app_commands.command(
        name="boosterpanel",
        description="Administrator: post the booster perks panel.",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def boosterpanel(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Administrator permission is required.",
                ephemeral=True,
            )
            return

        if interaction.channel is None:
            return

        embed = discord.Embed(
            title="💎 Sanity2X Booster Perks",
            description="Boost the server and claim your exclusive Discord perks.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Benefits",
            value=(
                "• Automatic Sanity2X Booster role\n"
                "• Special 💎 nickname tag\n"
                "• Booster Lounge access\n"
                "• Send images and attachments\n"
                "• Embed links\n"
                "• External emojis and stickers\n"
                "• GIFs and reactions\n"
                "• Booster-only events and giveaways\n"
                "• Priority support"
            ),
            inline=False,
        )
        embed.add_field(
            name="How to Claim",
            value=(
                "1. Boost the server.\n"
                "2. Link your account with `/link`.\n"
                "3. Press the button below."
            ),
            inline=False,
        )

        await interaction.channel.send(embed=embed, view=BoosterClaimView())
        await interaction.response.send_message(
            "✅ Booster panel posted.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(BoosterCog(bot))
