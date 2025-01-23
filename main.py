# main.py
import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from config.discord import (
    GUILD_ID, 
    ALLOWED_ROLE_IDS, 
    SKILL_GROUPS, 
    ATTENDANCE_CHANNEL_ID
)

# Load environment variables
load_dotenv()
TOKEN = os.environ.get('DISCORD_TOKEN')
if not TOKEN:
    raise ValueError("No Discord token found in .env file!")

class AttendanceBot(commands.Bot):
    """Main bot class for handling attendance."""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.voice_states = True
        intents.message_content = True
        
        # Remove application_id from super().__init__ as it's not needed
        super().__init__(
            command_prefix='!',
            intents=intents
        )
        
        # Make config available to cogs
        self.config = type('Config', (), {
            'ALLOWED_ROLE_IDS': ALLOWED_ROLE_IDS,
            'ATTENDANCE_CHANNEL_ID': ATTENDANCE_CHANNEL_ID,
            'GUILD_ID': GUILD_ID
        })

    async def setup_hook(self):
        """Sets up the bot's commands and syncs with Discord."""
        try:
            # Load the attendance cog
            await self.load_extension('cogs.attendance')
            print("Loaded attendance cog")
            
            # Load the reminder cog
            await self.load_extension('cogs.reminder')
            print("Loaded reminder cog")
            
            # Sync commands with Discord
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print("Synced command tree")
            
        except Exception as e:
            print(f"Error in setup_hook: {e}")
            print(f"Error details: {str(e)}")

    async def on_ready(self):
        """Called when the bot has successfully connected to Discord."""
        print(f'Logged in as {self.user}')
        print(f'Connected to {len(self.guilds)} guilds')
        print(f'Bot Application ID: {self.application_id}')  # Print the application ID for verification
        print('Bot is ready!')

def main():
    """Main entry point for the bot."""
    try:
        # Create and run the bot
        client = AttendanceBot()
        client.run(TOKEN)
    except Exception as e:
        print(f"Error starting bot: {e}")

if __name__ == '__main__':
    main()