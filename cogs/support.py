import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import asyncio

SUPPORT_PANEL_FILE = "data/support_panel.json"
SUPPORT_TICKETS_FILE = "data/support_tickets.json"

TRANSCRIPT_CHANNEL_ID = 1527113189458706463

# SUPPORT_BANNER_URL = "/Users/phatje/Desktop/ChatGPT Image 26 jun 2026, 08_00_45 kopie.png"

INGAME_STAFF_ROLE_IDS = [
    1520644874246819970,
    1520645054367273143,
    1520645243475722360,
    1520630982443663511,
    1520630990760837171,
    1520630994892361748,
]

DISCORD_STAFF_ROLE_IDS = [
    1520630997581041816,
    1520630996947697837,
    1520630996318290121,
    1520630982443663511,
    1520630990760837171,
    1520630994892361748,
]

STAFF_ROLE_IDS = INGAME_STAFF_ROLE_IDS + DISCORD_STAFF_ROLE_IDS

CATEGORY_IDS = {
    "Purchase Support": 1520784322574024864,
    "General Support": 1520784444204515358,
    "Report Player": 1520784444204515358,
    "In-Game Problem": 1520784444204515358,
    "Zorp Issue": 1520784444204515358,
    "Linking / Unlinking": 1520784444204515358,
}

INGAME_ONLY_CATEGORIES = [
    "Report Player",
    "In-Game Problem",
    "Zorp Issue"
]

creating_tickets = set()


def ensure_data():
    os.makedirs("data", exist_ok=True)
    for file in [SUPPORT_PANEL_FILE, SUPPORT_TICKETS_FILE]:
        if not os.path.exists(file):
            with open(file, "w") as f:
                json.dump({}, f, indent=4)


def load_json(file):
    ensure_data()
    with open(file, "r") as f:
        return json.load(f)


def save_json(file, data):
    ensure_data()
    with open(file, "w") as f:
        json.dump(data, f, indent=4)


def clean_name(name):
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789-"
    name = name.lower().replace(" ", "-").replace("_", "-")
    return "".join(c for c in name if c in allowed)


def category_to_prefix(category):
    return category.lower().replace("/", "").replace(" ", "-")


def is_staff_member(member):
    return any(role.id in STAFF_ROLE_IDS for role in member.roles)


def build_overwrites(guild, user, selected):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, attach_files=True, embed_links=True)
    }

    role_ids = INGAME_STAFF_ROLE_IDS if selected in INGAME_ONLY_CATEGORIES else STAFF_ROLE_IDS

    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, attach_files=True, embed_links=True)

    return overwrites


def build_ping_text(guild, selected):
    role_ids = INGAME_STAFF_ROLE_IDS if selected in INGAME_ONLY_CATEGORIES else STAFF_ROLE_IDS
    mentions = []

    for role_id in role_ids:
        role = guild.get_role(role_id)
        if role:
            mentions.append(role.mention)

    return " ".join(mentions)


def create_ticket_embed(category, user, channel):
    formats = {
        "Purchase Support": (
            "💳 Purchase Support",
            "🛒 **What did you purchase?**\n> Kit / VIP / item / service\n\n"
            "🌍 **Server**\n> Example: Solo / Duo / Main\n\n"
            "🎮 **Gamertag**\n> PSN / Xbox username\n\n"
            "🧾 **Order ID / Proof**\n> Send receipt or screenshot\n\n"
            "📝 **Issue**\n> Explain what went wrong"
        ),
        "General Support": (
            "💬 General Support",
            "❓ **Question / Issue**\n> Explain what you need help with\n\n"
            "🌍 **Server**\n> If related to a server, mention it here\n\n"
            "📎 **Extra Info**\n> Screenshots, clips, or more details"
        ),
        "Report Player": (
            "🚨 Report Player",
            "🌍 **Server**\n> Example: Solo / Duo / Main\n\n"
            "🎮 **Reported Player**\n> Gamertag / PSN / Xbox username\n\n"
            "📍 **Grid Location**\n> Example: G12\n\n"
            "⏰ **Time of Incident**\n> Approximate time it happened\n\n"
            "⚠️ **Rule Broken**\n> Cheating / Exploiting / Toxicity / Griefing / Zorp Abuse / Other\n\n"
            "📝 **What Happened?**\n> Describe exactly what happened\n\n"
            "📎 **Evidence**\n> Upload screenshots or video clips"
        ),
        "In-Game Problem": (
            "🎮 In-Game Problem",
            "🌍 **Server**\n> Which server are you playing on?\n\n"
            "🎮 **Gamertag**\n> PSN / Xbox username\n\n"
            "📍 **Location / Grid**\n> Where did it happen?\n\n"
            "📦 **Lost Items / Base Issue**\n> What was lost or affected?\n\n"
            "⏰ **When Did It Happen?**\n> Approximate time/date\n\n"
            "📎 **Evidence**\n> Screenshots or clips if possible"
        ),
        "Zorp Issue": (
            "🟢 Zorp Issue",
            "🌍 **Server**\n> Which server is your Zorp on?\n\n"
            "🎮 **Gamertag**\n> PSN / Xbox username\n\n"
            "🏠 **Base / Zorp Location**\n> Grid location or area\n\n"
            "🛡️ **Issue Type**\n> Protection / safe zone / command / radius / other\n\n"
            "📝 **What Happened?**\n> Explain the issue clearly\n\n"
            "📎 **Evidence**\n> Screenshots or clips if available"
        ),
        "Linking / Unlinking": (
            "🔗 Linking / Unlinking",
            "🎮 **Rust Gamertag**\n> PSN / Xbox username\n\n"
            "🔗 **Request Type**\n> Linking or unlinking?\n\n"
            "👤 **Current Account**\n> What account is currently linked?\n\n"
            "✅ **New Account**\n> What should be linked instead?\n\n"
            "📎 **Proof**\n> Screenshot proof if needed"
        )
    }

    title, info = formats.get(category, formats["General Support"])

    embed = discord.Embed(
        title=title,
        description=(
            f"Hey {user.mention}, thanks for contacting **Sanity2X Support**.\n"
            "Please fill out the format below so staff can help faster.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{info}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📊 **Status**\n"
            "🟠 OPEN\n\n"
            "👤 **Claimed By**\n"
            "*Unclaimed*\n\n"
            "🛡️ Staff will respond as soon as possible."
        ),
        color=0xFFA500
    )

    embed.set_footer(text=f"Sanity2X • Support Ticket #{channel.id}")
    return embed


class SupportDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Purchase Support", description="Store, VIP, kit, payment, or delivery issue.", emoji="💳"),
            discord.SelectOption(label="General Support", description="General questions or server help.", emoji="💬"),
            discord.SelectOption(label="Report Player", description="Report rule breaking, toxicity, cheating, or griefing.", emoji="🚨"),
            discord.SelectOption(label="In-Game Problem", description="Problems with items, base, server, or gameplay.", emoji="🎮"),
            discord.SelectOption(label="Zorp Issue", description="Problems with Zorp, safe zone, protection, or commands.", emoji="🟢"),
            discord.SelectOption(label="Linking / Unlinking", description="Link or unlink your Discord, Rust, or store account.", emoji="🔗"),
        ]

        super().__init__(
            placeholder="📬 Select a support category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="sanity2x_support_dropdown"
        )

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)

        if user_id in creating_tickets:
            await interaction.response.send_message("⏳ Your ticket is already being created. Please wait.", ephemeral=True)
            return

        creating_tickets.add(user_id)

        try:
            await interaction.response.defer(ephemeral=True)

            guild = interaction.guild
            user = interaction.user
            selected = self.values[0]

            await interaction.message.edit(view=SupportPanelView())

            tickets = load_json(SUPPORT_TICKETS_FILE)

            if user_id in tickets:
                old_channel = guild.get_channel(tickets[user_id])
                if old_channel:
                    await interaction.followup.send(f"❌ You already have an open ticket: {old_channel.mention}", ephemeral=True)
                    return

                del tickets[user_id]
                save_json(SUPPORT_TICKETS_FILE, tickets)

            category_id = CATEGORY_IDS.get(selected)
            ticket_category = guild.get_channel(category_id) if category_id else None

            if ticket_category is None or not isinstance(ticket_category, discord.CategoryChannel):
                await interaction.followup.send(f"❌ Category for **{selected}** was not found. Check CATEGORY_IDS.", ephemeral=True)
                return

            channel = await guild.create_text_channel(
                name=f"{category_to_prefix(selected)}-{clean_name(user.name)}",
                category=ticket_category,
                overwrites=build_overwrites(guild, user, selected)
            )

            tickets[user_id] = channel.id
            save_json(SUPPORT_TICKETS_FILE, tickets)

            await channel.send(
                content=f"{build_ping_text(guild, selected)}\n👋 **New {selected} ticket from {user.mention}**",
                embed=create_ticket_embed(selected, user, channel),
                view=SupportTicketView(),
                allowed_mentions=discord.AllowedMentions(roles=True, users=True)
            )

            await interaction.followup.send(f"✅ Your **{selected}** ticket has been created: {channel.mention}", ephemeral=True)

        finally:
            creating_tickets.discard(user_id)


class SupportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SupportDropdown())


class SupportTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim Ticket", emoji="🟢", style=discord.ButtonStyle.success, custom_id="sanity2x_claim_ticket")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            await interaction.response.send_message("❌ You do not have permission to claim tickets.", ephemeral=True)
            return

        async for message in interaction.channel.history(limit=20, oldest_first=True):
            if message.author == interaction.client.user and message.embeds:
                embed = message.embeds[0]

                if embed.description and "*Unclaimed*" not in embed.description:
                    await interaction.response.send_message("❌ This ticket is already claimed.", ephemeral=True)
                    return

                embed.description = embed.description.replace("🟠 OPEN", "🟢 CLAIMED")
                embed.description = embed.description.replace(
                    "👤 **Claimed By**\n*Unclaimed*",
                    f"👤 **Claimed By**\n{interaction.user.mention}"
                )
                embed.color = discord.Color.green()

                await message.edit(embed=embed)
                await interaction.response.send_message(f"✅ Ticket claimed by {interaction.user.mention}")
                return

        await interaction.response.send_message("❌ Could not find the ticket embed.", ephemeral=True)

    @discord.ui.button(label="Close Ticket", emoji="🔴", style=discord.ButtonStyle.danger, custom_id="sanity2x_close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff_member(interaction.user):
            await interaction.response.send_message("❌ You do not have permission to close tickets.", ephemeral=True)
            return

        await interaction.response.defer()

        async for message in interaction.channel.history(limit=20, oldest_first=True):
            if message.author == interaction.client.user and message.embeds:
                embed = message.embeds[0]

                if embed.description:
                    embed.description = embed.description.replace("🟠 OPEN", "🔴 CLOSED")
                    embed.description = embed.description.replace("🟢 CLAIMED", "🔴 CLOSED")
                    embed.color = discord.Color.red()
                    await message.edit(embed=embed)

                break

        transcript_text = ""

        async for msg in interaction.channel.history(limit=100, oldest_first=True):
            if not msg.author.bot:
                transcript_text += f"{msg.created_at.strftime('%Y-%m-%d %H:%M')} - {msg.author}: {msg.content}\n"

        file_name = f"transcript-{interaction.channel.name}.txt"

        with open(file_name, "w", encoding="utf-8") as f:
            f.write(transcript_text or "No user messages found.")

        transcript_channel = interaction.guild.get_channel(TRANSCRIPT_CHANNEL_ID)

        if transcript_channel:
            await transcript_channel.send(
                content=f"📄 Transcript for **{interaction.channel.name}**\nClosed by {interaction.user.mention}",
                file=discord.File(file_name)
            )

        tickets = load_json(SUPPORT_TICKETS_FILE)

        for uid, cid in list(tickets.items()):
            if cid == interaction.channel.id:
                del tickets[uid]
                save_json(SUPPORT_TICKETS_FILE, tickets)
                break

        countdown_msg = await interaction.channel.send(
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ **Ticket Closed Successfully**\n\n"
            "📄 Transcript has been saved.\n"
            "🗑️ This ticket will automatically close in\n\n"
            "5️⃣ **seconds...**\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        )

        numbers = {4: "4️⃣", 3: "3️⃣", 2: "2️⃣", 1: "1️⃣"}

        for seconds in range(4, 0, -1):
            await asyncio.sleep(1)
            await countdown_msg.edit(
                content=(
                    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✅ **Ticket Closed Successfully**\n\n"
                    "📄 Transcript has been saved.\n"
                    "🗑️ This ticket will automatically close in\n\n"
                    f"{numbers[seconds]} **seconds...**\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━"
                )
            )

        await asyncio.sleep(1)
        await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")


class Support(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(SupportPanelView())
        self.bot.add_view(SupportTicketView())

    def create_panel_embed(self):
        embed = discord.Embed(
            title="🛠️ SANITY2X • SUPPORT CENTER",
            description=(
                "Welcome to the official **Sanity2X Support Hub**.\n\n"
                "Need help? Select the correct category below and a **private ticket** will be created for you.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0xD32F2F
        )

        embed.add_field(name="🟢 Support Status", value="> Staff Team: **Available**\n> Average Response: **5–15 minutes**", inline=False)
        embed.add_field(name="💳 Store & Purchases", value="VIP • Kits • Missing Orders • Payments", inline=True)
        embed.add_field(name="💬 General Support", value="Questions • Discord Help • Server Info", inline=True)
        embed.add_field(name="🔗 Account Support", value="Linking • Unlinking • Account Issues", inline=True)
        embed.add_field(name="🚨 Report Player", value="Cheating • Exploiting • Toxicity • Rule Breaking", inline=True)
        embed.add_field(name="🎮 In-Game Support", value="Lost Items • Bugs • Server Issues • Gameplay Help", inline=True)
        embed.add_field(name="🛡️ Zorp Support", value="Protection • Safe Zones • Commands • Zorp Issues", inline=True)

        embed.add_field(
            name="📌 Before Opening a Ticket",
            value=(
                "📎 Include screenshots or clips when possible.\n"
                "🎮 Include your PSN/Xbox gamertag.\n"
                "🌍 Mention the server you play on.\n"
                "📝 Explain your issue clearly.\n"
                "⏳ Please be patient while staff reviews it."
            ),
            inline=False
        )

        embed.add_field(
            name="⬇️ Open Support",
            value="Use the dropdown below to choose your ticket category.",
            inline=False
        )

      #  embed.set_image(url=SUPPORT_BANNER_URL)
        embed.set_footer(text="Sanity2X • Rust Console Community • Support System")
        return embed

    @app_commands.command(name="supportpanel", description="Send or update the Sanity2X support panel.")
    @app_commands.default_permissions(administrator=True)
    async def supportpanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        panel_data = load_json(SUPPORT_PANEL_FILE)
        old_channel_id = panel_data.get("channel_id")
        old_message_id = panel_data.get("message_id")

        if old_channel_id and old_message_id:
            old_channel = interaction.guild.get_channel(old_channel_id)

            if old_channel:
                try:
                    old_message = await old_channel.fetch_message(old_message_id)
                    await old_message.edit(embed=self.create_panel_embed(), view=SupportPanelView())

                    await interaction.followup.send(f"✅ Existing support panel updated in {old_channel.mention}.", ephemeral=True)
                    return
                except Exception:
                    pass

        message = await interaction.channel.send(embed=self.create_panel_embed(), view=SupportPanelView())

        save_json(SUPPORT_PANEL_FILE, {
            "channel_id": interaction.channel.id,
            "message_id": message.id
        })

        await interaction.followup.send("✅ Support panel sent.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Support(bot))