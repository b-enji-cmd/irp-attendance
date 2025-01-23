# cogs/attendance.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from enum import Enum
from typing import List
from config.discord import (
    GUILD_ID, 
    ALLOWED_ROLE_IDS, 
    SKILL_GROUPS, 
    ATTENDANCE_CHANNEL_ID, 
    SKILL_GROUP_CHOICES
)
from views.attendance import ExcuseView
from models.database import DatabaseManager

class ReportGranularity(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"

def has_any_required_role():
    """Check if user has any of the required roles."""
    def predicate(interaction: discord.Interaction) -> bool:
        try:
            user_roles = interaction.user.roles
            return any(role.id in ALLOWED_ROLE_IDS for role in user_roles)
        except Exception as e:
            print(f"Error checking roles: {e}")
            return False
    return app_commands.check(predicate)

class AttendanceReport:
    """Handles attendance report generation and formatting."""
    
    # Constants for Discord embed limits
    MAX_FIELDS_PER_EMBED = 25
    MAX_FIELD_VALUE_LENGTH = 1024
    MAX_EMBED_DESCRIPTION_LENGTH = 4096

    @staticmethod
    async def get_report_data(connection, season: int, granularity: ReportGranularity, days: int = 7) -> List[dict]:
        """Fetches attendance data from database."""
        try:
            cursor = connection.cursor(dictionary=True)
            
            query = """
            WITH SessionAbsences AS (
                SELECT 
                    s.id AS session_id,
                    s.session_name,
                    s.skill_group,
                    DATE(s.created_date) AS session_date,
                    l.student_id,
                    l.is_excused
                FROM session s
                JOIN ledger l ON s.id = l.session_id
                WHERE 
                    s.season = %s
                    AND s.created_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    AND l.is_present = FALSE
            )
            SELECT 
                session_date,
                session_name,
                skill_group,
                COUNT(DISTINCT student_id) as total_absences,
                COUNT(DISTINCT CASE WHEN is_excused THEN student_id END) as excused_absences,
                GROUP_CONCAT(
                    CONCAT(student_id, ':', is_excused)
                    ORDER BY student_id
                    SEPARATOR ','
                ) as absent_data
            FROM SessionAbsences
            GROUP BY 
                session_date, 
                session_name, 
                skill_group
            ORDER BY 
                session_date DESC, 
                session_name
            """
            
            cursor.execute(query, (season, days))
            results = cursor.fetchall()
            cursor.close()
            return results
            
        except Exception as e:
            print(f"Error fetching report data: {e}")
            return []

    @staticmethod
    def create_session_field_content(session: dict, guild: discord.Guild) -> tuple[str, str]:
        """Creates the field name and value for a session entry."""
        session_date = session['session_date'].strftime('%Y-%m-%d')
        field_name = f"Session: {session['session_name']} on [{session_date}] for {session['skill_group']}"
        
        # Process absent students
        absent_students = []
        if session['absent_data']:
            for student_data in session['absent_data'].split(','):
                student_id, is_excused = student_data.split(':')
                member = guild.get_member(int(student_id))
                if member:
                    name = member.display_name
                    status = "(Excused)" if int(is_excused) else "(Unexcused)"
                    absent_students.append(f"{name} {status}")

        # Create field value
        field_value = "**Absent:**\n"
        if absent_students:
            for i, student in enumerate(absent_students, 1):
                field_value += f"{i}. {student}\n"
        else:
            field_value += "Everyone Present! 🎉\n"

        # Add summary line
        field_value += f"\nTotal Absences: **{session['total_absences']}** (Excused: {session['excused_absences']})"
        
        return field_name, field_value

    @staticmethod
    def create_report_embeds(data: List[dict], season: int, granularity: ReportGranularity, guild: discord.Guild) -> List[discord.Embed]:
        """Creates a list of Discord embeds for the attendance report, handling pagination."""
        current_time = datetime.now()
        embeds = []
        current_embed = discord.Embed(
            title=f"Attendance Report - Season {season}",
            description=f"{granularity.value.title()} report generated at {current_time.strftime('%Y-%m-%d %H:%M:%S')}",
            color=discord.Color.blue()
        )
        
        if not data:
            current_embed.add_field(
                name="No Data",
                value="No attendance records found for the specified period.",
                inline=False
            )
            return [current_embed]

        field_count = 0
        
        # Process each session
        for session in data:
            field_name, field_value = AttendanceReport.create_session_field_content(session, guild)
            
            # Check if we need a new embed
            if field_count >= AttendanceReport.MAX_FIELDS_PER_EMBED:
                embeds.append(current_embed)
                current_embed = discord.Embed(
                    title=f"Attendance Report - Season {season} (Continued)",
                    color=discord.Color.blue()
                )
                field_count = 0

            # Handle field value length limit
            if len(field_value) > AttendanceReport.MAX_FIELD_VALUE_LENGTH:
                field_value = field_value[:AttendanceReport.MAX_FIELD_VALUE_LENGTH - 3] + "..."

            current_embed.add_field(
                name=field_name,
                value=field_value,
                inline=False
            )
            field_count += 1

        # Add the last embed if it has fields
        if field_count > 0:
            embeds.append(current_embed)

        # Add page numbers
        total_pages = len(embeds)
        for i, embed in enumerate(embeds, 1):
            embed.set_footer(text=f"Page {i}/{total_pages}")

        return embeds

class AttendanceCog(commands.Cog):
    """Cog for handling attendance-related commands."""
    
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="take")
    @app_commands.describe(
        session_name="Name of the session (e.g., 'Agent Masterclass')",
        skill_group="Select the skill group to track",
        season="Season number (e.g., 1, 2, 3)"
    )
    @app_commands.choices(skill_group=[
        app_commands.Choice(name=choice[0], value=choice[1])
        for choice in SKILL_GROUP_CHOICES
    ])
    @has_any_required_role()
    async def take(
        self,
        interaction: discord.Interaction,
        session_name: str,
        skill_group: str,
        season: int
    ):
        """Takes attendance for a specific session."""
        try:
            member = interaction.guild.get_member(interaction.user.id)
            
            if member.voice is None:
                await interaction.response.send_message(
                    "You're not in a voice channel!", 
                    ephemeral=True
                )
                return

            voice_channel = member.voice.channel
            members_in_vc = voice_channel.members
            
            attendance_channel = interaction.guild.get_channel(ATTENDANCE_CHANNEL_ID)
            if not attendance_channel:
                await interaction.response.send_message(
                    "Could not find the attendance channel!", 
                    ephemeral=True
                )
                return

            # Handle combined or single role attendance
            if skill_group == "Combined":
                advanced_role = interaction.guild.get_role(SKILL_GROUPS["Advanced"])
                mechanics_role = interaction.guild.get_role(SKILL_GROUPS["Mechanics"])
                if not advanced_role or not mechanics_role:
                    await interaction.response.send_message(
                        "Could not find one or both roles to track attendance for!", 
                        ephemeral=True
                    )
                    return
                members_with_role = [
                    member for member in interaction.guild.members 
                    if advanced_role in member.roles or mechanics_role in member.roles
                ]
                role_name = "Advanced/Mechanics Combined"
            else:
                role_id = SKILL_GROUPS[skill_group]
                tracked_role = interaction.guild.get_role(role_id)
                if not tracked_role:
                    await interaction.response.send_message(
                        f"Could not find the role to track attendance for!", 
                        ephemeral=True
                    )
                    return
                members_with_role = [
                    member for member in interaction.guild.members 
                    if tracked_role in member.roles
                ]
                role_name = tracked_role.name
            
            absent_members = [
                member for member in members_with_role 
                if member not in members_in_vc
            ]
            
            embed = discord.Embed(
                title=f"Attendance Report - {session_name} (Season {season})",
                color=discord.Color.blue(),
                timestamp=interaction.created_at
            )
            
            embed.add_field(
                name="Session Info",
                value=f"**Session:** {session_name}\n"
                      f"**Channel:** {voice_channel.name}\n"
                      f"**Role:** {role_name}\n"
                      f"**Total Members:** {len(members_with_role)}",
                inline=False
            )
            
            if absent_members:
                absent_list = "\n".join([
                    f"{i}. {member.display_name}" 
                    for i, member in enumerate(absent_members, 1)
                ])
                embed.add_field(
                    name=f"Absent Students ({len(absent_members)})",
                    value=absent_list if len(absent_list) <= 1024 else f"{absent_list[:1021]}...",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Attendance",
                    value="Everyone is present! 🎉",
                    inline=False
                )
            
            embed.set_footer(text=f"Taken by {member.display_name}")

            view = ExcuseView(
                absent_members=absent_members,
                original_embed=embed,
                session_name=session_name,
                skill_group=skill_group,
                season=season
            )
            
            await attendance_channel.send(
                content=f"{interaction.user.mention} took attendance:", 
                embed=embed,
                view=view
            )
            
            await interaction.response.send_message(
                "Attendance report has been generated! "
                "Mark any excused absences before clicking 'Log Attendance' "
                "to save to the database.",
                ephemeral=True
            )

        except Exception as e:
            print(f"Error taking attendance: {e}")
            await interaction.response.send_message(
                "An error occurred while taking attendance. Please try again.",
                ephemeral=True
            )

    @app_commands.command(name="report")
    @app_commands.describe(
        granularity="Report timeframe (daily or weekly)",
        season="Season number"
    )
    @app_commands.choices(granularity=[
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly")
    ])
    @has_any_required_role()
    async def report(
        self,
        interaction: discord.Interaction,
        granularity: str,
        season: int
    ):
        """Generate an attendance report for the specified period."""
        try:
            await interaction.response.defer()
            
            report_type = ReportGranularity(granularity)
            days_back = 1 if report_type == ReportGranularity.DAILY else 7
            
            connection = DatabaseManager.create_connection()
            if not connection:
                await interaction.followup.send(
                    "Failed to connect to the database. Please try again later.",
                    ephemeral=True
                )
                return
                
            try:
                report_data = await AttendanceReport.get_report_data(
                    connection=connection,
                    season=season,
                    granularity=report_type,
                    days=days_back
                )
                
                embeds = AttendanceReport.create_report_embeds(
                    data=report_data,
                    season=season,
                    granularity=report_type,
                    guild=interaction.guild
                )
                
                # Send first embed with initial response
                await interaction.followup.send(embed=embeds[0])
                
                # Send additional embeds if they exist
                if len(embeds) > 1:
                    for embed in embeds[1:]:
                        await interaction.followup.send(embed=embed)
                
            finally:
                connection.close()
                
        except Exception as e:
            print(f"Error generating attendance report: {e}")
            await interaction.followup.send(
                "An error occurred while generating the report. Please try again.",
                ephemeral=True
            )

    @take.error
    async def take_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        """Error handler for the take command."""
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "You don't have permission to use this command!", 
                ephemeral=True
            )
        else:
            print(f"Command error occurred: {error}")
            await interaction.response.send_message(
                "An error occurred while processing the command. Please try again.",
                ephemeral=True
            )

async def setup(bot):
    """Sets up the attendance cog."""
    await bot.add_cog(AttendanceCog(bot))