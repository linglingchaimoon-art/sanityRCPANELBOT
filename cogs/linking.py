import discord
from discord.ext import commands

from config import LINKED_NICKNAME_PREFIX
from services.database import get_link_by_discord, save_link
from services.helpers import get_package_for_member, set_nickname


class LinkModal(discord.ui.Modal):
    gamertag = discord.ui.TextInput(
        label="Exact PSN or Xbox gamertag",
        placeholder="Enter the exact name shown in Rust",
        min_length=2,
        max_length=32,
    )

    def __init__(self, platform: str):
        super().__init__(title=f"Link {platform.title()} account")
        self.platform = platform

    async def on_submit(self, interaction: discord.Interaction) -> None:
        existing = await get_link_by_discord(interaction.user.id)

        if existing:
            await interaction.response.send_message(
                f"❌ You are already linked to `{existing['gamertag']}`.",
                ephemeral=True,
            )
            return

        gamertag = " ".join(str(self.gamertag).strip().split())

        try:
            await save_link(
                interaction.user.id,
                str(interaction.user),
                self.platform,
                gamertag,
            )
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        nickname_note = ""

        if isinstance(interaction.user, discord.Member):
            success, result = await set_nickname(
                interaction.user,
                LINKED_NICKNAME_PREFIX,
                gamertag,
                "Sanity2X account linked",
            )

            nickname_note = (
                f"\nYour nickname is now **{result}**."
                if success
                else f"\n⚠️ {result}"
            )

        await interaction.response.send_message(
            f"✅ Linked to `{gamertag}`.{nickname_note}",
            ephemeral=True,
        )


class PlatformSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Choose your platform",
            options=[
                discord.SelectOption(label="PlayStation", value="playstation", emoji="🎮"),
                discord.SelectOption(label="Xbox", value="xbox", emoji="🟢"),
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(LinkModal(self.values[0]))


class LinkView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(PlatformSelect())


class LinkingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(
        name="link",
        description="Link your Discord account to your Rust gamertag.",
    )
    @discord.app_commands.guild_only()
    async def link(self, interaction: discord.Interaction) -> None:
        existing = await get_link_by_discord(interaction.user.id)

        if existing:
            await interaction.response.send_message(
                f"❌ You are already linked to `{existing['gamertag']}`.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Choose your platform and enter your exact in-game gamertag.",
            view=LinkView(),
            ephemeral=True,
        )

    @discord.app_commands.command(
        name="linked",
        description="View your linked account.",
    )
    @discord.app_commands.guild_only()
    async def linked(self, interaction: discord.Interaction) -> None:
        row = await get_link_by_discord(interaction.user.id)

        if not row:
            await interaction.response.send_message(
                "❌ You are not linked. Use `/link`.",
                ephemeral=True,
            )
            return

        package = None

        if isinstance(interaction.user, discord.Member):
            package = get_package_for_member(interaction.user)

        embed = discord.Embed(
            title="🔗 Your Linked Account",
            color=discord.Color.green(),
        )
        embed.add_field(name="Gamertag", value=f"`{row['gamertag']}`", inline=False)
        embed.add_field(name="Platform", value=row["platform"].title(), inline=True)
        embed.add_field(name="VIP", value=package or "None", inline=True)
        embed.add_field(name="Status", value="✅ Linked", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(LinkingCog(bot))
