# views/attendance.py
import discord
from discord.ui import Button, View, Select
from models.database import DatabaseManager

class ExcuseView(View):
    """View class for handling attendance UI components."""
    def __init__(self, absent_members: list, original_embed: discord.Embed, 
                 session_name: str, skill_group: str, season: int):
        super().__init__(timeout=300)
        # Store all necessary data as instance variables
        self.absent_members = absent_members
        self.original_embed = original_embed
        self.excused_members = set()
        self.session_name = session_name
        self.skill_group = skill_group
        self.season = season

        # Create buttons and menus only if there are absent members
        if absent_members:
            excuse_button = Button(
                label="Mark Excused Absence",
                style=discord.ButtonStyle.primary,
                custom_id="excuse_button"
            )
            excuse_button.callback = self.show_select_menu
            self.add_item(excuse_button)

            self.select_student = Select(
                placeholder="Select student to excuse...",
                options=[
                    discord.SelectOption(
                        label=member.display_name,
                        value=str(member.id)
                    ) for member in absent_members
                ],
                min_values=1,
                max_values=1
            )
            self.select_student.callback = self.student_selected
        
        # Always add log attendance button
        log_button = Button(
            label="Log Attendance",
            style=discord.ButtonStyle.success,
            custom_id="log_button"
        )
        log_button.callback = self.log_attendance
        self.add_item(log_button)

    async def show_select_menu(self, interaction: discord.Interaction):
        try:
            self.add_item(self.select_student)
            await interaction.response.edit_message(view=self)
        except Exception as e:
            print(f"Error showing select menu: {e}")
            await interaction.response.send_message(
                "An error occurred while showing the menu. Please try again.",
                ephemeral=True
            )

    async def student_selected(self, interaction: discord.Interaction):
        try:
            selected_id = int(self.select_student.values[0])
            selected_member = next(m for m in self.absent_members if m.id == selected_id)
            
            # Add to excused set
            self.excused_members.add(selected_member)
            
            new_embed = self.original_embed.copy()
            
            for field in new_embed.fields:
                if field.name.startswith("Absent Students"):
                    lines = field.value.split('\n')
                    updated_lines = []
                    for line in lines:
                        if selected_member.display_name in line:
                            updated_lines.append(f"{line} (Excused ✓)")
                        else:
                            updated_lines.append(line)
                    new_value = '\n'.join(updated_lines)
                    new_embed.set_field_at(
                        index=new_embed.fields.index(field),
                        name=field.name,
                        value=new_value,
                        inline=field.inline
                    )
            
            self.remove_item(self.select_student)
            await interaction.message.edit(embed=new_embed, view=self)
            await interaction.response.send_message(
                f"Marked {selected_member.display_name} as excused.",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error marking student as excused: {e}")
            await interaction.response.send_message(
                "An error occurred while marking the absence as excused. Please try again.",
                ephemeral=True
            )

    async def log_attendance(self, interaction: discord.Interaction):
        try:
            # Safety check for voice channel
            if not interaction.user.voice:
                await interaction.response.send_message(
                    "You must be in a voice channel to log attendance.",
                    ephemeral=True
                )
                return

            # Get present members from voice channel
            voice_channel = interaction.guild.get_channel(interaction.user.voice.channel.id)
            present_members = voice_channel.members

            # Debug print
            print(f"Logging attendance for session '{self.session_name}' in group '{self.skill_group}' for season {self.season}")
            print(f"Present members: {len(present_members)}")
            print(f"Absent members: {len(self.absent_members)}")
            print(f"Excused members: {len(self.excused_members)}")

            # Create attendance records
            db_success = await DatabaseManager.create_attendance_records(
                user_id=interaction.user.id,
                session_name=self.session_name,
                skill_group=self.skill_group,
                season=self.season,
                present_members=present_members,
                absent_members=self.absent_members,
                excused_members=self.excused_members
            )

            if db_success:
                # Disable the log button after successful logging
                for item in self.children:
                    if isinstance(item, Button) and item.custom_id == "log_button":
                        item.disabled = True
                        break

                await interaction.message.edit(view=self)
                await interaction.response.send_message(
                    "Successfully logged attendance to the database!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "Failed to log attendance to the database. Please try again or contact an administrator.",
                    ephemeral=True
                )

        except Exception as e:
            print(f"Error logging attendance: {e}")
            # Print more debug info
            print(f"Current values:")
            print(f"- session_name: {self.session_name}")
            print(f"- skill_group: {self.skill_group}")
            print(f"- season: {self.season}")
            await interaction.response.send_message(
                "An error occurred while logging attendance. Please try again.",
                ephemeral=True
            )