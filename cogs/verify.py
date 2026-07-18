import discord
from discord.ext import commands
from discord import app_commands
import json
import os

VERIFY_ROLE_ID = 1520632776770982038  # Replace with your Verified role ID
PANEL_FILE = "data/rules_panel.json"

SERVER_BANNER_URL = "https://i.pinimg.com/736x/a0/9a/4a/a09a4a73dbd67daa71c1b874146ee29d.jpg"


def ensure_data():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(PANEL_FILE):
        with open(PANEL_FILE, "w") as f:
            json.dump({}, f, indent=4)


def load_panel():
    ensure_data()
    with open(PANEL_FILE, "r") as f:
        return json.load(f)


def save_panel(data):
    ensure_data()
    with open(PANEL_FILE, "w") as f:
        json.dump(data, f, indent=4)


class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="sanity2x_verify_button"
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(VERIFY_ROLE_ID)

        if role is None:
            await interaction.response.send_message(
                "❌ Verify role not found. Contact staff.",
                ephemeral=True
            )
            return

        if role in interaction.user.roles:
            await interaction.response.send_message(
                "✅ You are already verified.",
                ephemeral=True
            )
            return

        await interaction.user.add_roles(role)

        await interaction.response.send_message(
            "✅ You have successfully verified! Welcome to **Sanity2X**.",
            ephemeral=True
        )


class Verify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(VerifyButton())

    def create_rules_embed(self):
        embed = discord.Embed(
            title="📜 Sanity2X • Official Rules & Verification",
            description=(
                "Welcome to **Sanity2X**.\n"
                "Before entering the server, read the rules below and verify at the bottom.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "🌐 **Discord Rules**\n"
                "• Follow Discord **Terms of Service** and **Community Guidelines**.\n"
                "• No racism, hate speech, harassment, threats, or toxicity.\n"
                "• No NSFW, gore, illegal content, doxxing, or personal information.\n"
                "• No spam, mass mentions, advertising, scam links, or fake giveaways.\n\n"
                "🎮 **Rust Server Rules**\n"
                "• No cheating, scripting, exploiting, bug abuse, or third-party tools.\n"
                "• No insiding teammates, scamming trades, or abusing safe zones.\n"
                "• No excessive toxicity, slurs, harassment, or targeting players in Discord.\n"
                "• Respect event rules, raid rules, wipe rules, and staff decisions.\n"
                "• Report rule breakers with proof using the ticket system.\n\n"
                "🛡️ **Staff & Support**\n"
                "• Staff decisions are final.\n"
                "• Do not lie in tickets or waste staff time.\n"
                "• Punishment evasion can result in a permanent ban.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "✅ Click **Verify** below to accept the rules and unlock the server."
            ),
            color=0xE53935
        )

        embed.set_image(url=SERVER_BANNER_URL)
        embed.set_footer(
            text="Sanity2X • By verifying, you agree to follow all Discord and Rust server rules."
        )

        return embed

    @app_commands.command(name="rulespanel", description="Send or update the rules verification panel.")
    @app_commands.default_permissions(administrator=True)
    async def rulespanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        panel_data = load_panel()
        old_channel_id = panel_data.get("channel_id")
        old_message_id = panel_data.get("message_id")

        if old_channel_id and old_message_id:
            old_channel = interaction.guild.get_channel(old_channel_id)

            if old_channel:
                try:
                    old_message = await old_channel.fetch_message(old_message_id)

                    await old_message.edit(
                        embed=self.create_rules_embed(),
                        view=VerifyButton()
                    )

                    await interaction.followup.send(
                        f"✅ Existing rules panel updated in {old_channel.mention}.",
                        ephemeral=True
                    )
                    return

                except Exception:
                    pass

        message = await interaction.channel.send(
            embed=self.create_rules_embed(),
            view=VerifyButton()
        )

        save_panel({
            "channel_id": interaction.channel.id,
            "message_id": message.id
        })

        await interaction.followup.send(
            "✅ Rules panel sent.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Verify(bot))