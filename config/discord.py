GUILD_ID = 1329334053580836950
ALLOWED_ROLE_IDS = [1329341459329191948]

# Role configurations for different skill groups
SKILL_GROUPS = {
    "Advanced": 1329349873790881853,
    "Mechanics": 1329360868714086461
}

# Channel configurations
ATTENDANCE_CHANNEL_ID = 1329356087744532531

# Choices for skill group command parameter
SKILL_GROUP_CHOICES = [
    ('Advanced', 'Advanced'),
    ('Mechanics', 'Mechanics'),
    ('Combined', 'Combined')
]

# Role configurations for user types
USER_ROLE_TYPES = {
    # Format: role_id: user_type
    1329341459329191948: 'coach',     # Coach role ID
    1234567890123456: 'admin',      # Admin role ID (update with actual ID)
    2345678901234567: 'manager',    # Community Manager role ID (update with actual ID)
    3456789012345678: 'student',    # IRP Student role ID (update with actual ID)
    4567890123456789: 'graduate'    # IRP Graduate Continued role ID (update with actual ID)
}

# Role priority (higher index = higher priority)
ROLE_PRIORITY = [
    'student',
    'graduate',
    'manager',
    'admin',
    'coach'
]