import discord
from discord import app_commands
from discord.ext import commands

from config import LOA_REVIEW_CHANNEL_ID, LOA_ROLE_ID
from services.database import (
    create_loa_request,
    get_active_loa_request,
    get_loa_request,
    get_pending_loa_requests,
    update_loa_request_message,
    update_loa_status,
)
from services.helpers import is_hr


class LOAModal(discord.ui.Modal):
    reason = discord.ui.TextInput(
        label="Reason",
        placeholder="Why do you need LOA?",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=1000,
    )
    start_date = discord.ui.TextInput(
        label="Start date",
        placeholder="Example: 20 July 2026",
        max_length=50,
    )
    end_date = discord.ui.TextInput(
        label="End date",
        placeholder="Example: 27 July 2026",
        max_length=50,
    )
    extra = discord.ui.TextInput(
        label="Extra information",
        placeholder="Optional",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )

    def __init__(self, bot):
        super().__init__(title="Sanity2X LOA Request")
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member):
            return

        if interaction.guild is None:
            return

        active = await get_active_loa_request(interaction.user.id)

        if active:
            await interaction.response.send_message(
                f"❌ You already have an active LOA request. Status: `{active['status']}`",
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(LOA_REVIEW_CHANNEL_ID)

        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ LOA review channel is not configured correctly.",
                ephemeral=True,
            )
            return

        request_id = await create_loa_request(
            interaction.user.id,
            str(interaction.user),
            str(self.reason),
            str(self.start_date),
            str(self.end_date),
            str(self.extra or ""),
        )

        embed = discord.Embed(
            title="📋 New LOA Request",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Member", value=interaction.user.mention, inline=False)
        embed.add_field(
            name="Dates",
            value=f"{self.start_date} → {self.end_date}",
            inline=False,
        )
        embed.add_field(name="Reason", value=str(self.reason), inline=False)
        embed.add_field(name="Extra", value=str(self.extra or "None"), inline=False)
        embed.add_field(name="Status", value="⏳ Pending HR review", inline=False)
        embed.set_footer(text=f"LOA Request ID: {request_id}")

        message = await channel.send(
            embed=embed,
            view=LOAReviewView(self.bot, request_id),
        )

        await update_loa_request_message(
            request_id,
            message.id,
            channel.id,
        )

        await interaction.response.send_message(
            f"✅ LOA request submitted. Request ID: `{request_id}`",
            ephemeral=True,
        )


class DenyModal(discord.ui.Modal):
    reason = discord.ui.TextInput(
        label="Denial reason",
        style=discord.TextStyle.paragraph,
        min_length=3,
        max_length=1000,
    )

    def __init__(self, request_id: int, review_view):
        super().__init__(title="Deny LOA Request")
        self.request_id = request_id
        self.review_view = review_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        request = await get_loa_request(self.request_id)

        if not request or request["status"] != "pending":
            await interaction.response.send_message(
                "❌ This request was already reviewed.",
                ephemeral=True,
            )
            return

        await update_loa_status(
            self.request_id,
            "denied",
            interaction.user.id,
            str(interaction.user),
            str(self.reason),
        )

        for child in self.review_view.children:
            child.disabled = True

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()

        for index, field in enumerate(embed.fields):
            if field.name == "Status":
                embed.set_field_at(
                    index,
                    name="Status",
                    value=f"❌ Denied by {interaction.user.mention}\n**Reason:** {self.reason}",
                    inline=False,
                )

        await interaction.message.edit(embed=embed, view=self.review_view)
        await interaction.response.send_message("✅ LOA request denied.", ephemeral=True)


class LOAReviewView(discord.ui.View):
    def __init__(self, bot, request_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.request_id = request_id

        self.approve.custom_id = f"sanity2x:loa:approve:{request_id}"
        self.deny.custom_id = f"sanity2x:loa:deny:{request_id}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False

        if not is_hr(interaction.user):
            await interaction.response.send_message(
                "❌ Only HR or administrators can review LOA requests.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        request = await get_loa_request(self.request_id)

        if not request or request["status"] != "pending":
            await interaction.response.send_message(
                "❌ This request was already reviewed.",
                ephemeral=True,
            )
            return

        if interaction.guild is None:
            return

        role = interaction.guild.get_role(LOA_ROLE_ID)

        if role is None:
            await interaction.response.send_message(
                "❌ LOA role was not found.",
                ephemeral=True,
            )
            return

        try:
            member = interaction.guild.get_member(int(request["discord_id"]))

            if member is None:
                member = await interaction.guild.fetch_member(int(request["discord_id"]))

            await member.add_roles(
                role,
                reason=f"LOA request #{self.request_id} approved by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Give the bot Manage Roles and place its role above the LOA role.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ Failed to assign the LOA role.",
                ephemeral=True,
            )
            return

        await update_loa_status(
            self.request_id,
            "approved",
            interaction.user.id,
            str(interaction.user),
            "Approved by HR",
        )

        for child in self.children:
            child.disabled = True

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()

        for index, field in enumerate(embed.fields):
            if field.name == "Status":
                embed.set_field_at(
                    index,
                    name="Status",
                    value=f"✅ Approved by {interaction.user.mention}",
                    inline=False,
                )

        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.send_message("✅ LOA request approved.", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.send_modal(DenyModal(self.request_id, self))


class LOACog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        for request in await get_pending_loa_requests():
            self.bot.add_view(
                LOAReviewView(self.bot, int(request["id"]))
            )

    @app_commands.command(name="loa", description="Submit a leave of absence request.")
    @app_commands.guild_only()
    async def loa(self, interaction: discord.Interaction) -> None:
        active = await get_active_loa_request(interaction.user.id)

        if active:
            await interaction.response.send_message(
                f"❌ You already have an active LOA request. Status: `{active['status']}`",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(LOAModal(self.bot))

    @app_commands.command(name="loastatus", description="View your LOA request.")
    @app_commands.guild_only()
    async def loastatus(self, interaction: discord.Interaction) -> None:
        request = await get_active_loa_request(interaction.user.id)

        if not request:
            await interaction.response.send_message(
                "You do not have an active LOA request.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📋 Your LOA Request",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Request ID", value=f"`{request['id']}`", inline=True)
        embed.add_field(name="Status", value=request["status"].title(), inline=True)
        embed.add_field(
            name="Dates",
            value=f"{request['start_date']} → {request['end_date']}",
            inline=False,
        )
        embed.add_field(name="Reason", value=request["reason"], inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(LOACog(bot))
