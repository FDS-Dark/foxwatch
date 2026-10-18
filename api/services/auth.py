import logging

from databridge.postgres_databridge import PostgresDatabridge

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, databridge: PostgresDatabridge):
        self.databridge = databridge

    async def user_has_role(self, user_id: str, role_name: str) -> bool:
        query = """
            SELECT 1
            FROM auth.user_roles ur
            JOIN auth.roles r ON r.role_id = ur.role_id
            WHERE ur.user_id = :user_id AND r.name = :role_name
            LIMIT 1
        """
        df = await self.databridge.execute_query(
            query, {"user_id": user_id, "role_name": role_name}
        )
        return not df.empty
