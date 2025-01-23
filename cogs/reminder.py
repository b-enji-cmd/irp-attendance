# cogs/reminder.py
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import Dict, Set

class VoiceReminderCog(commands.Cog):
    """Cog for handling automatic attendance reminders."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.coach_voice_states: Dict[int, datetime] = {}
        self.reminded_coaches: Set[int] = set()
        self.check_voice_duration.start()
        self.reset_daily_reminders.start()
        print("VoiceReminderCog initialized")
        
        # Initialize voice states for coaches already in voice channels
        self.bot.loop.create_task(self.initialize_voice_states())

    async def initialize_voice_states(self):
        """Initialize voice states for coaches already in voice channels."""
        await self.bot.wait_until_ready()
        current_time = datetime.now()
        
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                for member in voice_channel.members:
                    if any(role.id in self.bot.config.ALLOWED_ROLE_IDS for role in member.roles):
                        self.coach_voice_states[member.id] = current_time
                        print(f"Initialized voice state for {member.display_name}")

    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        self.check_voice_duration.cancel()
        self.reset_daily_reminders.cancel()
        print("VoiceReminderCog unloaded")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Tracks when coaches join/leave voice channels."""
        try:
            # Check if member has the coach role
            has_coach_role = any(role.id in self.bot.config.ALLOWED_ROLE_IDS for role in member.roles)
            print(f"Voice state update for {member.display_name} (Coach role: {has_coach_role})")
            
            if not has_coach_role:
                return

            current_time = datetime.now()

            # Coach joined a voice channel from being outside voice
            if before.channel is None and after.channel is not None:
                print(f"Coach {member.display_name} joined voice channel {after.channel.name}")
                self.coach_voice_states[member.id] = current_time
                print(f"Started tracking {member.display_name} at {current_time}")
                
            # Coach left voice entirely
            elif before.channel is not None and after.channel is None:
                print(f"Coach {member.display_name} left voice channel {before.channel.name}")
                self.coach_voice_states.pop(member.id, None)
                print(f"Stopped tracking {member.display_name}")
                
            print(f"Current coach_voice_states: {self.coach_voice_states}")
            
        except Exception as e:
            print(f"Error in voice state update: {e}")

    @tasks.loop(seconds=30)
    async def check_voice_duration(self):
        """Checks if coaches have been in VC for 5 minutes without taking attendance."""
        try:
            current_time = datetime.now()
            print(f"\nChecking voice duration at {current_time}")
            
            for guild in self.bot.guilds:
                attendance_channel = guild.get_channel(self.bot.config.ATTENDANCE_CHANNEL_ID)
                if not attendance_channel:
                    print(f"Could not find attendance channel in guild {guild.name}")
                    continue

                for voice_channel in guild.voice_channels:
                    coaches = [
                        member for member in voice_channel.members
                        if any(role.id in self.bot.config.ALLOWED_ROLE_IDS for role in member.roles)
                        and member.id not in self.reminded_coaches
                    ]

                    if coaches:
                        print(f"Found coaches in {voice_channel.name}: {[c.display_name for c in coaches]}")

                    for coach in coaches:
                        join_time = self.coach_voice_states.get(coach.id)
                        if not join_time:
                            # Initialize join time if not set
                            print(f"Initializing join time for coach {coach.display_name}")
                            self.coach_voice_states[coach.id] = current_time
                            continue

                        time_in_channel = current_time - join_time
                        print(f"Coach {coach.display_name} has been in channel for {time_in_channel.total_seconds()} seconds")

                        if time_in_channel >= timedelta(minutes=5):
                            print(f"Sending reminder to coach {coach.display_name}")
                            
                            embed = discord.Embed(
                                title="Attendance Reminder",
                                description=f"You've been in {voice_channel.name} for 5 minutes. Don't forget to take attendance!",
                                color=discord.Color.yellow(),
                                timestamp=current_time
                            )
                            embed.set_footer(text="Use /attendance take to record attendance")

                            await attendance_channel.send(
                                content=f"{coach.mention} Reminder to take attendance!",
                                embed=embed
                            )

                            self.reminded_coaches.add(coach.id)
                            print(f"Added {coach.display_name} to reminded_coaches set")

        except Exception as e:
            print(f"Error in check_voice_duration: {e}")

    @check_voice_duration.before_loop
    async def before_check_voice_duration(self):
        """Wait for the bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()
        print("Voice duration check loop is ready")

    @tasks.loop(hours=24)
    async def reset_daily_reminders(self):
        """Resets the reminded_coaches set once per day."""
        old_count = len(self.reminded_coaches)
        self.reminded_coaches.clear()
        self.coach_voice_states.clear()
        print(f"Reset daily reminders. Cleared {old_count} reminded coaches.")
        
        # Re-initialize voice states after reset
        await self.initialize_voice_states()

    @reset_daily_reminders.before_loop
    async def before_reset_daily_reminders(self):
        """Wait for the bot to be ready before starting the loop."""
        await self.bot.wait_until_ready()
        print("Daily reset loop is ready")

async def setup(bot: commands.Bot):
    """Sets up the reminder cog."""
    await bot.add_cog(VoiceReminderCog(bot))
    print("VoiceReminderCog setup complete")