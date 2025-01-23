# models/database.py
from mysql.connector import Error
import mysql.connector
from datetime import datetime
from config.database import DB_CONFIG
from config.discord import USER_ROLE_TYPES, ROLE_PRIORITY

class DatabaseManager:
    """Handles all database operations for the attendance bot."""
    
    @staticmethod
    def create_connection():
        """Creates and returns a database connection."""
        try:
            connection = mysql.connector.connect(**DB_CONFIG)
            return connection
        except Error as e:
            print(f"Error connecting to MySQL database: {e}")
            return None

    @staticmethod
    async def create_attendance_records(user_id: int, session_name: str, skill_group: str, season: int, 
                                     present_members: list, absent_members: list, excused_members: list) -> bool:
        """
        Creates a session record and corresponding attendance records.
        
        Args:
            user_id (int): Discord ID of the coach taking attendance
            session_name (str): Name of the session being conducted
            skill_group (str): The skill group for the session
            season (int): Current season number
            present_members (list): List of members present in the session
            absent_members (list): List of members absent from the session
            excused_members (list): List of members with excused absences
        """
        connection = None
        try:
            connection = DatabaseManager.create_connection()
            if not connection:
                return False
            
            cursor = connection.cursor()
            
            # Create session record with corrected column list
            session_query = """
            INSERT INTO session 
            (session_name, user, skill_group, season, created_date, modified_date) 
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            current_time = datetime.now()
            session_values = (
                session_name,
                str(user_id),  # Discord ID directly
                skill_group,
                season,
                current_time,
                current_time
            )
            
            cursor.execute(session_query, session_values)
            session_id = cursor.lastrowid

            # Create ledger entries for attendance records
            ledger_query = """
            INSERT INTO ledger 
            (session_id, student_id, is_present, is_excused, event_date) 
            VALUES (%s, %s, %s, %s, %s)
            """
            
            # Process present members
            for member in present_members:
                values = (session_id, str(member.id), True, False, current_time)
                cursor.execute(ledger_query, values)

            # Process absent members
            for member in absent_members:
                is_excused = member in excused_members
                values = (session_id, str(member.id), False, is_excused, current_time)
                cursor.execute(ledger_query, values)

            connection.commit()
            return True
            
        except Error as e:
            print(f"Error creating attendance records: {e}")
            if connection:
                connection.rollback()
            return False
            
        finally:
            if connection:
                cursor.close()
                connection.close()


    @staticmethod
    async def sync_users(members: list) -> tuple[bool, int, int]:
        """
        Syncs Discord users to the database.
        
        Args:
            members (list): List of Discord member objects to sync
            
        Returns:
            tuple: (success: bool, users_added: int, users_updated: int)
        """
        from config.discord import USER_ROLE_TYPES, ROLE_PRIORITY, SKILL_GROUPS
        
        connection = None
        try:
            connection = DatabaseManager.create_connection()
            if not connection:
                return False, 0, 0
            
            cursor = connection.cursor()
            users_added = 0
            users_updated = 0
            
            for member in members:
                # Skip bots
                if member.bot:
                    continue
                    
                # Determine user type based on roles
                user_type = None
                member_role_types = []
                skill_group = None
                
                # Get all valid role types for this member
                for role in member.roles:
                    if role.id in USER_ROLE_TYPES:
                        member_role_types.append(USER_ROLE_TYPES[role.id])
                    
                    # Check for skill group role
                    if role.id == SKILL_GROUPS["Advanced"]:
                        skill_group = "Advanced"
                    elif role.id == SKILL_GROUPS["Mechanics"]:
                        skill_group = "Mechanics"
                
                # If user has any valid roles, select the highest priority one
                if member_role_types:
                    # Sort role types by priority and take the highest
                    sorted_roles = sorted(
                        member_role_types,
                        key=lambda x: ROLE_PRIORITY.index(x) if x in ROLE_PRIORITY else -1
                    )
                    user_type = sorted_roles[-1]
                    
                    # Skip if user_type is not 'student' or 'coach' (based on enum constraint)
                    if user_type not in ['student', 'coach']:
                        continue
                else:
                    # Skip users with no relevant roles
                    continue
                
                # Check if user exists
                cursor.execute("SELECT id FROM user WHERE discord_id = %s", (str(member.id),))
                existing_user = cursor.fetchone()
                
                if existing_user:
                    # Update existing user
                    update_query = """
                    UPDATE user 
                    SET name = %s, user_type = %s, skill_group = %s, is_active = %s 
                    WHERE discord_id = %s
                    """
                    update_values = (member.display_name, user_type, skill_group, 1, str(member.id))
                    cursor.execute(update_query, update_values)
                    users_updated += 1
                else:
                    # Insert new user
                    insert_query = """
                    INSERT INTO user (name, discord_id, user_type, skill_group, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                    """
                    insert_values = (
                        member.display_name,
                        str(member.id),
                        user_type,
                        skill_group,
                        1
                    )
                    cursor.execute(insert_query, insert_values)
                    users_added += 1
            
            connection.commit()
            return True, users_added, users_updated
            
        except Error as e:
            print(f"Error syncing users: {e}")
            return False, 0, 0
            
        finally:
            if connection:
                cursor.close()
                connection.close()