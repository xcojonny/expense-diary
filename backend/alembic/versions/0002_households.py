"""Mehrbenutzerbetrieb: Haushalte, Nutzer, Mitgliedschaften, Einladungen, OIDC.

Der Haushalt wird zur Mandantengrenze (ADR-004). `receipts` und `items` bekommen
`household_id`, `api_tokens` bekommt `user_id` — alle drei `NOT NULL`.

**Handgeschrieben statt autogeneriert**, weil `autogenerate` die Spalten direkt
als `NOT NULL` anlegt. Auf einer Datenbank mit Bons scheitert das. Der Weg hier:
Spalte nullable anlegen → bestehende Zeilen einem Standard-Haushalt zuordnen →
erst dann `NOT NULL` erzwingen.

Revision ID: 0002_households
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_households"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Muss zu app/services/users.py passen, damit der Start denselben Nutzer findet.
SINGLE_USER_EMAIL = "haushalt@localhost"
DEFAULT_HOUSEHOLD_NAME = "Haushalt"


def _has_rows(connection: sa.Connection, table: str) -> bool:
    return bool(
        connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first()
    )


def upgrade() -> None:
    # --- Neue Tabellen --------------------------------------------------------
    op.create_table(
        "households",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_households_created_at", "households", ["created_at"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_created_at", "users", ["created_at"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "household_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('admin','member')", name="ck_members_role"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("household_id", "user_id", name="uq_members_household_user"),
    )
    op.create_index("ix_household_members_created_at", "household_members", ["created_at"])
    op.create_index("ix_household_members_household_id", "household_members", ["household_id"])
    op.create_index("ix_household_members_user_id", "household_members", ["user_id"])

    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("household_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invitations_created_at", "invitations", ["created_at"])
    op.create_index("ix_invitations_household_id", "invitations", ["household_id"])
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"], unique=True)

    op.create_table(
        "oidc_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject", name="uq_oidc_issuer_subject"),
    )
    op.create_index("ix_oidc_identities_created_at", "oidc_identities", ["created_at"])
    op.create_index("ix_oidc_identities_user_id", "oidc_identities", ["user_id"])

    # --- Spalten nullable anlegen --------------------------------------------
    with op.batch_alter_table("receipts") as batch_op:
        batch_op.add_column(sa.Column("household_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(sa.Column("household_id", sa.Integer(), nullable=True))
    with op.batch_alter_table("api_tokens") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))

    # --- Bestehende Daten übernehmen -----------------------------------------
    connection = op.get_bind()
    needs_default = any(
        _has_rows(connection, table) for table in ("receipts", "items", "api_tokens")
    )
    if needs_default:
        # Genau ein Haushalt und ein Nutzer — die Instanz war bisher einbenutzig.
        connection.execute(
            sa.text(
                "INSERT INTO households (name, created_at, updated_at) "
                "VALUES (:name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"name": DEFAULT_HOUSEHOLD_NAME},
        )
        household_id = connection.execute(
            sa.text("SELECT id FROM households ORDER BY id LIMIT 1")
        ).scalar_one()

        connection.execute(
            sa.text(
                "INSERT INTO users (email, display_name, is_active, created_at, updated_at) "
                "VALUES (:email, :name, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"email": SINGLE_USER_EMAIL, "name": DEFAULT_HOUSEHOLD_NAME},
        )
        user_id = connection.execute(
            sa.text("SELECT id FROM users WHERE email = :email"), {"email": SINGLE_USER_EMAIL}
        ).scalar_one()

        connection.execute(
            sa.text(
                "INSERT INTO household_members "
                "(household_id, user_id, role, created_at, updated_at) "
                "VALUES (:household_id, :user_id, 'admin', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"household_id": household_id, "user_id": user_id},
        )

        connection.execute(
            sa.text("UPDATE receipts SET household_id = :hid"), {"hid": household_id}
        )
        connection.execute(
            sa.text("UPDATE items SET household_id = :hid"), {"hid": household_id}
        )
        connection.execute(sa.text("UPDATE api_tokens SET user_id = :uid"), {"uid": user_id})

    # --- Jetzt NOT NULL, Indizes und Fremdschlüssel --------------------------
    # Namen ausdrücklich setzen: SQLite kann unbenannte Constraints nicht löschen,
    # der Downgrade unten braucht sie.
    with op.batch_alter_table("receipts") as batch_op:
        batch_op.alter_column("household_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_index("ix_receipts_household_id", ["household_id"])
        batch_op.create_foreign_key(
            "fk_receipts_household", "households", ["household_id"], ["id"], ondelete="CASCADE"
        )

    with op.batch_alter_table("items") as batch_op:
        batch_op.alter_column("household_id", existing_type=sa.Integer(), nullable=False)
        # Eindeutigkeit wandert von global auf „pro Haushalt".
        batch_op.drop_index("ix_items_normalized_name")
        batch_op.create_index("ix_items_normalized_name", ["normalized_name"])
        batch_op.create_index("ix_items_household_id", ["household_id"])
        batch_op.create_unique_constraint(
            "uq_items_household_name", ["household_id", "normalized_name"]
        )
        batch_op.create_foreign_key(
            "fk_items_household", "households", ["household_id"], ["id"], ondelete="CASCADE"
        )

    with op.batch_alter_table("api_tokens") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_index("ix_api_tokens_user_id", ["user_id"])
        batch_op.create_foreign_key(
            "fk_api_tokens_user", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    """Zurück zum Einzelnutzer-Schema.

    Die Bons bleiben erhalten — nur die Haushaltszuordnung fällt weg. Bei mehreren
    Haushalten würden dabei ihre Artikelkataloge zusammenfallen; die
    Eindeutigkeit auf `normalized_name` bricht dann. Deshalb: nur zurückrollen,
    solange es einen Haushalt gibt.
    """
    connection = op.get_bind()
    households = connection.execute(sa.text("SELECT COUNT(*) FROM households")).scalar_one()
    if households > 1:
        raise RuntimeError(
            f"Downgrade abgelehnt: {households} Haushalte vorhanden. Artikel wären "
            "danach nicht mehr eindeutig. Erst auf einen Haushalt reduzieren."
        )

    with op.batch_alter_table("api_tokens") as batch_op:
        batch_op.drop_constraint("fk_api_tokens_user", type_="foreignkey")
        batch_op.drop_index("ix_api_tokens_user_id")
        batch_op.drop_column("user_id")

    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_constraint("fk_items_household", type_="foreignkey")
        batch_op.drop_constraint("uq_items_household_name", type_="unique")
        batch_op.drop_index("ix_items_household_id")
        batch_op.drop_index("ix_items_normalized_name")
        batch_op.create_index("ix_items_normalized_name", ["normalized_name"], unique=True)
        batch_op.drop_column("household_id")

    with op.batch_alter_table("receipts") as batch_op:
        batch_op.drop_constraint("fk_receipts_household", type_="foreignkey")
        batch_op.drop_index("ix_receipts_household_id")
        batch_op.drop_column("household_id")

    op.drop_index("ix_oidc_identities_user_id", table_name="oidc_identities")
    op.drop_index("ix_oidc_identities_created_at", table_name="oidc_identities")
    op.drop_table("oidc_identities")

    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_index("ix_invitations_household_id", table_name="invitations")
    op.drop_index("ix_invitations_created_at", table_name="invitations")
    op.drop_table("invitations")

    op.drop_index("ix_household_members_user_id", table_name="household_members")
    op.drop_index("ix_household_members_household_id", table_name="household_members")
    op.drop_index("ix_household_members_created_at", table_name="household_members")
    op.drop_table("household_members")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_created_at", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_households_created_at", table_name="households")
    op.drop_table("households")
