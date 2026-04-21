"""RLS smoke test for migrations 0008/0009/0010.

Asserts the security guarantees we *claim* in the migration files:

  1. The runtime login (default ``proline``) has membership in all four
     ``app_*`` roles after 0010 -- otherwise SET LOCAL ROLE silently fails
     in production with ``permission denied to set role``.
  2. ``SET LOCAL ROLE app_operator`` followed by an ``audit_log_actions``
     INSERT whose ``actor`` does NOT match ``app.current_actor`` is
     rejected by the ``audit_log_actions_insert_self`` policy (anti-
     impersonation guarantee).
  3. After two operators each insert a row, a third ``SELECT`` as
     ``app_operator`` with the first operator's GUC sees only that
     operator's row (cross-actor leak guarantee).

Skipped automatically when ``POSTGRES_DSN`` is unset.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError


pytestmark = pytest.mark.db_fixture


def _expected_login() -> str:
    return os.environ.get("DASHBOARD_APP_LOGIN_ROLE", "proline")


def test_runtime_login_has_app_role_membership(db_session) -> None:
    login = _expected_login()
    rows = db_session.execute(
        text(
            "SELECT pg_get_userbyid(roleid) AS role "
            "FROM pg_auth_members "
            "WHERE pg_get_userbyid(member) = :login"
        ),
        {"login": login},
    ).all()
    granted = {r[0] for r in rows}
    assert {"app_viewer", "app_operator", "app_reviewer", "app_admin"} <= granted, (
        f"login {login!r} is missing app_* memberships -- 0010 did not run "
        f"with DASHBOARD_APP_LOGIN_ROLE={login!r}. Granted: {sorted(granted)}"
    )


def test_audit_insert_rejects_actor_impersonation(db_session) -> None:
    actor_real = f"alice+{uuid.uuid4().hex[:6]}@example.com"
    actor_forged = f"bob+{uuid.uuid4().hex[:6]}@example.com"

    db_session.execute(text("SET LOCAL ROLE app_operator"))
    db_session.execute(
        text("SELECT set_config('app.current_actor', :a, true)"),
        {"a": actor_real},
    )

    with pytest.raises(ProgrammingError) as exc:
        db_session.execute(
            text(
                "INSERT INTO audit_log_actions "
                "  (actor, actor_role, action, target_type, target_id) "
                "VALUES (:actor, 'operator', 'test_impersonation', 'mcp', :tid)"
            ),
            {"actor": actor_forged, "tid": str(uuid.uuid4())},
        )
    # psycopg2 surfaces RLS rejections as "new row violates row-level security policy".
    assert "row-level security" in str(exc.value).lower(), exc.value


def test_audit_select_isolates_actors(db_session) -> None:
    alice = f"alice+{uuid.uuid4().hex[:6]}@example.com"
    bob = f"bob+{uuid.uuid4().hex[:6]}@example.com"

    # Insert one row per actor under their own GUC so WITH CHECK passes.
    for actor in (alice, bob):
        db_session.execute(text("SET LOCAL ROLE app_operator"))
        db_session.execute(
            text("SELECT set_config('app.current_actor', :a, true)"),
            {"a": actor},
        )
        db_session.execute(
            text(
                "INSERT INTO audit_log_actions "
                "  (actor, actor_role, action, target_type, target_id) "
                "VALUES (:actor, 'operator', 'test_isolation', 'mcp', :tid)"
            ),
            {"actor": actor, "tid": str(uuid.uuid4())},
        )
        # Reset role between operators so policies re-evaluate cleanly.
        db_session.execute(text("RESET ROLE"))

    # Read back as alice — should see alice's rows only.
    db_session.execute(text("SET LOCAL ROLE app_operator"))
    db_session.execute(
        text("SELECT set_config('app.current_actor', :a, true)"),
        {"a": alice},
    )
    visible = db_session.execute(
        text(
            "SELECT DISTINCT actor FROM audit_log_actions "
            "WHERE action = 'test_isolation'"
        )
    ).scalars().all()
    assert set(visible) == {alice}, (
        f"app_operator with current_actor={alice!r} saw rows for: {visible}"
    )
