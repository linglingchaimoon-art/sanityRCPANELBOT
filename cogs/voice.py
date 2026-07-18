import discord
from discord.ext import commands
from discord import app_commands

# Channel users join to create their own voice channel
CREATE_VOICE_CHANNEL_ID = 1527112174454181939

# Category where temp voice channels will be created
VOICE_CATEGORY_ID = 1520611292996698162

temp_channels = {}


class VoiceSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        # User joined "Create Voice"
        if after.channel and after.channel.id == CREATE_VOICE_CHANNEL_ID:
            guild = member.guild
            category = guild.get_channel(VOICE_CATEGORY_ID)

            channel = await guild.create_voice_channel(
                name=f"🔊 {member.display_name}'s Voice",
                category=category,
                user_limit=5
            )

            temp_channels[channel.id] = member.id

            await channel.set_permissions(
                member,
                manage_channels=True,
                connect=True,
                speak=True,
                view_channel=True
            )

            await member.move_to(channel)

        # Delete empty temporary channels
        if before.channel and before.channel.id in temp_channels:
            if len(before.channel.members) == 0:
                del temp_channels[before.channel.id]
                await before.channel.delete()

    def is_owner_channel(self, interaction):
        channel = interaction.user.voice.channel if interaction.user.voice else None

        if not channel:
            return None, "❌ You are not in a voice channel."

        if channel.id not in temp_channels:
            return None, "❌ This is not a temporary voice channel."

        if temp_channels[channel.id] != interaction.user.id:
            return None, "❌ You do not own this voice channel."

        return channel, None

    @app_commands.command(name="voice-lock", description="Lock your temporary voice channel.")
    async def voice_lock(self, interaction: discord.Interaction):
        channel, error = self.is_owner_channel(interaction)

        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await channel.set_permissions(
            interaction.guild.default_role,
            connect=False
        )

        await interaction.response.send_message(
            "🔒 Your voice channel has been locked.",
            ephemeral=True
        )

    @app_commands.command(name="voice-unlock", description="Unlock your temporary voice channel.")
    async def voice_unlock(self, interaction: discord.Interaction):
        channel, error = self.is_owner_channel(interaction)

        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await channel.set_permissions(
            interaction.guild.default_role,
            connect=True
        )

        await interaction.response.send_message(
            "🔓 Your voice channel has been unlocked.",
            ephemeral=True
        )

    @app_commands.command(name="voice-hide", description="Hide your temporary voice channel.")
    async def voice_hide(self, interaction: discord.Interaction):
        channel, error = self.is_owner_channel(interaction)

        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await channel.set_permissions(
            interaction.guild.default_role,
            view_channel=False
        )

        await interaction.response.send_message(
            "👻 Your voice channel is now hidden.",
            ephemeral=True
        )

    @app_commands.command(name="voice-show", description="Show your temporary voice channel.")
    async def voice_show(self, interaction: discord.Interaction):
        channel, error = self.is_owner_channel(interaction)

        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await channel.set_permissions(
            interaction.guild.default_role,
            view_channel=True
        )

        await interaction.response.send_message(
            "👁️ Your voice channel is now visible.",
            ephemeral=True
        )

    @app_commands.command(name="voice-limit", description="Set a user limit for your voice channel.")
    async def voice_limit(self, interaction: discord.Interaction, limit: int):
        channel, error = self.is_owner_channel(interaction)

        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        if limit < 0 or limit > 99:
            await interaction.response.send_message(
                "❌ Limit must be between 0 and 99. Use 0 for no limit.",
                ephemeral=True
            )
            return

        await channel.edit(user_limit=limit)

        await interaction.response.send_message(
            f"👥 Voice limit set to **{limit}**.",
            ephemeral=True
        )

    @app_commands.command(name="voice-rename", description="Rename your temporary voice channel.")
    async def voice_rename(self, interaction: discord.Interaction, name: str):
        channel, error = self.is_owner_channel(interaction)

        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        if len(name) > 32:
            await interaction.response.send_message(
                "❌ Name must be 32 characters or less.",
                ephemeral=True
            )
            return

        await channel.edit(name=f"🔊 {name}")

        await interaction.response.send_message(
            f"✏️ Voice channel renamed to **{name}**.",
            ephemeral=True
        )

    @app_commands.command(name="voice-permit", description="Allow a user to join your locked/hidden voice channel.")
    async def voice_permit(self, interaction: discord.Interaction, member: discord.Member):
        channel, error = self.is_owner_channel(interaction)

        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await channel.set_permissions(
            member,
            view_channel=True,
            connect=True,
            speak=True
        )

        await interaction.response.send_message(
            f"✅ {member.mention} can now join your voice channel.",
            ephemeral=True
        )

    @app_commands.command(name="voice-deny", description="Block a user from your voice channel.")
    async def voice_deny(self, interaction: discord.Interaction, member: discord.Member):
        channel, error = self.is_owner_channel(interaction)

        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await channel.set_permissions(
            member,
            view_channel=False,
            connect=False
        )

        if member.voice and member.voice.channel == channel:
            await member.move_to(None)

        await interaction.response.send_message(
            f"🚫 {member.mention} has been blocked from your voice channel.",
            ephemeral=True
        )

    @app_commands.command(name="voice-transfer", description="Transfer ownership of your voice channel.")
    async def voice_transfer(self, interaction: discord.Interaction, member: discord.Member):
        channel, error = self.is_owner_channel(interaction)

        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        if not member.voice or member.voice.channel != channel:
            await interaction.response.send_message(
                "❌ That user must be inside your voice channel.",
                ephemeral=True
            )
            return

        temp_channels[channel.id] = member.id

        await channel.set_permissions(
            member,
            manage_channels=True,
            connect=True,
            speak=True,
            view_channel=True
        )

        await interaction.response.send_message(
            f"👑 Ownership transferred to {member.mention}.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(VoiceSystem(bot))