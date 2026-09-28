from app.models.base import Base
from app.models.role import Roles
from app.models.tenant import Tenants
from app.models.user import Users
from app.models.coversation import Conversations
from app.models.message import Messages
from app.models.document import Documents
from app.models.chunk import Chunks
from app.models.auditlog import AuditLogs
from app.models.token import Tokens
# Backward-compat alias so any existing code referencing InvitationTokens still works
InvitationTokens = Tokens

"""
    Bắt buộc phải viết imports ở đây => để target metadata trong migration imports vào đây 
"""

__all__ = [
    "Base", "Roles", "Tenants", "Users", "Conversations",
    "Messages", "Documents", "Chunks", "AuditLogs", "Tokens", "InvitationTokens",
]