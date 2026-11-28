# backend/migrations/versions/0001_initial_release_schema.py
# =====================================================================
# EFHC Bot — self-contained frozen initial release schema для PostgreSQL.
#
# Greenfield CANON:
# - это единственная Alembic revision; 0002+ отсутствуют;
# - первый production launch создаётся на чистой БД;
# - physical schema snapshot находится в ЭТОМ migration-файле и не
#   импортирует текущие app.models / release metadata;
# - изменение ORM после release не может молча изменить DDL 0001;
# - users.global_id — physical BIGINT PK и единственный user owner;
# - provider identity хранится в user_identities; TON ownership — в wallet_bindings;
# - удалённые panels_archive/ranks_* не создаются.
# =====================================================================

from __future__ import annotations

import sys

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

CORE = "efhc_core"
ADMIN = "efhc_admin"

ECONOMIC_GUARD_MARKER = (
    "payment_intents external tx hash partial unique index"
)

EXPECTED_TABLE_COUNT = 53
EXPECTED_TABLES = frozenset({
    ('efhc_admin', 'admin_action_log'),
    ('efhc_admin', 'admin_nft_whitelist'),
    ('efhc_admin', 'admin_notifications'),
    ('efhc_admin', 'admin_role'),
    ('efhc_admin', 'admin_whitelist'),
    ('efhc_admin', 'efhc_sale_packages'),
    ('efhc_admin', 'idempotency_key'),
    ('efhc_core', 'achievements'),
    ('efhc_core', 'ad_admin_audit_log'),
    ('efhc_core', 'ad_daily_counters'),
    ('efhc_core', 'ad_events'),
    ('efhc_core', 'ad_provider_claims'),
    ('efhc_core', 'ad_provider_configs'),
    ('efhc_core', 'ad_provider_daily_metrics'),
    ('efhc_core', 'ad_sessions'),
    ('efhc_core', 'ads'),
    ('efhc_core', 'app_settings'),
    ('efhc_core', 'auth_challenges'),
    ('efhc_core', 'auth_sessions'),
    ('efhc_core', 'bank_balance'),
    ('efhc_core', 'bank_metrics_snapshot'),
    ('efhc_core', 'efhc_transfers_log'),
    ('efhc_core', 'hub_links'),
    ('efhc_core', 'outcome_fallback_promos'),
    ('efhc_core', 'panels'),
    ('efhc_core', 'payment_intents'),
    ('efhc_core', 'processed_external_events'),
    ('efhc_core', 'referral_bonus_ledger'),
    ('efhc_core', 'referral_codes'),
    ('efhc_core', 'referral_links'),
    ('efhc_core', 'scheduler_task_log'),
    ('efhc_core', 'shop_items'),
    ('efhc_core', 'shop_orders'),
    ('efhc_core', 'system_templates'),
    ('efhc_core', 'task_bonus_log'),
    ('efhc_core', 'task_complete_lock'),
    ('efhc_core', 'task_submissions'),
    ('efhc_core', 'tasks'),
    ('efhc_core', 'ton_inbox_logs'),
    ('efhc_core', 'tx_hash_locks'),
    ('efhc_core', 'unmatched_incoming'),
    ('efhc_core', 'user_cosmetics'),
    ('efhc_core', 'user_identities'),
    ('efhc_core', 'user_roles'),
    ('efhc_core', 'user_skins'),
    ('efhc_core', 'user_tasks_status'),
    ('efhc_core', 'users'),
    ('efhc_core', 'wallet_bindings'),
    ('efhc_core', 'wallet_connect_idempotency'),
    ('efhc_core', 'wallet_proof_token_uses'),
    ('efhc_core', 'withdraw_outcome_events'),
    ('efhc_core', 'withdraw_requests'),
    ('efhc_core', 'withdrawals'),
})

def _build_release_metadata() -> sa.MetaData:
    """Построить замороженный physical schema snapshot release 0001."""
    metadata = sa.MetaData()
    global_id_sequence = sa.Sequence(
        'users_global_id_seq', schema=CORE, start=1, increment=1,
        minvalue=1, maxvalue=9_999_999_999, cycle=False,
    )
    # Снимок источника: achievements_models.py:Achievement
    sa.Table('achievements', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('level', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('global_id', 'level', name='uq_achievements_global_level'),
        schema='efhc_core',
    )
    # Снимок источника: admin_models.py:AdminWhitelist
    sa.Table('admin_whitelist', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='PK записи', nullable=False),
        sa.Column('tg_id', sa.BigInteger, nullable=True, index=True, comment='Telegram provider subject; не actor owner'),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_admin_whitelist_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), nullable=False, index=True, comment='Канонический account/actor owner администратора.'),
        sa.Column('ton_wallet_id', sa.String(128), nullable=True, comment='ton_wallet_id: адрес TON-кошелька как provider subject'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true'), comment='Статус: активен/заблокирован'),
        sa.Column('note', sa.String(255), nullable=True, comment='Комментарий'),
        sa.Column('added_by_tg_id', sa.BigInteger, nullable=True, comment='Telegram ID того, кто добавил админа'),
        sa.Column('added_by_global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_admin_whitelist_added_global_users_global_id', onupdate='RESTRICT', ondelete='SET NULL'), nullable=True, index=True, comment='Канонический actor; tg_id остаётся provider metadata.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда создан (UTC)'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда обновлён (UTC)'),
        sa.UniqueConstraint('tg_id', name='uq_admin_whitelist_telegram'),
        sa.UniqueConstraint('global_id', name='uq_admin_whitelist_global_id'),
        sa.UniqueConstraint('ton_wallet_id', name='uq_admin_whitelist_ton'),
        schema='efhc_admin',
    )
    # Снимок источника: admin_models.py:AdminNftWhitelist
    sa.Table('admin_nft_whitelist', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('ton_wallet_id', sa.String(128), nullable=False, comment='Канонический TON provider subject резервного Admin NFT-доступа.'),
        sa.Column('role', sa.String(32), nullable=False, server_default=sa.text("'admin'"), comment='RBAC-совместимая роль резервного Admin NFT-доступа.'),
        sa.Column('nft_id', sa.String(256), nullable=True, comment='Точный NFT-item address, обнаруженный у текущего владельца.'),
        sa.Column('source', sa.String(32), nullable=False, server_default=sa.text("'env_nft'")),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('ton_wallet_id', name='uq_admin_nft_whitelist_ton_wallet_id'),
        schema='efhc_admin',
    )
    # Снимок источника: admin_models.py:AdminRole
    sa.Table('admin_role', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='PK записи роли', nullable=False),
        sa.Column('admin_id', sa.BigInteger, sa.ForeignKey("efhc_admin.admin_whitelist.id", ondelete='CASCADE', onupdate='CASCADE', name='fk_admin_role_admin'), nullable=False, index=True, comment='FK → AdminWhitelist.id'),
        sa.Column('role', sa.Enum('superadmin', 'admin', 'support', 'auditor', name='enum_admin_role', schema='efhc_admin', create_constraint=True), nullable=False, comment='Название роли'),
        sa.Column('granted_by_tg_id', sa.BigInteger, nullable=True, comment='Кто назначил (Telegram ID)'),
        sa.Column('granted_by_global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_admin_role_granted_global_users_global_id', onupdate='RESTRICT', ondelete='SET NULL'), nullable=True, index=True, comment='Канонический actor назначения роли.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда назначена роль (UTC)'),
        sa.UniqueConstraint('admin_id', 'role', name='uq_admin_role_pair'),
        schema='efhc_admin',
    )
    # Снимок источника: admin_models.py:AdminActionLog
    sa.Table('admin_action_log', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='PK записи лога', nullable=False),
        sa.Column('admin_id', sa.BigInteger, nullable=True, index=True, comment='Legacy local/provider audit metadata; не actor owner'),
        sa.Column('actor_global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_admin_action_actor_global_users_global_id', onupdate='RESTRICT', ondelete='SET NULL'), nullable=True, index=True, comment='Канонический actor owner административного действия.'),
        sa.Column('action', sa.String(64), nullable=False, index=True, comment='Короткое имя действия'),
        sa.Column('target_type', sa.String(64), nullable=True, index=True, comment='Тип цели'),
        sa.Column('target_id', sa.String(128), nullable=True, index=True, comment='Идентификатор цели'),
        sa.Column('details_json', postgresql.JSONB, nullable=True, comment='Подробности действия в JSON'),
        sa.Column('ip', sa.String(64), nullable=True, comment='IP-адрес источника (если известен)'),
        sa.Column('user_agent', sa.Text, nullable=True, comment='User-Agent клиента (если известен)'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда зафиксировано действие (UTC)'),
        schema='efhc_admin',
    )
    # Снимок источника: admin_models.py:IdempotencyKey
    sa.Table('idempotency_key', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='PK записи ключа', nullable=False),
        sa.Column('key', sa.String(128), nullable=False, comment='Уникальный идемпотентный ключ (или его хэш)'),
        sa.Column('scope', sa.String(64), nullable=True, index=True, comment='Область применения ключа'),
        sa.Column('request_fingerprint', sa.String(128), nullable=True, comment='Хэш входных данных запроса'),
        sa.Column('used', sa.Boolean, nullable=False, server_default=sa.text('false'), index=True, comment='Признак, что ключ уже использован'),
        sa.Column('response_code', sa.BigInteger, nullable=True, comment='Код результата первой обработки'),
        sa.Column('response_payload_json', postgresql.JSONB, nullable=True, comment='Часть ответа первой обработки'),
        sa.Column('admin_id', sa.BigInteger, sa.ForeignKey("efhc_admin.admin_whitelist.id", ondelete='SET NULL', onupdate='CASCADE', name='fk_idempotency_key_admin'), nullable=True, index=True, comment='FK → AdminWhitelist.id (если из админки)'),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_idempotency_global_users_global_id', onupdate='RESTRICT', ondelete='SET NULL'), nullable=True, index=True, comment='Канонический owner административной идемпотентности.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда создан ключ (UTC)'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, index=True, comment='Когда ключ истекает (UTC)'),
        sa.UniqueConstraint('key', name='uq_idempotency_key_key'),
        schema='efhc_admin',
    )
    # Снимок источника: admin_models.py:EFHCSalePackage
    sa.Table('efhc_sale_packages', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='PK пакета', nullable=False),
        sa.Column('title', sa.String(128), nullable=False, comment='Название пакета'),
        sa.Column('asset', sa.String(16), nullable=False, server_default=sa.text("'TON'"), comment='Актив цены (TON/USDT и т.п.)'),
        sa.Column('price_asset_d8', sa.Numeric(30, 8), nullable=False, comment='Цена в asset (scale=8)'),
        sa.Column('efhc_amount_d8', sa.Numeric(30, 8), nullable=False, comment='Сколько EFHC выдаём (scale=8)'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true'), comment='Активен ли пакет'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда создан (UTC)'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда обновлён (UTC)'),
        schema='efhc_admin',
    )
    # Снимок источника: admin_models.py:AdminNotification
    sa.Table('admin_notifications', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('event', sa.String(128), nullable=False),
        sa.Column('payload_json', sa.Text, nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default=sa.text("'NEW'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Index('ix_admin_notifications_status', 'status'),
        sa.Index('ix_admin_notifications_created_at', 'created_at'),
        schema='efhc_admin',
    )
    # Снимок источника: ads_models.py:Ad
    sa.Table('ads', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='active'),
        sa.Column('weight', sa.Integer, nullable=False, server_default='1'),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema='efhc_core',
    )
    # Снимок источника: ads_models.py:AdProviderConfig
    sa.Table('ad_provider_configs', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('code', sa.String(48), nullable=False, index=True),
        sa.Column('display_name', sa.String(128), nullable=False),
        sa.Column('enabled', sa.Boolean, nullable=False),
        sa.Column('priority', sa.Integer, nullable=False),
        sa.Column('miniapp_enabled', sa.Boolean, nullable=False),
        sa.Column('bot_enabled', sa.Boolean, nullable=False),
        sa.Column('rewarded_enabled', sa.Boolean, nullable=False),
        sa.Column('config_json', sa.JSON, nullable=True),
        sa.Column('public_config_json', sa.JSON, nullable=True),
        sa.Column('secret_config_encrypted', sa.Text, nullable=True),
        sa.Column('countries_allow', sa.JSON, nullable=True),
        sa.Column('countries_block', sa.JSON, nullable=True),
        sa.Column('languages_allow', sa.JSON, nullable=True),
        sa.Column('languages_block', sa.JSON, nullable=True),
        sa.Column('verification_mode', sa.String(32), nullable=False),
        sa.Column('verification_level', sa.String(8), nullable=False),
        sa.Column('moderation_status', sa.String(32), nullable=True),
        sa.Column('health_status', sa.String(32), nullable=False),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_code', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.UniqueConstraint('code', name='uq_ad_provider_configs_code'),
        sa.CheckConstraint('priority >= 0', name='ck_ad_provider_priority_nonnegative'),
        schema='efhc_core',
    )
    # Снимок источника: ads_models.py:AdSession
    sa.Table('ad_sessions', metadata,
        sa.Column('session_id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('task_code', sa.String(64), nullable=False, index=True),
        sa.Column('primary_provider', sa.String(48), nullable=True),
        sa.Column('actual_provider', sa.String(48), nullable=True, index=True),
        sa.Column('provider_ref', sa.String(255), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, index=True),
        sa.Column('app_language', sa.String(16), nullable=False),
        sa.Column('country_code', sa.String(2), nullable=True),
        sa.Column('platform', sa.String(32), nullable=True),
        sa.Column('reward_snapshot_efhcb', sa.Numeric(18, 8), nullable=False),
        sa.Column('provider_public_config', sa.JSON, nullable=True),
        sa.Column('attempted_providers', sa.JSON, nullable=True),
        sa.Column('verification_level', sa.String(8), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.Column('shown_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rewarded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reward_slot_reserved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('task_slot_reserved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('estimated_revenue_usd', sa.Numeric(18, 8), nullable=True),
        sa.Column('actual_revenue_usd', sa.Numeric(18, 8), nullable=True),
        sa.Column('failure_code', sa.String(64), nullable=True),
        sa.Column('fallback_count', sa.Integer, nullable=False),
        sa.Column('test_mode', sa.Boolean, nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_ad_sessions_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_ad_sessions_global_id_range'),
        sa.CheckConstraint('fallback_count >= 0', name='ck_ad_sessions_fallback_nonnegative'),
        sa.UniqueConstraint('actual_provider', 'provider_ref', name='uq_ad_sessions_provider_ref'),
        schema='efhc_core',
    )
    # Снимок источника: ads_models.py:AdDailyCounter
    sa.Table('ad_daily_counters', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('task_code', sa.String(64), nullable=False, index=True),
        sa.Column('utc_date', sa.Date, nullable=False, index=True),
        sa.Column('attempts', sa.Integer, nullable=False),
        sa.Column('successful_views', sa.Integer, nullable=False),
        sa.Column('rewards', sa.Integer, nullable=False),
        sa.Column('reserved_rewards', sa.Integer, nullable=False),
        sa.Column('last_view_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.UniqueConstraint('global_id', 'task_code', 'utc_date', name='uq_ad_daily_counter_owner_task_day'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_ad_daily_counter_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('attempts >= 0', name='ck_ad_daily_attempts_nonnegative'),
        sa.CheckConstraint('successful_views >= 0', name='ck_ad_daily_success_nonnegative'),
        sa.CheckConstraint('rewards >= 0', name='ck_ad_daily_rewards_nonnegative'),
        sa.CheckConstraint('reserved_rewards >= 0', name='ck_ad_daily_reserved_nonnegative'),
        schema='efhc_core',
    )
    # Снимок источника: ads_models.py:AdEvent
    sa.Table('ad_events', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('session_id', sa.String(36), nullable=False, index=True),
        sa.Column('provider', sa.String(48), nullable=True, index=True),
        sa.Column('task_code', sa.String(64), nullable=False, index=True),
        sa.Column('event_type', sa.String(48), nullable=False, index=True),
        sa.Column('provider_event_id', sa.String(255), nullable=True),
        sa.Column('estimated_revenue_usd', sa.Numeric(18, 8), nullable=True),
        sa.Column('actual_revenue_usd', sa.Numeric(18, 8), nullable=True),
        sa.Column('metadata_json', sa.JSON, nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), index=True),
        sa.UniqueConstraint('provider', 'provider_event_id', 'event_type', name='uq_ad_events_provider_event_type'),
        schema='efhc_core',
    )
    # Снимок источника: ads_models.py:AdProviderClaim
    sa.Table('ad_provider_claims', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('provider', sa.String(48), nullable=False, index=True),
        sa.Column('provider_event_id', sa.String(255), nullable=False),
        sa.Column('session_id', sa.String(36), nullable=False, index=True),
        sa.Column('global_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.UniqueConstraint('provider', 'provider_event_id', name='uq_ad_provider_claims_provider_event'),
        sa.ForeignKeyConstraint(['session_id'], ["efhc_core.ad_sessions.session_id"], name='fk_ad_provider_claims_session', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_ad_provider_claims_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_ad_provider_claims_global_id_range'),
        schema='efhc_core',
    )
    # Снимок источника: ads_models.py:AdAdminAuditLog
    sa.Table('ad_admin_audit_log', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('admin_global_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('provider', sa.String(48), nullable=False, index=True),
        sa.Column('field_name', sa.String(64), nullable=True),
        sa.Column('action', sa.String(64), nullable=False, index=True),
        sa.Column('metadata_json', sa.JSON, nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), index=True),
        schema='efhc_core',
    )
    # Снимок источника: ads_models.py:AdProviderDailyMetric
    sa.Table('ad_provider_daily_metrics', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('metric_date', sa.Date, nullable=False, index=True),
        sa.Column('provider', sa.String(48), nullable=False, index=True),
        sa.Column('country_code', sa.String(2), nullable=True),
        sa.Column('app_language', sa.String(16), nullable=True),
        sa.Column('task_code', sa.String(64), nullable=True),
        sa.Column('requests', sa.Integer, nullable=False),
        sa.Column('fills', sa.Integer, nullable=False),
        sa.Column('impressions', sa.Integer, nullable=False),
        sa.Column('completed_views', sa.Integer, nullable=False),
        sa.Column('valued_events', sa.Integer, nullable=False),
        sa.Column('clicks', sa.Integer, nullable=False),
        sa.Column('fallbacks_in', sa.Integer, nullable=False),
        sa.Column('fallbacks_out', sa.Integer, nullable=False),
        sa.Column('errors', sa.Integer, nullable=False),
        sa.Column('no_fill', sa.Integer, nullable=False),
        sa.Column('estimated_revenue_usd', sa.Numeric(18, 8), nullable=False),
        sa.Column('confirmed_revenue_usd', sa.Numeric(18, 8), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.UniqueConstraint('metric_date', 'provider', 'country_code', 'app_language', 'task_code', name='uq_ad_provider_daily_metric_dimensions'),
        schema='efhc_core',
    )
    # Снимок источника: auth_models.py:AuthChallenge
    sa.Table('auth_challenges', metadata,
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=False, nullable=False),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('provider_tenant', sa.String(128), nullable=False, server_default=sa.text(f"'{'default'}'")),
        sa.Column('purpose', sa.String(64), nullable=False),
        sa.Column('domain', sa.String(255), nullable=False),
        sa.Column('challenge_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('consumed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('invalidated_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id', name='pk_auth_challenges'),
        sa.UniqueConstraint('challenge_hash', name='uq_auth_challenges_challenge_hash'),
        sa.CheckConstraint("provider ~ '^[a-z][a-z0-9_]{0,31}$'", name='ck_auth_challenges_provider_format'),
        sa.CheckConstraint("provider <> 'mock'", name='ck_auth_challenges_provider_not_mock'),
        sa.CheckConstraint('char_length(provider_tenant) BETWEEN 1 AND 128 AND provider_tenant = btrim(provider_tenant)', name='ck_auth_challenges_tenant'),
        sa.CheckConstraint("purpose ~ '^[a-z][a-z0-9_.:-]{0,63}$'", name='ck_auth_challenges_purpose'),
        sa.CheckConstraint('char_length(domain) BETWEEN 1 AND 255 AND domain = btrim(domain)', name='ck_auth_challenges_domain'),
        sa.CheckConstraint("challenge_hash ~ '^[0-9a-f]{64}$'", name='ck_auth_challenges_hash'),
        sa.CheckConstraint('expires_at > created_at', name='ck_auth_challenges_expiry'),
        sa.CheckConstraint('NOT (consumed_at IS NOT NULL AND invalidated_at IS NOT NULL) AND (consumed_at IS NULL OR consumed_at >= created_at) AND (invalidated_at IS NULL OR invalidated_at >= created_at)', name='ck_auth_challenges_terminal_state'),
        sa.Index('ix_auth_challenges_expires_at', 'expires_at'),
        sa.Index('ix_auth_challenges_provider_purpose', 'provider', 'purpose'),
        schema='efhc_core',
    )
    # Снимок источника: auth_models.py:AuthSession
    sa.Table('auth_sessions', metadata,
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False),
        sa.Column('identity_id', sa.BigInteger, nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('revoked_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_seen_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id', name='pk_auth_sessions'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_auth_sessions_global_id_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['identity_id', 'global_id'], ["efhc_core.user_identities.id", "efhc_core.user_identities.global_id"], name='fk_auth_sessions_identity_global_user_identities', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.UniqueConstraint('token_hash', name='uq_auth_sessions_token_hash'),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name='ck_auth_sessions_token_hash'),
        sa.CheckConstraint("status IN ('active', 'revoked')", name='ck_auth_sessions_status'),
        sa.CheckConstraint('expires_at > created_at', name='ck_auth_sessions_expiry'),
        sa.CheckConstraint("(status = 'active' AND revoked_at IS NULL) OR (status = 'revoked' AND revoked_at IS NOT NULL)", name='ck_auth_sessions_revocation'),
        sa.Index('ix_auth_sessions_global_status', 'global_id', 'status'),
        sa.Index('ix_auth_sessions_identity_id', 'identity_id'),
        sa.Index('ix_auth_sessions_expires_at', 'expires_at'),
        schema='efhc_core',
    )
    # Снимок источника: auth_models.py:UserRole
    sa.Table('user_roles', metadata,
        sa.Column('id', sa.BigInteger, sa.Identity(start=1), nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False),
        sa.Column('role', sa.String(64), nullable=False),
        sa.Column('source', sa.String(32), nullable=False, server_default=sa.text("'system'")),
        sa.Column('status', sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column('granted_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('revoked_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id', name='pk_user_roles'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_user_roles_global_id_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.UniqueConstraint('global_id', 'role', name='uq_user_roles_global_id_role'),
        sa.CheckConstraint("role ~ '^[a-z][a-z0-9_.:-]{0,63}$'", name='ck_user_roles_role_format'),
        sa.CheckConstraint("source ~ '^[a-z][a-z0-9_.:-]{0,31}$'", name='ck_user_roles_source'),
        sa.CheckConstraint("status IN ('active', 'revoked')", name='ck_user_roles_status'),
        sa.CheckConstraint("(status = 'active' AND revoked_at IS NULL) OR (status = 'revoked' AND revoked_at IS NOT NULL)", name='ck_user_roles_revocation'),
        sa.Index('ix_user_roles_global_status', 'global_id', 'status'),
        schema='efhc_core',
    )
    # Снимок источника: bank_balance_models.py:BankBalance
    sa.Table('bank_balance', metadata,
        sa.Column('key', sa.String(32), primary_key=True, nullable=False),
        sa.Column('balance', sa.Numeric(30, 8), nullable=False, server_default='0'),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        schema='efhc_core',
    )
    # Снимок источника: bank_metrics_snapshot_models.py:BankMetricsSnapshot
    sa.Table('bank_metrics_snapshot', metadata,
        sa.Column('id', sa.SmallInteger, primary_key=True, nullable=False, server_default=sa.text('1')),
        sa.Column('reserve_efhc_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('circulation_efhc_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('users_main_efhc_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('users_bonus_efhc_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('actual_mass_efhc_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('panel_spent_efhc_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('generated_kwh_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('new_obligations_efhcm_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('fixed_obligations_efhcm_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('converted_kwh_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('pending_kwh_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('expected_supply_efhc_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('integrity_delta_efhc_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('reserve_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('circulation_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('new_obligations_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('users_main_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('users_bonus_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('actual_mass_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('fixed_obligations_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('panel_spent_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('generated_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('converted_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('pending_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('integrity_pct_d8', sa.BigInteger, nullable=False, server_default=sa.text('0')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.CheckConstraint('id = 1', name='ck_bank_metrics_snapshot_singleton'),
        sa.CheckConstraint('panel_spent_efhc_d8 >= 0', name='ck_bank_metrics_snapshot_spent_nonnegative'),
        sa.CheckConstraint('generated_kwh_d8 >= 0', name='ck_bank_metrics_snapshot_generated_nonnegative'),
        sa.CheckConstraint('converted_kwh_d8 >= 0', name='ck_bank_metrics_snapshot_converted_nonnegative'),
        schema='efhc_core',
    )
    # Снимок источника: external_events_models.py:ProcessedExternalEvent
    sa.Table('processed_external_events', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='Идентификатор записи.', nullable=False),
        sa.Column('provider', sa.String(64), nullable=False, index=True, comment='Имя провайдера (telegram, ads, ...).'),
        sa.Column('event_id', sa.String(128), nullable=False, index=True, comment='Хеш внешнего идентификатора события.'),
        sa.Column('resolved_global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_external_event_resolved_global_users_global_id', onupdate='RESTRICT', ondelete='SET NULL'), nullable=True, index=True, comment='Будущий resolved owner; provider/event_id неизменны.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись создана (UTC).'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись обновлена (UTC).'),
        sa.UniqueConstraint('provider', 'event_id', name='uq_processed_external_events_provider_event_id'),
        schema='efhc_core',
    )
    # Снимок источника: hub_links_models.py:HubLink
    sa.Table('hub_links', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('code', sa.String(64), nullable=False, index=True),
        sa.Column('title', sa.String(128), nullable=False),
        sa.Column('subtitle', sa.Text, nullable=True),
        sa.Column('url', sa.String(1024), nullable=False),
        sa.Column('target_kind', sa.String(32), nullable=False),
        sa.Column('open_mode', sa.String(32), nullable=False),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default=sa.text('100')),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
        sa.Column('icon_key', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись создана (UTC).'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись обновлена (UTC).'),
        sa.UniqueConstraint('code', name='uq_hub_links_code'),
        sa.CheckConstraint("target_kind IN ('external_url','internal_route','backend_handoff')", name='ck_hub_links_target_kind'),
        sa.CheckConstraint("open_mode IN ('same_app','new_tab','external_browser','telegram_webapp_route')", name='ck_hub_links_open_mode'),
        sa.Index('ix_hub_links_sort_order_id', 'sort_order', 'id'),
        schema='efhc_core',
    )
    # Снимок источника: identity_models.py:UserIdentity
    sa.Table('user_identities', metadata,
        sa.Column('id', sa.BigInteger, sa.Identity(start=1), nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('provider_tenant', sa.String(128), nullable=False, server_default=sa.text(f"'{'default'}'")),
        sa.Column('provider_subject', sa.String(512), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column('is_primary', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('is_verified', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('verified_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id', name='pk_user_identities'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_user_identities_global_id_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.UniqueConstraint('provider', 'provider_tenant', 'provider_subject', name='uq_user_identities_provider_tenant_subject'),
        sa.UniqueConstraint('id', 'global_id', name='uq_user_identities_id_global_id'),
        sa.CheckConstraint(f'global_id BETWEEN {1} AND {9999999999}', name='ck_user_identities_global_id_range'),
        sa.CheckConstraint("provider ~ '^[a-z][a-z0-9_]{0,31}$'", name='ck_user_identities_provider_format'),
        sa.CheckConstraint("provider <> 'mock'", name='ck_user_identities_provider_not_mock'),
        sa.CheckConstraint(f'char_length(provider_tenant) BETWEEN 1 AND {128} AND provider_tenant = btrim(provider_tenant)', name='ck_user_identities_tenant_length'),
        sa.CheckConstraint(f'char_length(provider_subject) BETWEEN 1 AND {512}', name='ck_user_identities_subject_length'),
        sa.CheckConstraint("status IN ('active', 'disabled', 'revoked')", name='ck_user_identities_status'),
        sa.CheckConstraint('(is_verified AND verified_at IS NOT NULL) OR (NOT is_verified AND verified_at IS NULL)', name='ck_user_identities_verified_at'),
        sa.CheckConstraint("NOT is_primary OR (is_verified AND status = 'active')", name='ck_user_identities_primary_state'),
        sa.Index('ix_user_identities_global_id', 'global_id'),
        sa.Index('ix_user_identities_provider_status', 'provider', 'status'),
        sa.Index('ix_user_identities_provider_subject', 'provider_subject'),
        sa.Index('uq_user_identities_primary_per_global', 'global_id', unique=True, postgresql_where=sa.text('is_primary')),
        schema='efhc_core',
    )
    # Снимок источника: outcome_models.py:WithdrawOutcomeEvent
    sa.Table('withdraw_outcome_events', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('withdraw_request_id', sa.BigInteger, sa.ForeignKey("efhc_core.withdraw_requests.id", ondelete='CASCADE'), nullable=False),
        sa.Column('tg_id', sa.BigInteger, nullable=False, comment='Telegram recipient; not a business owner.'),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_withdraw_outcome_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), nullable=False, index=True, comment='Единственный business owner записи.'),
        sa.Column('outcome_kind', sa.String(32), nullable=False),
        sa.Column('locale', sa.String(16), nullable=False),
        sa.Column('comment_template_key', sa.String(128), nullable=True),
        sa.Column('comment_text', sa.Text, nullable=False),
        sa.Column('comment_source', sa.String(32), nullable=False),
        sa.Column('manual_override_used', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('auto_translated', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('promo_enabled', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('promo_key', sa.String(128), nullable=True),
        sa.Column('promo_title', sa.Text, nullable=True),
        sa.Column('promo_body', sa.Text, nullable=True),
        sa.Column('promo_cta_label', sa.String(255), nullable=True),
        sa.Column('promo_cta_url', sa.String(512), nullable=True),
        sa.Column('promo_source', sa.String(32), nullable=True),
        sa.Column('source_snapshot', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись создана (UTC).'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись обновлена (UTC).'),
        sa.UniqueConstraint('withdraw_request_id', name='uq_withdraw_outcome_events_request_id'),
        schema='efhc_core',
    )
    # Снимок источника: outcome_models.py:OutcomeFallbackPromo
    sa.Table('outcome_fallback_promos', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('domain', sa.String(64), nullable=False),
        sa.Column('locale', sa.String(16), nullable=False),
        sa.Column('context', sa.String(64), nullable=True),
        sa.Column('title', sa.Text, nullable=True),
        sa.Column('body', sa.Text, nullable=True),
        sa.Column('cta_label', sa.String(255), nullable=True),
        sa.Column('cta_url', sa.String(512), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись создана (UTC).'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись обновлена (UTC).'),
        sa.UniqueConstraint('domain', 'locale', 'context', name='uq_outcome_fallback_promos_domain_locale_context'),
        schema='efhc_core',
    )
    # Снимок источника: panels_models.py:Panel
    sa.Table('panels', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true', index=True),
        sa.Column('is_archived', sa.Boolean, nullable=False, server_default='false', index=True),
        sa.Column('public_id', sa.String(12), nullable=False, index=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('activated_at', postgresql.TIMESTAMP(timezone=True), nullable=True, index=True),
        sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), nullable=True, index=True),
        sa.Column('archived_at', postgresql.TIMESTAMP(timezone=True), nullable=True, index=True),
        sa.Column('last_generated_at', postgresql.TIMESTAMP(timezone=True), nullable=True, index=True),
        sa.Column('base_gen_per_sec', sa.Numeric(30, 8), nullable=False, server_default='0'),
        sa.Column('generated_kwh', sa.Numeric(30, 8), nullable=False, server_default='0'),
        sa.Column('title', sa.String(64), nullable=True),
        sa.Column('meta', postgresql.JSONB, nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('generated_kwh >= 0', name='ck_panels_generated_nonneg'),
        sa.CheckConstraint('base_gen_per_sec >= 0', name='ck_panels_base_rate_nonneg'),
        sa.CheckConstraint('expires_at > activated_at', name='ck_panels_expires_gt_activated'),
        sa.UniqueConstraint('public_id', name='uq_panels_public_id'),
        sa.CheckConstraint(
            "public_id ~ '^PNL-[0-9]{8}$' AND public_id <> 'PNL-00000000'",
            name='ck_panels_public_id_pnl8',
        ),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_panels_global_id_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_panels_global_id_range'),
        schema='efhc_core',
    )
    # Снимок источника: payment_intents_models.py:PaymentIntent
    sa.Table('payment_intents', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('tg_id', sa.BigInteger, nullable=True, comment='Telegram provider attribute; nullable for TON-only owner.'),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_payment_intents_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), nullable=False, comment='Канонический владелец payment intent.'),
        sa.Column('purpose', sa.String(64), nullable=False),
        sa.Column('package_id', sa.BigInteger, nullable=True),
        sa.Column('asset', sa.String(16), nullable=False),
        sa.Column('amount_asset_d8', sa.Numeric(38, 8), nullable=False),
        sa.Column('efhc_amount_d8', sa.Numeric(38, 8), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('idempotency_key', sa.String(128), nullable=False),
        sa.Column('payload', sa.Text, nullable=False),
        sa.Column('to_address', sa.String(128), nullable=False),
        sa.Column('external_tx_hash', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Index('ix_payment_intents_global_id', 'global_id'),
        sa.UniqueConstraint('global_id', 'purpose', 'idempotency_key', name='uq_payment_intents_global_idempo'),
        sa.Index('ix_payment_intents_status', 'status'),
        sa.Index('ux_payment_intents_external_tx_hash_nn', 'external_tx_hash', unique=True, postgresql_where=sa.text('external_tx_hash IS NOT NULL')),
        schema='efhc_core',
    )
    # Снимок источника: referral_codes_models.py:ReferralCode
    sa.Table('referral_codes', metadata,
        sa.Column('code', sa.String, primary_key=True, nullable=False),
        sa.Column('inviter_global_id', sa.BigInteger, nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['inviter_global_id'], ["efhc_core.users.global_id"], name='fk_ref_codes_inviter_global_users_global_id', onupdate='RESTRICT', ondelete='CASCADE'),
        sa.UniqueConstraint('inviter_global_id', name='uq_referral_codes_inviter_global_id'),
        sa.CheckConstraint('inviter_global_id IS NULL OR inviter_global_id BETWEEN 1 AND 9999999999', name='ck_ref_codes_inviter_global_range'),
        sa.Index('ix_referral_codes_created_at', 'created_at'),
        schema='efhc_core',
    )
    # Снимок источника: referral_models.py:ReferralLink
    sa.Table('referral_links', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('inviter_global_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('invitee_global_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('activated_at', postgresql.TIMESTAMP(timezone=True), nullable=True, index=True),
        sa.Column('unit_reward_no', sa.Integer, nullable=True, comment='Номер monetary slot 1..10000 для direct referral reward.'),
        sa.Column('campaign', sa.String(64), nullable=True, index=True),
        sa.Column('meta', postgresql.JSONB, nullable=True),
        sa.UniqueConstraint('invitee_global_id', name='uq_referral_links_invitee_global_id'),
        sa.UniqueConstraint('inviter_global_id', 'unit_reward_no', name='uq_referral_links_inviter_unit_reward_no'),
        sa.ForeignKeyConstraint(['inviter_global_id'], ["efhc_core.users.global_id"], name='fk_ref_links_inviter_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['invitee_global_id'], ["efhc_core.users.global_id"], name='fk_ref_links_invitee_global_users_global_id', onupdate='RESTRICT', ondelete='CASCADE'),
        sa.CheckConstraint('inviter_global_id BETWEEN 1 AND 9999999999', name='ck_ref_links_inviter_global_range'),
        sa.CheckConstraint('invitee_global_id BETWEEN 1 AND 9999999999', name='ck_ref_links_invitee_global_range'),
        sa.CheckConstraint('inviter_global_id <> invitee_global_id', name='ck_ref_links_global_not_self'),
        sa.CheckConstraint('unit_reward_no IS NULL OR unit_reward_no BETWEEN 1 AND 10000', name='ck_ref_links_unit_reward_no_range'),
        schema='efhc_core',
    )
    # Снимок источника: referral_models.py:ReferralBonusLedger
    sa.Table('referral_bonus_ledger', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False, index=True),
        sa.Column('tg_id', sa.BigInteger, nullable=True),
        sa.Column('amount_efhc', sa.Numeric(20, 8), nullable=False),
        sa.Column('kind', sa.String(32), nullable=False, index=True),
        sa.Column('meta', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_ref_bonus_global_id_users_global_id', onupdate='RESTRICT', ondelete='CASCADE'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_ref_bonus_global_id_range'),
        schema='efhc_core',
    )
    # Снимок источника: scheduler_models.py:SchedulerTaskLog
    sa.Table('scheduler_task_log', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=True),
        sa.Column('task_name', sa.String(128), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('error_text', sa.Text, nullable=True),
        sa.Column('payload', sa.JSON, nullable=True),
        sa.Column('retry_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_sec', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_scheduler_task_log_global_id_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('global_id IS NULL OR global_id BETWEEN 1 AND 9999999999', name='ck_scheduler_task_log_global_id_range'),
        sa.Index('ix_scheduler_task_log_status_retry_time', 'status', 'retry_time'),
        sa.Index('ix_scheduler_task_log_global_id', 'global_id'),
        schema='efhc_core',
    )
    # Снимок источника: settings_models.py:AppSetting
    sa.Table('app_settings', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('key', sa.String(128), nullable=False),
        sa.Column('value', sa.String(2048), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Index('ix_app_settings_key', 'key', unique=True),
        schema='efhc_core',
    )
    # Снимок источника: shop_models.py:ShopItem
    sa.Table('shop_items', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('sku', sa.String(64), nullable=False, index=True),
        sa.Column('title', sa.String(128), nullable=False),
        sa.Column('description', sa.String(512), nullable=True),
        sa.Column('quantity_efhc', sa.Numeric(30, 8), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('extra', postgresql.JSONB, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('sku', name='uq_shop_items_sku'),
        schema='efhc_core',
    )
    # Снимок источника: shop_models.py:ShopOrder
    sa.Table('shop_orders', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_shop_orders_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), index=True, nullable=False, comment='Canonical global account owner'),
        sa.Column('type', sa.String(8), nullable=False, index=True),
        sa.Column('status', sa.String(24), nullable=False, index=True),
        sa.Column('quantity_efhc', sa.Numeric(30, 8), nullable=True),
        sa.Column('expected_amount', sa.Numeric(30, 8), nullable=True, comment='Ожидаемая сумма оплаты (TON и т.п.)'),
        sa.Column('tx_hash', sa.String(128), nullable=True, index=True),
        sa.Column('memo', sa.String(256), nullable=True),
        sa.Column('payment_error_log', sa.Text, nullable=True, comment='Последняя текстовая ошибка реконсиляции/оплаты'),
        sa.Column('idempotency_key', sa.String(128), nullable=True, index=True),
        sa.Column('extra', postgresql.JSONB, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('paid_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('fulfilled_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint('tx_hash', name='uq_shop_orders_tx_hash'),
        sa.UniqueConstraint('global_id', 'idempotency_key', name='uq_shop_orders_global_id_idempotency'),
        sa.CheckConstraint("(type = 'EFHC' OR type = 'NFT')", name='ck_shop_orders_type_enum'),
        sa.CheckConstraint('quantity_efhc IS NULL OR quantity_efhc >= 0', name='ck_shop_orders_qty_nonneg'),
        sa.CheckConstraint('expected_amount IS NULL OR expected_amount >= 0', name='ck_shop_orders_expected_nonneg'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_shop_orders_global_id_range'),
        schema='efhc_core',
    )
    # Снимок источника: shop_payment_tx_hash_lock_models.py:TxHashLock
    sa.Table('tx_hash_locks', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('tx_hash', sa.String(128), nullable=False),
        sa.Column('purpose', sa.String(64), nullable=False),
        sa.Column('intent_id', sa.BigInteger, nullable=True),
        sa.Column('order_id', sa.BigInteger, nullable=True),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_tx_hash_locks_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), nullable=False, comment='Канонический владелец tx hash lock.'),
        sa.Column('trusted_operation_at', sa.DateTime(timezone=True), nullable=False, comment='Доверенное время on-chain операции; после 180 суток первичный settlement запрещён.'),
        sa.Column('server_first_seen_at', sa.DateTime(timezone=True), nullable=False, comment='Первое server-side наблюдение операции; вторая временная граница settlement.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('tx_hash', name='uq_tx_hash_locks_tx_hash'),
        sa.Index('ix_tx_hash_locks_intent_id', 'intent_id'),
        sa.Index('ix_tx_hash_locks_global_id', 'global_id'),
        sa.Index('ix_tx_hash_locks_trusted_operation_at', 'trusted_operation_at'),
        schema='efhc_core',
    )
    # Снимок источника: skins_models.py:UserSkin
    sa.Table('user_skins', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_user_skins_global_users_global_id', onupdate='RESTRICT', ondelete='CASCADE'), nullable=False),
        sa.Column('skin_id', sa.Integer, nullable=False),
        sa.Column('purchased_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('global_id', 'skin_id', name='uq_user_skins_global_skin'),
        sa.Index('ix_user_skins_global_id', 'global_id'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_user_skins_global_id_range'),
        schema='efhc_core',
    )
    # Снимок источника: skins_models.py:UserCosmetics
    sa.Table('user_cosmetics', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_user_cosmetics_global_users_global_id', onupdate='RESTRICT', ondelete='CASCADE'), nullable=False),
        sa.Column('active_skin_id', sa.Integer, nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('global_id', name='uq_user_cosmetics_global_id'),
        sa.Index('ix_user_cosmetics_global_id', 'global_id'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_user_cosmetics_global_id_range'),
        schema='efhc_core',
    )
    # Снимок источника: system_templates_models.py:SystemTemplate
    sa.Table('system_templates', metadata,
        sa.Column('key', sa.String(128), primary_key=True, comment='Уникальный ключ шаблона.', nullable=False),
        sa.Column('content', sa.Text, nullable=True, comment='Содержимое шаблона.'),
        sa.Column('description', sa.String(255), nullable=False, comment='Описание шаблона для администратора.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись создана (UTC).'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись обновлена (UTC).'),
        schema='efhc_core',
    )
    # Снимок источника: tasks_models.py:Task
    sa.Table('tasks', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='Идентификатор задания.', nullable=False),
        sa.Column('code', sa.String(64), nullable=False, index=True, comment='Код задания, уникален в рамках таблицы.'),
        sa.Column('title', sa.String(255), nullable=False, comment='Короткий заголовок задания.'),
        sa.Column('description', sa.Text, nullable=True, comment='Описание задания, инструкции для пользователя.'),
        sa.Column('type', sa.String(50), nullable=False, index=True, comment='Тип задания: subscribe/join/visit/custom/watch_ad/...'),
        sa.Column('active', sa.Boolean, nullable=False, index=True, comment='Видимость задания пользователям.'),
        sa.Column('bonus_efhc', sa.Numeric(18, 8), nullable=False, comment='Сколько бонусных EFHC начислять за выполнение.'),
        sa.Column('price_usd_hint', sa.Numeric(18, 8), nullable=True, comment='Подсказка админам: сколько стоит задание в USD.'),
        sa.Column('limit_per_user', sa.Integer, nullable=False, comment='Сколько раз один пользователь может выполнить задание.'),
        sa.Column('total_limit', sa.Integer, nullable=True, comment='Глобальный лимит выполнений; NULL = без лимита.'),
        sa.Column('performed_count', sa.Integer, nullable=False, comment='Сколько выполнений уже одобрено.'),
        sa.Column('proof_type', sa.String(50), nullable=True, comment='Тип доказательства: url/screenshot/text/none/...'),
        sa.Column('proof_hint', sa.String(255), nullable=True, comment='Подсказка пользователю по доказательству.'),
        sa.Column('meta', sa.JSON, nullable=True, comment='JSON-метаданные задания для UI и portal continuity.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись создана (UTC).'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись обновлена (UTC).'),
        sa.UniqueConstraint('code', name='uq_tasks_code'),
        sa.CheckConstraint('bonus_efhc >= 0', name='chk_tasks_bonus_nonnegative'),
        sa.CheckConstraint('limit_per_user >= 0', name='chk_tasks_limit_per_user_nonnegative'),
        sa.CheckConstraint('(total_limit IS NULL) OR (total_limit >= 0)', name='chk_tasks_total_limit_nonnegative'),
        schema='efhc_core',
    )
    # Снимок источника: tasks_models.py:TaskSubmission
    sa.Table('task_submissions', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='Идентификатор отправки.', nullable=False),
        sa.Column('task_id', sa.BigInteger, sa.ForeignKey("efhc_core.tasks.id", ondelete='CASCADE'), nullable=False, index=True, comment='FK → tasks.id'),
        sa.Column('tg_id', sa.BigInteger, nullable=True, comment='Telegram ID только для уведомления пользователю.'),
        sa.Column('global_id', sa.BigInteger, nullable=False, comment='Канонический владелец отправки задания.'),
        sa.Column('status', sa.String(24), nullable=False, index=True, comment='Статус модерации/выплаты.'),
        sa.Column('proof_text', sa.Text, nullable=True, comment='Текстовое доказательство/комментарий.'),
        sa.Column('proof_url', sa.String(1024), nullable=True, comment='URL-доказательство.'),
        sa.Column('bonus_amount_efhc', sa.Numeric(18, 8), nullable=False, comment='Сколько EFHC начислено при одобрении.'),
        sa.Column('paid', sa.Boolean, nullable=False, index=True, comment='Флаг фактической выплаты EFHC.'),
        sa.Column('paid_tx_id', sa.BigInteger, nullable=True, index=True, comment='ID внутренней EFHC-транзакции, если есть.'),
        sa.Column('moderator_global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_task_submissions_moderator_global_users_global_id', onupdate='RESTRICT', ondelete='SET NULL'), nullable=True, index=True, comment='Канонический actor модерации по global_id.'),
        sa.Column('moderator_note', sa.Text, nullable=True, comment='Комментарий модератора.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись создана (UTC).'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись обновлена (UTC).'),
        sa.UniqueConstraint('task_id', 'global_id', name='uq_task_submissions_task_global_once'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_task_submissions_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_task_submissions_global_id_range'),
        sa.CheckConstraint('bonus_amount_efhc >= 0', name='chk_task_submissions_bonus_nonnegative'),
        schema='efhc_core',
    )
    # Снимок источника: tasks_models.py:UserTaskStatus
    sa.Table('user_tasks_status', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='Идентификатор статуса.', nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False, comment='Канонический владелец задания.'),
        sa.Column('task_code', sa.String(64), nullable=False, index=True, comment='Код задания.'),
        sa.Column('status', sa.String(24), nullable=False, index=True, comment='available/done/cooldown/pending_check/...'),
        sa.Column('last_completed_at', sa.DateTime(timezone=True), nullable=True, comment='Когда задание было завершено последний раз.'),
        sa.Column('next_available_at', sa.DateTime(timezone=True), nullable=True, comment='Когда задание снова станет доступным.'),
        sa.UniqueConstraint('global_id', 'task_code', name='uq_user_tasks_status_global_task_code'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_user_tasks_status_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_user_tasks_status_global_id_range'),
        schema='efhc_core',
    )
    # Снимок источника: tasks_models.py:TaskBonusLog
    sa.Table('task_bonus_log', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='Идентификатор записи журнала.', nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False, comment='Канонический владелец начисления.'),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Время начисления бонуса.'),
        sa.Column('task_code', sa.String(64), nullable=False, index=True, comment='Код задания.'),
        sa.Column('amount_bonus_efhc', sa.Numeric(18, 8), nullable=False, comment='Сумма начисленного бонуса.'),
        sa.Column('idempotency_key', sa.String(255), nullable=False, comment='Идемпотентный ключ начисления.'),
        sa.UniqueConstraint('idempotency_key', name='uq_task_bonus_log_idempotency_key'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_task_bonus_log_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_task_bonus_log_global_id_range'),
        schema='efhc_core',
    )
    # Снимок источника: tasks_models.py:TaskCompleteLock
    sa.Table('task_complete_lock', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, comment='Идентификатор lock-записи.', nullable=False),
        sa.Column('idempotency_key', sa.String(255), nullable=True, comment='Идемпотентный ключ.'),
        sa.Column('global_id', sa.BigInteger, nullable=False, comment='Канонический владелец lock-записи.'),
        sa.Column('task_code', sa.String(64), nullable=False, index=True, comment='Код задания.'),
        sa.Column('credited', sa.Boolean, nullable=False, server_default=sa.text('false'), comment='Флаг успешного начисления бонуса.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись создана (UTC).'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись обновлена (UTC).'),
        sa.UniqueConstraint('idempotency_key', name='uq_task_complete_lock_idempotency_key'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_task_complete_lock_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_task_complete_lock_global_id_range'),
        schema='efhc_core',
    )
    # Снимок источника: ton_logs_models.py:TonInboxLog
    sa.Table('ton_inbox_logs', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('tx_hash', sa.String(128), nullable=False, index=True),
        sa.Column('from_address', sa.String(128), nullable=True, index=True),
        sa.Column('to_address', sa.String(128), nullable=True, index=True),
        sa.Column('amount', sa.Numeric(30, 8), nullable=False, server_default='0'),
        sa.Column('memo', sa.String(512), nullable=True),
        sa.Column('parsed_kind', sa.String(32), nullable=True, index=True),
        sa.Column('parsed_tg_id', sa.BigInteger, nullable=True, index=True),
        sa.Column('resolved_global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_ton_inbox_resolved_global_users_global_id', onupdate='RESTRICT', ondelete='SET NULL'), nullable=True, index=True, comment='Будущий resolved owner; parsed_tg_id сохраняется.'),
        sa.Column('parsed_sku', sa.String(64), nullable=True, index=True),
        sa.Column('status', sa.String(32), nullable=False, index=True, server_default='received'),
        sa.Column('retries_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('next_retry_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('processed_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('trusted_operation_at', postgresql.TIMESTAMP(timezone=True), nullable=True, comment='Доверенное время внешней финансовой операции; NULL означает fail-closed для первичного зачисления.'),
        sa.Column('last_error', sa.String(512), nullable=True),
        sa.Column('meta', postgresql.JSONB, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('tx_hash', name='uq_ton_inbox_tx'),
        sa.CheckConstraint('amount >= 0', name='ck_ton_inbox_amount_nonneg'),
        schema='efhc_core',
    )
    # Снимок источника: ton_logs_models.py:UnmatchedIncoming
    sa.Table('unmatched_incoming', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('tx_hash', sa.String(128), nullable=False, index=True),
        sa.Column('asset', sa.String(16), nullable=False, server_default='TON'),
        sa.Column('amount_asset_d8', sa.Numeric(30, 8), nullable=False, server_default='0'),
        sa.Column('from_address', sa.String(128), nullable=True),
        sa.Column('to_address', sa.String(128), nullable=True),
        sa.Column('memo', sa.String(1024), nullable=True),
        sa.Column('utime', sa.BigInteger, nullable=True),
        sa.Column('reason', sa.String(128), nullable=True),
        sa.Column('resolved_global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_unmatched_resolved_global_users_global_id', onupdate='RESTRICT', ondelete='SET NULL'), nullable=True, index=True, comment='Будущий resolved owner; raw source сохраняется.'),
        sa.Column('meta', postgresql.JSONB, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('tx_hash', name='uq_unmatched_incoming_tx'),
        schema='efhc_core',
    )
    # Снимок источника: transactions_models.py:EfhcTransferLog
    sa.Table('efhc_transfers_log', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True, nullable=False),
        sa.Column('tg_id', sa.BigInteger, nullable=True, index=True, comment='Telegram provider attribute; nullable for TON-only owner.'),
        sa.Column('system_entity', sa.String(64), nullable=True, index=True, comment='Системная сторона проводки; для центрального банка используется BANK_EFHC. У банковской строки global_id/tg_id NULL.'),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_efhc_transfers_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), nullable=True, index=True, comment='Канонический владелец аккаунта; NULL допустим только для системной зеркальной строки банка.'),
        sa.Column('amount', sa.Numeric(30, 8), nullable=False),
        sa.Column('direction', sa.String(24), nullable=False, index=True),
        sa.Column('balance_type', sa.String(8), nullable=False, index=True),
        sa.Column('reason', sa.String(32), nullable=False, index=True),
        sa.Column('idempotency_key', sa.String(128), nullable=False, index=True),
        sa.Column('meta', sa.Text, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('idempotency_key', name='uq_efhc_transfers_idem_key'),
        sa.CheckConstraint('amount >= 0', name='ck_efhc_transfers_amount_nonneg'),
        sa.CheckConstraint("direction IN ('credit','debit')", name='ck_efhc_transfers_direction_enum'),
        sa.CheckConstraint("balance_type IN ('main','bonus')", name='ck_efhc_transfers_baltype_enum'),
        sa.CheckConstraint("system_entity IS NULL OR system_entity = 'BANK_EFHC'", name='ck_efhc_transfers_system_entity_enum'),
        sa.CheckConstraint("(system_entity = 'BANK_EFHC' AND global_id IS NULL AND tg_id IS NULL) OR (system_entity IS NULL AND global_id IS NOT NULL)", name='ck_efhc_transfers_owner_shape'),
        schema='efhc_core',
    )
    # Снимок источника: user_models.py:User
    sa.Table('users', metadata,
        sa.Column('global_id', sa.BigInteger, global_id_sequence, server_default=global_id_sequence.next_value(), primary_key=True, nullable=False),
        sa.Column('username', sa.String(64), nullable=True, index=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true', index=True),
        sa.Column('is_vip', sa.Boolean, nullable=False, server_default='false', index=True),
        sa.Column('vip_since', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('vip_checked_at', postgresql.TIMESTAMP(timezone=True), nullable=True, index=True),
        sa.Column('main_balance', sa.Numeric(30, 8), nullable=False, server_default='0'),
        sa.Column('bonus_balance', sa.Numeric(30, 8), nullable=False, server_default='0'),
        sa.Column('available_kwh', sa.Numeric, sa.Computed('CAST(GREATEST(CAST(total_generated_kwh AS numeric) - CAST(exchanged_kwh_total AS numeric), 0) AS numeric)', persisted=True), nullable=False),
        sa.Column('total_generated_kwh', sa.Numeric(30, 8), nullable=False, server_default='0'),
        sa.Column('exchanged_kwh_total', sa.Numeric(30, 8), nullable=False, server_default='0'),
        sa.Column('rank_position', sa.BigInteger, nullable=True, index=True),
        sa.Column('rank_score_kwh', sa.Numeric(30, 8), nullable=True),
        sa.Column('rank_calculated_at', postgresql.TIMESTAMP(timezone=True), nullable=True, index=True),
        sa.Column('last_seen_at', postgresql.TIMESTAMP(timezone=True), nullable=True, index=True),
        sa.Column('last_sync_at', postgresql.TIMESTAMP(timezone=True), nullable=True, index=True),
        sa.Column('meta', postgresql.JSONB, nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('global_id BETWEEN 1 AND 9999999999', name='ck_users_global_id_range'),
        sa.CheckConstraint("global_id <> 1313131313 OR COALESCE(meta ->> 'reserved_identity', '') = 'superadmin'", name='ck_users_superadmin_global_id_reserved'),
        sa.CheckConstraint('main_balance >= 0', name='ck_users__main__balance_nonneg'),
        sa.CheckConstraint('bonus_balance >= 0', name='ck_users_bonus_balance_nonneg'),
        sa.CheckConstraint('available_kwh >= 0', name='ck_users_available_kwh_nonneg'),
        sa.CheckConstraint('total_generated_kwh >= 0', name='ck_users_total_generated_kwh_nonneg'),
        sa.CheckConstraint('exchanged_kwh_total >= 0', name='ck_users_exchanged_kwh_total_nonneg'),
        sa.CheckConstraint('exchanged_kwh_total <= total_generated_kwh', name='ck_users_exchanged_le_total'),
        sa.CheckConstraint('available_kwh = (total_generated_kwh - exchanged_kwh_total)', name='ck_users_available_eq_mirror'),
        schema='efhc_core',
    )
    # Снимок источника: wallets_models.py:WalletBinding
    sa.Table('wallet_bindings', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('global_id', sa.BigInteger, nullable=False),
        sa.Column('tg_id', sa.BigInteger, nullable=True, index=True),
        sa.Column('wallet_address', sa.Text, unique=True, nullable=False),
        sa.Column('wallet_app', sa.String(32), nullable=True),
        sa.Column('is_primary', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('proof_verified', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('proof_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('proof_payload_hash', sa.Text, nullable=True),
        sa.Column('proof_source', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись создана (UTC).'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())"), comment='Когда запись обновлена (UTC).'),
        sa.ForeignKeyConstraint(['global_id'], ["efhc_core.users.global_id"], name='fk_wallet_bindings_global_id_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'),
        sa.CheckConstraint('global_id IS NOT NULL', name='ck_wallet_bindings_owner_reference'),
        sa.CheckConstraint('global_id IS NULL OR global_id BETWEEN 1 AND 9999999999', name='ck_wallet_bindings_global_id_range'),
        sa.Index('ix_wallet_bindings_global_id', 'global_id'),
        schema='efhc_core',
    )
    # Снимок источника: wallets_models.py:WalletConnectIdempotency
    sa.Table('wallet_connect_idempotency', metadata,
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_wallet_connect_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), nullable=False, primary_key=True, index=True, comment='Канонический account owner.'),
        sa.Column('tg_id', sa.BigInteger, nullable=True, index=True),
        sa.Column('idempotency_key', sa.Text, primary_key=True, nullable=False),
        sa.Column('wallet_id', sa.BigInteger, nullable=False),
        sa.Column('wallet_address', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.UniqueConstraint('global_id', 'idempotency_key', name='uq_wallet_connect_global_idk'),
        schema='efhc_core',
    )
    # Снимок источника: wallets_models.py:WalletProofTokenUse
    sa.Table('wallet_proof_token_uses', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('tg_id', sa.BigInteger, nullable=True),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_wallet_proof_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), nullable=False, index=True, comment='Канонический account owner proof marker.'),
        sa.Column('wallet_address', sa.Text, nullable=False),
        sa.Column('proof_payload_hash', sa.Text, nullable=False),
        sa.Column('idempotency_key', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
        sa.UniqueConstraint('proof_payload_hash', name='uq_wallet_proof_payload_hash'),
        schema='efhc_core',
    )
    # Снимок источника: withdraw_models.py:WithdrawRequest
    sa.Table('withdraw_requests', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('tg_id', sa.BigInteger, nullable=True, comment='Telegram delivery metadata; never a business owner or FK.'),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_withdraw_requests_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), nullable=False, index=True, comment='Канонический и единственный владелец заявки.'),
        sa.Column('amount', sa.Numeric(30, 8), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='PENDING'),
        sa.Column('idempotency_key', sa.String(128), nullable=False, unique=True),
        sa.Column('hold_done', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('refund_done', sa.Boolean, nullable=False, server_default=sa.text('false')),
        sa.Column('payout_ref', sa.String(128), nullable=True),
        sa.Column('external_address', sa.String(256), nullable=True),
        sa.Column('processing_idempotency_key', sa.String(128), nullable=True),
        sa.Column('tx_hash', sa.String(128), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('PENDING','PAID','REJECTED','CANCELED')", name='ck_withdraw_requests_status_enum'),
        sa.UniqueConstraint('processing_idempotency_key', name='uq_withdraw_processing_idempotency_key'),
        sa.UniqueConstraint('payout_ref', name='uq_withdraw_payout_ref'),
        schema='efhc_core',
    )
    # Снимок источника: withdraw_models.py:Withdrawal
    sa.Table('withdrawals', metadata,
        sa.Column('id', sa.BigInteger, primary_key=True, nullable=False),
        sa.Column('tg_id', sa.BigInteger, nullable=True, comment='Historical Telegram delivery metadata; not an owner or FK.'),
        sa.Column('global_id', sa.BigInteger, sa.ForeignKey("efhc_core.users.global_id", name='fk_withdrawals_global_users_global_id', onupdate='RESTRICT', ondelete='RESTRICT'), nullable=False, index=True, comment='Канонический owner deprecated-таблицы.'),
        sa.Column('amount_efhc', sa.Numeric(20, 8), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='requested'),
        sa.Column('idempotency_key', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('PENDING','PAID','REJECTED','CANCELED')", name='ck_payment_intents_status_enum'),
        schema='efhc_core',
    )
    # Снимок внешнего индекса: admin_models.py:ix_admin_whitelist_created_at
    sa.Index('ix_admin_whitelist_created_at', metadata.tables['efhc_admin.admin_whitelist'].c.created_at.desc())
    # Снимок внешнего индекса: admin_models.py:ix_admin_nft_whitelist_active_created
    sa.Index('ix_admin_nft_whitelist_active_created', metadata.tables['efhc_admin.admin_nft_whitelist'].c.is_active, metadata.tables['efhc_admin.admin_nft_whitelist'].c.created_at.desc())
    # Снимок внешнего индекса: admin_models.py:uq_admin_nft_whitelist_active_nft_id
    sa.Index('uq_admin_nft_whitelist_active_nft_id', metadata.tables['efhc_admin.admin_nft_whitelist'].c.nft_id, unique=True, postgresql_where=metadata.tables['efhc_admin.admin_nft_whitelist'].c.is_active.is_(True))
    # Снимок внешнего индекса: admin_models.py:ix_admin_role_created_at
    sa.Index('ix_admin_role_created_at', metadata.tables['efhc_admin.admin_role'].c.created_at.desc())
    # Снимок внешнего индекса: admin_models.py:ix_admin_action_log_created_at
    sa.Index('ix_admin_action_log_created_at', metadata.tables['efhc_admin.admin_action_log'].c.created_at.desc())
    # Снимок внешнего индекса: admin_models.py:ix_admin_action_log_action_type
    sa.Index('ix_admin_action_log_action_type', metadata.tables['efhc_admin.admin_action_log'].c.action, metadata.tables['efhc_admin.admin_action_log'].c.target_type)
    # Снимок внешнего индекса: admin_models.py:ix_idempotency_key_expiry
    sa.Index('ix_idempotency_key_expiry', metadata.tables['efhc_admin.idempotency_key'].c.expires_at)
    # Снимок внешнего индекса: admin_models.py:ix_idempotency_key_scope_used
    sa.Index('ix_idempotency_key_scope_used', metadata.tables['efhc_admin.idempotency_key'].c.scope, metadata.tables['efhc_admin.idempotency_key'].c.used)
    # Снимок внешнего индекса: ads_models.py:ix_ad_sessions_global_task_started
    sa.Index('ix_ad_sessions_global_task_started', metadata.tables['efhc_core.ad_sessions'].c.global_id, metadata.tables['efhc_core.ad_sessions'].c.task_code, metadata.tables['efhc_core.ad_sessions'].c.started_at)
    # Снимок внешнего индекса: bank_balance_models.py:ix_bank_balance_updated
    sa.Index('ix_bank_balance_updated', metadata.tables['efhc_core.bank_balance'].c.updated_at, postgresql_using='btree')
    # Снимок внешнего индекса: external_events_models.py:ix_processed_external_events_provider_event
    sa.Index('ix_processed_external_events_provider_event', metadata.tables['efhc_core.processed_external_events'].c.provider, metadata.tables['efhc_core.processed_external_events'].c.event_id)
    # Снимок внешнего индекса: panels_models.py:ix_panels_created_id
    sa.Index('ix_panels_created_id', metadata.tables['efhc_core.panels'].c.created_at, metadata.tables['efhc_core.panels'].c.id, postgresql_using='btree')
    # Снимок внешнего индекса: panels_models.py:ix_panels_global_id
    sa.Index('ix_panels_global_id', metadata.tables['efhc_core.panels'].c.global_id, postgresql_using='btree')
    # Снимок внешнего индекса: panels_models.py:ix_panels_global_active
    sa.Index('ix_panels_global_active', metadata.tables['efhc_core.panels'].c.global_id, metadata.tables['efhc_core.panels'].c.is_active, postgresql_using='btree')
    # Снимок внешнего индекса: panels_models.py:ix_panels_global_expire
    sa.Index('ix_panels_global_expire', metadata.tables['efhc_core.panels'].c.global_id, metadata.tables['efhc_core.panels'].c.expires_at, postgresql_using='btree')
    # Снимок внешнего индекса: panels_models.py:ix_panels_global_activated
    sa.Index('ix_panels_global_activated', metadata.tables['efhc_core.panels'].c.global_id, metadata.tables['efhc_core.panels'].c.activated_at, postgresql_using='btree')
    # Снимок внешнего индекса: referral_models.py:ix_ref_links_created_id
    sa.Index('ix_ref_links_created_id', metadata.tables['efhc_core.referral_links'].c.created_at, metadata.tables['efhc_core.referral_links'].c.id, postgresql_using='btree')
    # Снимок внешнего индекса: referral_models.py:ix_referral_links_inviter_created_invitee_global
    sa.Index('ix_referral_links_inviter_created_invitee_global', metadata.tables['efhc_core.referral_links'].c.inviter_global_id, metadata.tables['efhc_core.referral_links'].c.created_at.desc(), metadata.tables['efhc_core.referral_links'].c.invitee_global_id.desc(), postgresql_using='btree')
    # Снимок внешнего индекса: referral_models.py:ix_ref_links_activated_at
    sa.Index('ix_ref_links_activated_at', metadata.tables['efhc_core.referral_links'].c.activated_at, postgresql_using='btree')
    # Снимок внешнего индекса: shop_models.py:ix_shop_items_created_id
    sa.Index('ix_shop_items_created_id', metadata.tables['efhc_core.shop_items'].c.created_at, metadata.tables['efhc_core.shop_items'].c.id, postgresql_using='btree')
    # Снимок внешнего индекса: shop_models.py:ix_shop_orders_created_id
    sa.Index('ix_shop_orders_created_id', metadata.tables['efhc_core.shop_orders'].c.created_at, metadata.tables['efhc_core.shop_orders'].c.id, postgresql_using='btree')
    # Снимок внешнего индекса: shop_models.py:ix_shop_orders_global_created
    sa.Index('ix_shop_orders_global_created', metadata.tables['efhc_core.shop_orders'].c.global_id, metadata.tables['efhc_core.shop_orders'].c.created_at, postgresql_using='btree')
    # Снимок внешнего индекса: shop_models.py:ix_shop_orders_status
    sa.Index('ix_shop_orders_status', metadata.tables['efhc_core.shop_orders'].c.status, postgresql_using='btree')
    # Снимок внешнего индекса: shop_models.py:ix_shop_orders_idem
    sa.Index('ix_shop_orders_idem', metadata.tables['efhc_core.shop_orders'].c.idempotency_key, postgresql_using='btree')
    # Снимок внешнего индекса: tasks_models.py:ix_tasks_active_type
    sa.Index('ix_tasks_active_type', metadata.tables['efhc_core.tasks'].c.active, metadata.tables['efhc_core.tasks'].c.type)
    # Снимок внешнего индекса: tasks_models.py:ix_task_submissions_global_status
    sa.Index('ix_task_submissions_global_status', metadata.tables['efhc_core.task_submissions'].c.global_id, metadata.tables['efhc_core.task_submissions'].c.status)
    # Снимок внешнего индекса: tasks_models.py:ix_user_tasks_status_global_status
    sa.Index('ix_user_tasks_status_global_status', metadata.tables['efhc_core.user_tasks_status'].c.global_id, metadata.tables['efhc_core.user_tasks_status'].c.status)
    # Снимок внешнего индекса: tasks_models.py:ix_task_bonus_log_global_id_id
    sa.Index('ix_task_bonus_log_global_id_id', metadata.tables['efhc_core.task_bonus_log'].c.global_id, metadata.tables['efhc_core.task_bonus_log'].c.id)
    # Снимок внешнего индекса: tasks_models.py:ix_task_complete_lock_global_task_code
    sa.Index('ix_task_complete_lock_global_task_code', metadata.tables['efhc_core.task_complete_lock'].c.global_id, metadata.tables['efhc_core.task_complete_lock'].c.task_code)
    # Снимок внешнего индекса: ton_logs_models.py:ix_ton_inbox_created_id
    sa.Index('ix_ton_inbox_created_id', metadata.tables['efhc_core.ton_inbox_logs'].c.created_at, metadata.tables['efhc_core.ton_inbox_logs'].c.id, postgresql_using='btree')
    # Снимок внешнего индекса: ton_logs_models.py:ix_ton_inbox_status_nextretry
    sa.Index('ix_ton_inbox_status_nextretry', metadata.tables['efhc_core.ton_inbox_logs'].c.status, metadata.tables['efhc_core.ton_inbox_logs'].c.next_retry_at, postgresql_using='btree')
    # Снимок внешнего индекса: ton_logs_models.py:ix_ton_inbox_parsed_kind
    sa.Index('ix_ton_inbox_parsed_kind', metadata.tables['efhc_core.ton_inbox_logs'].c.parsed_kind, postgresql_using='btree')
    # Снимок внешнего индекса: transactions_models.py:ix_eftl_created_id
    sa.Index('ix_eftl_created_id', metadata.tables['efhc_core.efhc_transfers_log'].c.created_at, metadata.tables['efhc_core.efhc_transfers_log'].c.id, postgresql_using='btree')
    # Снимок внешнего индекса: transactions_models.py:ix_eftl_owner_created
    sa.Index('ix_eftl_owner_created', metadata.tables['efhc_core.efhc_transfers_log'].c.global_id, metadata.tables['efhc_core.efhc_transfers_log'].c.created_at, postgresql_using='btree')
    # Снимок внешнего индекса: transactions_models.py:ix_eftl_reason_created
    sa.Index('ix_eftl_reason_created', metadata.tables['efhc_core.efhc_transfers_log'].c.reason, metadata.tables['efhc_core.efhc_transfers_log'].c.created_at, postgresql_using='btree')
    # Снимок внешнего индекса: transactions_models.py:ix_eftl_system_entity_created
    sa.Index('ix_eftl_system_entity_created', metadata.tables['efhc_core.efhc_transfers_log'].c.system_entity, metadata.tables['efhc_core.efhc_transfers_log'].c.created_at, postgresql_using='btree')
    # Снимок внешнего индекса: user_models.py:ix_users_created_global_id
    sa.Index('ix_users_created_global_id', metadata.tables['efhc_core.users'].c.created_at, metadata.tables['efhc_core.users'].c.global_id, postgresql_using='btree')
    # Снимок внешнего индекса: user_models.py:ix_users_total_kwh_global_id
    sa.Index('ix_users_total_kwh_global_id', metadata.tables['efhc_core.users'].c.total_generated_kwh, metadata.tables['efhc_core.users'].c.global_id, postgresql_using='btree')
    # Снимок внешнего индекса: user_models.py:ix_users_available_kwh_global_id
    sa.Index('ix_users_available_kwh_global_id', metadata.tables['efhc_core.users'].c.available_kwh, metadata.tables['efhc_core.users'].c.global_id, postgresql_using='btree')
    # Снимок внешнего индекса: user_models.py:ix_users_rank_position_global_id
    sa.Index('ix_users_rank_position_global_id', metadata.tables['efhc_core.users'].c.rank_position, metadata.tables['efhc_core.users'].c.global_id, postgresql_using='btree')
    return metadata

RELEASE_METADATA = _build_release_metadata()

_REQUIRED_FQ = frozenset(
    {
        "efhc_core.users",
        "efhc_core.user_identities",
        "efhc_core.auth_challenges",
        "efhc_core.auth_sessions",
        "efhc_core.user_roles",
        "efhc_core.wallet_bindings",
        "efhc_core.wallet_connect_idempotency",
        "efhc_core.wallet_proof_token_uses",
        "efhc_core.withdraw_requests",
        "efhc_core.payment_intents",
        "efhc_core.withdraw_outcome_events",
        "efhc_core.outcome_fallback_promos",
        "efhc_core.panels",
        "efhc_core.tasks",
        "efhc_core.task_submissions",
        "efhc_core.user_tasks_status",
        "efhc_core.task_bonus_log",
        "efhc_core.task_complete_lock",
        "efhc_admin.efhc_sale_packages",
    }
)

_REQUIRED_METADATA_NAMES = frozenset(
    {
        "uq_payment_intents_global_idempo",
        "ck_users_superadmin_global_id_reserved",
        "ck_panels_public_id_pnl8",
        "uq_panels_public_id",
    }
)


def _schema_exists(conn: sa.Connection, name: str) -> bool:
    result = conn.execute(
        sa.text("SELECT 1 FROM pg_namespace WHERE nspname=:name"),
        {"name": name},
    )
    return result.scalar() is not None


def _to_regclass(conn: sa.Connection, fq_name: str) -> bool:
    result = conn.execute(
        sa.text("SELECT to_regclass(:name)"),
        {"name": fq_name},
    )
    return result.scalar() is not None


def _column_exists(
    conn: sa.Connection,
    schema: str,
    table: str,
    column: str,
) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema=:schema AND table_name=:table "
            "AND column_name=:column"
        ),
        {"schema": schema, "table": table, "column": column},
    )
    return result.scalar() is not None


def _column_is_nullable(
    conn: sa.Connection,
    schema: str,
    table: str,
    column: str,
) -> bool:
    value = conn.execute(
        sa.text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema=:schema AND table_name=:table "
            "AND column_name=:column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar()
    return value == "YES"


def _column_char_max_length(
    conn: sa.Connection,
    schema: str,
    table: str,
    column: str,
) -> int | None:
    value = conn.execute(
        sa.text(
            "SELECT character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema=:schema AND table_name=:table "
            "AND column_name=:column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar()
    return int(value) if value is not None else None


def _column_data_type(
    conn: sa.Connection,
    schema: str,
    table: str,
    column: str,
) -> str | None:
    value = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema=:schema AND table_name=:table "
            "AND column_name=:column"
        ),
        {"schema": schema, "table": table, "column": column},
    ).scalar()
    return str(value) if value is not None else None


def _metadata_named_objects() -> set[str]:
    names: set[str] = set()
    for table in RELEASE_METADATA.tables.values():
        for constraint in table.constraints:
            if constraint.name:
                names.add(str(constraint.name))
        for index in table.indexes:
            if index.name:
                names.add(str(index.name))
    return names


def _expected_global_owner_fk_count() -> int:
    total = 0
    for table in RELEASE_METADATA.tables.values():
        for constraint in table.foreign_key_constraints:
            if any(
                element.target_fullname == "efhc_core.users.global_id"
                for element in constraint.elements
            ):
                total += 1
    return total


def _validate_release_identity_schema(conn: sa.Connection) -> None:
    columns = {
        str(row[0])
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='efhc_core' AND table_name='users'"
            )
        ).fetchall()
    }
    if "global_id" not in columns:
        raise RuntimeError("0001: users.global_id physical column missing")
    forbidden = {"id", "user_id", "tg_id", "ton_wallet"} & columns
    if forbidden:
        raise RuntimeError(
            "0001: retired users columns present: "
            + ",".join(sorted(forbidden))
        )

    primary_columns = {
        str(row[0])
        for row in conn.execute(
            sa.text(
                "SELECT kcu.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON tc.constraint_name=kcu.constraint_name "
                "AND tc.table_schema=kcu.table_schema "
                "WHERE tc.table_schema='efhc_core' "
                "AND tc.table_name='users' "
                "AND tc.constraint_type='PRIMARY KEY'"
            )
        ).fetchall()
    }
    if primary_columns != {"global_id"}:
        raise RuntimeError(
            f"0001: users PK must be global_id, got {sorted(primary_columns)}"
        )

    sequence = conn.execute(
        sa.text(
            "SELECT pg_get_serial_sequence("
            "'efhc_core.users', 'global_id')"
        )
    ).scalar()
    if sequence != "efhc_core.users_global_id_seq":
        raise RuntimeError(
            "0001: users.global_id sequence ownership mismatch"
        )

    fk_total = int(
        conn.execute(
            sa.text(
                "SELECT count(*) FROM pg_constraint c "
                "JOIN pg_attribute a ON a.attrelid=c.confrelid "
                "AND a.attnum=ANY(c.confkey) "
                "WHERE c.contype='f' "
                "AND c.confrelid='efhc_core.users'::regclass "
                "AND a.attname='global_id'"
            )
        ).scalar()
        or 0
    )
    expected_fk_total = _expected_global_owner_fk_count()
    if fk_total != expected_fk_total:
        raise RuntimeError(
            "0001: global owner FK mismatch: "
            f"expected {expected_fk_total}, got {fk_total}"
        )


def _validate_clean_schema(conn: sa.Connection) -> None:
    missing: list[str] = []
    if not _schema_exists(conn, CORE):
        missing.append(f"schema:{CORE}")
    if not _schema_exists(conn, ADMIN):
        missing.append(f"schema:{ADMIN}")

    tables = sorted(RELEASE_METADATA.tables.keys())
    if len(tables) != EXPECTED_TABLE_COUNT:
        missing.append(
            f"tables_count_expected_{EXPECTED_TABLE_COUNT}_got_{len(tables)}"
        )
    actual_contract = {
        (str(table.schema or ""), str(table.name))
        for table in RELEASE_METADATA.sorted_tables
        if table.schema in {CORE, ADMIN}
    }
    if actual_contract != EXPECTED_TABLES:
        missing.append("ORM_metadata_contract_mismatch")
    for table_name in tables:
        fq_name = (
            table_name if "." in table_name else f"{CORE}.{table_name}"
        )
        if not _to_regclass(conn, fq_name):
            missing.append(fq_name)

    required_columns = {
        (CORE, "users", "global_id"),
        (CORE, "users", "rank_position"),
        (CORE, "users", "rank_score_kwh"),
        (CORE, "users", "rank_calculated_at"),
        (CORE, "users", "main_balance"),
        (CORE, "users", "bonus_balance"),
        (CORE, "users", "available_kwh"),
        (CORE, "users", "total_generated_kwh"),
        (CORE, "users", "is_vip"),
        (CORE, "wallet_bindings", "global_id"),
        (CORE, "wallet_bindings", "wallet_address"),
        (CORE, "wallet_bindings", "proof_verified"),
        (CORE, "panels", "global_id"),
        (CORE, "panels", "is_active"),
        (CORE, "panels", "archived_at"),
        (CORE, "payment_intents", "global_id"),
        (CORE, "ton_inbox_logs", "trusted_operation_at"),
        (CORE, "tx_hash_locks", "trusted_operation_at"),
        (CORE, "tx_hash_locks", "server_first_seen_at"),
        (CORE, "withdraw_requests", "global_id"),
        (CORE, "efhc_transfers_log", "global_id"),
        (CORE, "tasks", "bonus_efhc"),
        (CORE, "task_submissions", "global_id"),
    }
    for schema, table, column in sorted(required_columns):
        if not _column_exists(conn, schema, table, column):
            missing.append(f"{schema}.{table}.{column}")

    if not _column_is_nullable(conn, CORE, "payment_intents", "package_id"):
        missing.append("efhc_core.payment_intents.package_id_nullable")
    if _column_is_nullable(conn, CORE, "panels", "public_id"):
        missing.append("efhc_core.panels.public_id_nullable")
    if _column_char_max_length(conn, CORE, "panels", "public_id") != 12:
        missing.append("efhc_core.panels.public_id_length_not_12")
    counter = conn.execute(
        sa.text(
            "SELECT value FROM efhc_core.app_settings "
            "WHERE key = 'panels.pnl.last_issued'"
        )
    ).scalar()
    if counter != '0':
        missing.append("efhc_core.app_settings.initial_pnl_counter_invalid")
    trigger_count = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM pg_trigger "
            "WHERE tgrelid = 'efhc_core.panels'::regclass "
            "AND tgname = 'trg_panels_immutable_identity' "
            "AND NOT tgisinternal"
        )
    ).scalar()
    if trigger_count != 1:
        missing.append("efhc_core.panels.identity_trigger_missing")
    direction_len = _column_char_max_length(
        conn, CORE, "efhc_transfers_log", "direction"
    )
    if direction_len is None or direction_len < 24:
        missing.append("efhc_core.efhc_transfers_log.direction_varchar24")

    required_bigint_columns = {
        (ADMIN, "efhc_sale_packages", "id"),
        (CORE, "app_settings", "id"),
        (CORE, "efhc_transfers_log", "id"),
        (CORE, "payment_intents", "package_id"),
        (CORE, "referral_links", "id"),
        (CORE, "scheduler_task_log", "id"),
        (CORE, "shop_items", "id"),
        (CORE, "shop_orders", "id"),
        (CORE, "user_cosmetics", "id"),
        (CORE, "user_skins", "id"),
        (CORE, "users", "global_id"),
        (CORE, "wallet_bindings", "id"),
        (CORE, "wallet_proof_token_uses", "id"),
    }
    for schema, table, column in sorted(required_bigint_columns):
        if _column_data_type(conn, schema, table, column) != "bigint":
            missing.append(f"{schema}.{table}.{column}:expected_bigint")

    retired_tables = {
        f"{CORE}.panels_archive",
        f"{CORE}.ranks_snapshots",
        f"{CORE}.ranks_top_cache",
        f"{CORE}.ranks_user_snapshots",
    }
    for fq_name in retired_tables:
        if _to_regclass(conn, fq_name):
            missing.append(f"retired_table_present:{fq_name}")

    if missing:
        raise RuntimeError(
            "0001 sanity failed; objects: " + ", ".join(missing)
        )
    _validate_release_identity_schema(conn)


def upgrade() -> None:
    conn = op.get_bind()
    offline = bool(alembic_context.is_offline_mode())

    if not offline:
        try:
            database = conn.execute(
                sa.text("SELECT current_database()")
            ).scalar()
            search_path = conn.execute(sa.text("SHOW search_path")).scalar()
            sys.stdout.write(f"0001: db={database}\n")
            sys.stdout.write(f"0001: search_path={search_path}\n")
        except Exception:
            sys.stdout.write("0001: db_diag_unavailable\n")

    # Clean Greenfield DB не обязана заранее содержать application schemas.
    conn.execute(sa.text("CREATE SCHEMA IF NOT EXISTS efhc_core"))
    conn.execute(sa.text("CREATE SCHEMA IF NOT EXISTS efhc_admin"))
    conn.execute(sa.text("SET search_path TO efhc_core, efhc_admin"))
    conn2 = conn.execution_options(
        schema_translate_map={None: CORE}
    )
    sys.stdout.write(
        f"0001: metadata_tables={len(RELEASE_METADATA.tables)}\n"
    )

    metadata_tables = set(RELEASE_METADATA.tables.keys())
    missing_metadata = sorted(_REQUIRED_FQ - metadata_tables)
    if missing_metadata:
        raise RuntimeError(
            "0001 sanity failed; missing in frozen release metadata: "
            + ", ".join(missing_metadata)
        )
    missing_named = sorted(
        _REQUIRED_METADATA_NAMES - _metadata_named_objects()
    )
    if missing_named:
        raise RuntimeError(
            "0001 sanity failed; missing metadata constraints/indexes: "
            + ", ".join(missing_named)
        )

    RELEASE_METADATA.create_all(bind=conn2, checkfirst=True)
    if not offline:
        # Durable rollback-safe PNL counter; no PostgreSQL sequence for public IDs.
        conn.execute(sa.text(
            "INSERT INTO efhc_core.app_settings (key, value) "
            "VALUES ('panels.pnl.last_issued', '0') "
            "ON CONFLICT (key) DO NOTHING"
        ))
        conn.execute(sa.text("""
            CREATE OR REPLACE FUNCTION efhc_core.guard_panel_identity()
            RETURNS trigger LANGUAGE plpgsql AS $pnl_guard$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'Historical panel records cannot be deleted'
                        USING ERRCODE = '23514';
                END IF;
                IF NEW.public_id IS DISTINCT FROM OLD.public_id
                    OR NEW.global_id IS DISTINCT FROM OLD.global_id THEN
                    RAISE EXCEPTION 'Panel PNL and Global ID are immutable'
                        USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END;
            $pnl_guard$;
        """))
        conn.execute(sa.text("""
            CREATE TRIGGER trg_panels_immutable_identity
            BEFORE UPDATE OR DELETE ON efhc_core.panels
            FOR EACH ROW EXECUTE FUNCTION efhc_core.guard_panel_identity()
        """))
        conn.execute(
            sa.text(
                "ALTER SEQUENCE efhc_core.users_global_id_seq "
                "OWNED BY efhc_core.users.global_id"
            )
        )
        conn.execute(
            sa.text(
                "ALTER TABLE efhc_core.users ALTER COLUMN global_id "
                "SET DEFAULT nextval("
                "'efhc_core.users_global_id_seq'::regclass)"
            )
        )
        count = conn.execute(
            sa.text(
                "SELECT count(*) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.relkind='r' "
                "AND n.nspname IN ('efhc_core','efhc_admin')"
            )
        ).scalar()
        sys.stdout.write(f"0001: tables_in_schemas={count}\n")
        _validate_clean_schema(conn)

    sys.stdout.write("0001: create_all_done\n")

    st = sa.Table(
        'system_templates',
        sa.MetaData(),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('description', sa.String(), nullable=False),
        schema='efhc_core',
    )
    template_rows = [
        {
            'key': 'task_reject_fallback',
            'content': 'Выполнение не подтверждено.',
            'description': 'Автоответ при отклонении задания',
        },
        {
            'key': 'task_approve_fallback',
            'content': None,
            'description': 'Автоответ при одобрении задания',
        },
    ]
    localized_templates = {
        'task_approve_prefix': {
            'description': 'Префикс уведомления: задание подтверждено',
            'values': {
                'en': '✅ Task approved.',
                'ru': '✅ Задание подтверждено.',
                'uk': '✅ Завдання підтверджено.',
                'de': '✅ Aufgabe bestätigt.',
                'fr': '✅ Tâche confirmée.',
                'es': '✅ Tarea confirmada.',
                'it': '✅ Attività confermata.',
                'tr': '✅ Görev onaylandı.',
                'pl': '✅ Zadanie potwierdzone.',
                'da': '✅ Opgaven er bekræftet.',
                'hi': '✅ कार्य की पुष्टि हो गई।',
                'id': '✅ Tugas dikonfirmasi.',
                'sw': '✅ Kazi imethibitishwa.',
            },
        },
        'task_reject_prefix': {
            'description': 'Префикс уведомления: задание отклонено',
            'values': {
                'en': '⚠️ Task rejected.',
                'ru': '⚠️ Задание отклонено.',
                'uk': '⚠️ Завдання відхилено.',
                'de': '⚠️ Aufgabe abgelehnt.',
                'fr': '⚠️ Tâche refusée.',
                'es': '⚠️ Tarea rechazada.',
                'it': '⚠️ Attività rifiutata.',
                'tr': '⚠️ Görev reddedildi.',
                'pl': '⚠️ Zadanie odrzucone.',
                'da': '⚠️ Opgaven blev afvist.',
                'hi': '⚠️ कार्य अस्वीकृत किया गया।',
                'id': '⚠️ Tugas ditolak.',
                'sw': '⚠️ Kazi imekataliwa.',
            },
        },
        'task_approve_fallback': {
            'description': 'Fallback-комментарий: задание подтверждено',
            'values': {
                'en': 'Task result confirmed.',
                'ru': 'Результат задания подтвержден.',
                'uk': 'Результат завдання підтверджено.',
                'de': 'Das Ergebnis der Aufgabe wurde bestätigt.',
                'fr': 'Le résultat de la tâche a été confirmé.',
                'es': 'El resultado de la tarea fue confirmado.',
                'it': "Il risultato dell'attività è stato confermato.",
                'tr': 'Görev sonucu doğrulandı.',
                'pl': 'Wynik zadania został potwierdzony.',
                'da': 'Opgavens resultat er bekræftet.',
                'hi': 'कार्य का परिणाम पुष्टि कर दिया गया है।',
                'id': 'Hasil tugas telah dikonfirmasi.',
                'sw': 'Matokeo ya kazi yamehakikishwa.',
            },
        },
        'task_reject_fallback': {
            'description': 'Fallback-комментарий: задание отклонено',
            'values': {
                'en': 'Task result was not confirmed.',
                'ru': 'Выполнение не подтверждено.',
                'uk': 'Виконання не підтверджено.',
                'de': 'Die Ausführung wurde nicht bestätigt.',
                'fr': "L'exécution n'a pas été confirmée.",
                'es': 'La ejecución no fue confirmada.',
                'it': "L'esecuzione non è stata confermata.",
                'tr': 'Tamamlama doğrulanmadı.',
                'pl': 'Wykonanie nie zostało potwierdzone.',
                'da': 'Udførelsen blev ikke bekræftet.',
                'hi': 'कार्य पूरा होने की पुष्टि नहीं हुई।',
                'id': 'Penyelesaian tidak dikonfirmasi.',
                'sw': 'Utekelezaji haujathibitishwa.',
            },
        },
    }
    for base_key, spec in localized_templates.items():
        for lang, content in spec['values'].items():
            template_rows.append(
                {
                    'key': f'{base_key}.{lang}',
                    'content': content,
                    'description': (
                        f"{spec['description']} [{lang}]"
                    ),
                }
            )
    for row in template_rows:
        stmt = pg_insert(st).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=['key'],
            set_={
                'description': row['description'],
                'content': row['content'],
            },
        )
        conn.execute(stmt)

    # Системные строки создаёт только app.release.initial_data.
    sys.stdout.write("0001: ok\n")


def downgrade() -> None:
    # Канон: downgrade не удаляет production objects.
    pass
