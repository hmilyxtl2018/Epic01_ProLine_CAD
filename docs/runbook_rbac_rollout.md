# Runbook — RBAC + RLS Production Rollout (Phase E2)

**Status:** Draft — pending change window  
**Window:** **TBD** (insert UTC date/time once approved by ops)  
**Estimated execution time:** 5–10 min DDL + 5 min smoke verification  
**Blast radius:** dashboard read/write paths (audit_log_actions, mcp_contexts)  
**Owner:** backend / platform

---

## 1. Why we are doing this

Phase E2 introduces row-level security (RLS) and a four-role RBAC model
backed by Postgres roles. Migrations `0007 → 0011` collectively:

| Rev | Effect |
|-----|--------|
| 0007 | Widen `actor_role` enum (viewer/operator/reviewer/admin). |
| 0008 | Create `app_viewer/operator/reviewer/admin` NOLOGIN roles + GRANTs to **migrator** (CURRENT_USER). |
| 0009 | Enable RLS + policies on `mcp_contexts` and `audit_log_actions`. |
| **0010** | **Parameterised** GRANT of `app_*` membership to the **runtime login** named in `DASHBOARD_DB_LOGIN_ROLE` (default `proline`). This separates the migrator from the app login in prod. |
| **0011** | Backfill `audit_log_actions.actor` NULLs to `'system'` so legacy rows remain visible under RLS. |

After rollout, every API request runs in a transaction with
`SET LOCAL ROLE app_<role>` + `set_config('app.current_actor', ...)`, and
the database — not the app — enforces tenancy / role gating.

---

## 2. Pre-flight checklist (T-24h)

- [ ] Code merged to `main` past commit containing `0011_audit_actor_backfill`.
- [ ] CI green: `full_quality.yml` integration job (includes `tests/db/test_rls_smoke.py`) passing.
- [ ] Confirm prod app login name → set `DASHBOARD_DB_LOGIN_ROLE=<name>`.
  - Default `proline` is **dev only**. Prod login is typically `proline_app` or per-environment.
- [ ] Confirm migrator login has `CREATEROLE` + ownership of target schemas (needed to GRANT roles it doesn't own).
- [ ] Snapshot a recent backup (RPO ≤ 1h is sufficient; 0011 is idempotent so re-run is safe).
- [ ] Take a count of NULL actors **right now** for sizing:
  ```sql
  SELECT COUNT(*) FROM audit_log_actions WHERE actor IS NULL;
  ```
  If > 100k rows, schedule a maintenance window; the UPDATE is single-statement and runs under transactional DDL.
- [ ] Notify dashboard users: ~30s of API 503 expected during the migration window (Alembic holds AccessExclusiveLock briefly when enabling RLS).

---

## 3. Staging dry-run (T-1d)

Run on staging Postgres with a recent prod snapshot restored.

```pwsh
# Use a separate migrator DSN so DDL privileges don't leak into the app DSN
$env:MIGRATION_DSN          = "postgresql+psycopg2://migrator:***@stg-pg/proline_cad"
$env:POSTGRES_DSN           = "postgresql+psycopg2://proline_app:***@stg-pg/proline_cad"
$env:DASHBOARD_DB_LOGIN_ROLE = "proline_app"

# Apply
.\.venv\Scripts\python.exe -m alembic -c db/alembic.ini upgrade head

# Verify membership
.\.venv\Scripts\python.exe scripts\check_rbac_membership.py
# Expect: login='proline_app' membership: ['app_admin','app_operator','app_reviewer','app_viewer']

# Smoke RLS policies against staging
.\.venv\Scripts\python.exe -m pytest tests\db\test_rls_smoke.py -v
# Expect: 3 passed
```

**Pass criteria (must all be true before scheduling prod):**
1. Alembic ends at `0011_audit_actor_backfill (head)`.
2. `check_rbac_membership.py` lists all four `app_*` roles for the prod login.
3. RLS smoke `tests/db/test_rls_smoke.py` 3/3 passing.
4. Dashboard end-to-end happy-path (login → list runs → upload → quarantine accept) succeeds for each of viewer/operator/reviewer/admin tokens.

---

## 4. Production rollout — execution steps

### 4.1 Lock-in

```pwsh
$env:MIGRATION_DSN          = "postgresql+psycopg2://migrator:***@prod-pg/proline_cad"
$env:POSTGRES_DSN           = "postgresql+psycopg2://proline_app:***@prod-pg/proline_cad"  # for the app, not used by alembic
$env:DASHBOARD_DB_LOGIN_ROLE = "proline_app"
```

### 4.2 Snapshot current head + count NULL actors

```pwsh
.\.venv\Scripts\python.exe -m alembic -c db/alembic.ini current   # record output
psql "$env:MIGRATION_DSN" -c "SELECT COUNT(*) AS null_actors FROM audit_log_actions WHERE actor IS NULL;"
```

Record both numbers in the change ticket.

### 4.3 Apply migrations

```pwsh
.\.venv\Scripts\python.exe -m alembic -c db/alembic.ini upgrade head
```

Watch for these expected log lines:
- `Running upgrade 0007 -> 0008 ... rbac roles`
- `Running upgrade 0008 -> 0009 ... rls policies`
- `Running upgrade 0009 -> 0010_rbac_login_split` → no errors about missing login
- `Running upgrade 0010_rbac_login_split -> 0011_audit_actor_backfill` → NOTICE `0011: backfilled N audit rows with actor=system`

### 4.4 Post-apply verification (mandatory before unlocking)

```pwsh
# 1. Head check
.\.venv\Scripts\python.exe -m alembic -c db/alembic.ini current
# Expect: 0011_audit_actor_backfill (head)

# 2. Membership check
.\.venv\Scripts\python.exe scripts\check_rbac_membership.py

# 3. NULL actors residual must be 0
psql "$env:MIGRATION_DSN" -c "SELECT COUNT(*) FROM audit_log_actions WHERE actor IS NULL;"

# 4. Smoke RLS
.\.venv\Scripts\python.exe -m pytest tests\db\test_rls_smoke.py -v
```

### 4.5 App restart

Roll the dashboard backend pods (no schema change, but `app/deps.py`
already issues `SET LOCAL ROLE`; a fresh process pool clears any cached
connections holding the old privilege set).

### 4.6 Smoke prod traffic

- `GET /healthz` from each pod → 200.
- One read+write loop per role token (viewer 403 on POST, operator 200, etc.).

---

## 5. Rollback plan

The migration is reversible **down to 0009**. Order:

```pwsh
# Step 1: revert backfill (no-op by design, but advances revision pointer)
.\.venv\Scripts\python.exe -m alembic -c db/alembic.ini downgrade 0010_rbac_login_split

# Step 2: revert login-split GRANTs
.\.venv\Scripts\python.exe -m alembic -c db/alembic.ini downgrade 0009_rls_policies

# Step 3 (optional, full revert of RLS): only if blocking outage
.\.venv\Scripts\python.exe -m alembic -c db/alembic.ini downgrade 0008_rbac_pg_roles
```

> **Note:** Step 3 disables RLS policies entirely → all rows visible to
> the app login. Do not execute unless you are accepting that exposure
> for the rollback duration.

If the app cannot connect after rollout (most likely cause: wrong
`DASHBOARD_DB_LOGIN_ROLE` value), fix the env var on the running pods
**without** rolling back DDL — re-grant manually:

```sql
GRANT app_viewer, app_operator, app_reviewer, app_admin TO <correct_login>;
```

---

## 6. Decision points still open

- **Window date** — replace `TBD` in the header once ops approves.
- **Migrator vs app login**: If prod currently uses one superuser for both
  DDL and runtime, **do not deploy this rollout** until split. The whole
  point of 0010 is gone otherwise.
- **Audit retention**: `actor='system'` backfill is permanent. If
  compliance requires preserving the original NULL marker, snapshot
  `audit_log_actions` to cold storage before step 4.3.

---

## 7. Reference commits

- `f842f0f` — M1+M2 backend, web/, 0007–0009, Redis dev container.
- `059f35e` — 0010 login split, RLS smoke tests, web CI typecheck, email-validator.
- *(this commit)* — 0011 actor backfill, repo-local venv, runbook.
