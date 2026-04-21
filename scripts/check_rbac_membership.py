"""Quick smoke for 0010: list app_* memberships granted to the runtime login."""
import os
from sqlalchemy import create_engine, text

dsn = os.environ["POSTGRES_DSN"]
login = os.environ.get("DASHBOARD_APP_LOGIN_ROLE", "proline")
e = create_engine(dsn)
with e.connect() as c:
    rows = c.execute(
        text(
            "SELECT pg_get_userbyid(roleid) AS role "
            "FROM pg_auth_members "
            "WHERE pg_get_userbyid(member) = :login "
            "ORDER BY role"
        ),
        {"login": login},
    ).all()
    print(f"login={login!r} membership: {[r[0] for r in rows]}")
