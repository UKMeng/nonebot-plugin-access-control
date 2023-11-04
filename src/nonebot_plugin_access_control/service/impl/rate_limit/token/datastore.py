from nonebot import require

require("nonebot_plugin_apscheduler")

from typing import Optional
from datetime import datetime

from loguru import logger
from sqlalchemy import func, delete, select
from nonebot_plugin_apscheduler import scheduler
from apscheduler.triggers.interval import IntervalTrigger

from .interface import TokenStorage
from .....utils.session import use_ac_session
from .....models import RateLimitRuleOrm, RateLimitTokenOrm
from ....rate_limit import RateLimitRule, RateLimitSingleToken


class DataStoreTokenStorage(TokenStorage):
    async def get_first_expire_token(
        self, rule: RateLimitRule, user: str
    ) -> Optional[RateLimitSingleToken]:
        now = datetime.utcnow()

        async with use_ac_session() as sess:
            stmt = (
                select(func.min(RateLimitTokenOrm.expire_time))
                .select_from(RateLimitTokenOrm)
                .where(RateLimitTokenOrm.expire_time > now)
                .scalar_subquery()
            )
            stmt = (
                select(RateLimitTokenOrm)
                .where(RateLimitTokenOrm.expire_time == stmt)
                .limit(1)
            )
            res = (await sess.execute(stmt)).scalar_one_or_none()

            if res is None:
                return None
            else:
                return RateLimitSingleToken(
                    res.id,
                    res.rule_id,
                    res.user,
                    res.acquire_time,
                    res.acquire_time + rule.time_span,
                )

    async def acquire_token(
        self, rule: RateLimitRule, user: str
    ) -> Optional[RateLimitSingleToken]:
        now = datetime.utcnow()

        async with use_ac_session() as sess:
            stmt = select(func.count()).where(
                RateLimitTokenOrm.rule_id == rule.id,
                RateLimitTokenOrm.user == user,
                RateLimitTokenOrm.expire_time > now,
            )
            cnt = (await sess.execute(stmt)).scalar_one()

            if cnt >= rule.limit:
                return None

            acquire_time = datetime.utcnow()
            expire_time = acquire_time + rule.time_span

            x = RateLimitTokenOrm(
                rule_id=rule.id,
                user=user,
                acquire_time=acquire_time,
                expire_time=expire_time,
            )
            sess.add(x)
            await sess.commit()

            await sess.refresh(x)

            return RateLimitSingleToken(
                x.id, x.rule_id, x.user, acquire_time, expire_time
            )

    async def retire_token(self, token: RateLimitSingleToken):
        async with use_ac_session() as sess:
            stmt = delete(RateLimitTokenOrm).where(RateLimitTokenOrm.id == token.id)
            await sess.execute(stmt)
            await sess.commit()

    async def delete_outdated_tokens(self):
        async with use_ac_session() as session:
            now = datetime.utcnow()
            stmts = []
            async for rule in await session.stream_scalars(select(RateLimitRuleOrm)):
                stmt = (
                    delete(RateLimitTokenOrm)
                    .where(
                        RateLimitTokenOrm.rule_id == rule.id,
                        RateLimitTokenOrm.expire_time <= now,
                    )
                    .execution_options(synchronize_session=False)
                )
                stmts.append(stmt)

            rowcount = 0
            for stmt in stmts:
                result = await session.execute(stmt)
                rowcount += result.rowcount

            await session.commit()

            logger.debug(f"deleted {rowcount} outdated rate limit token(s)")


datastore_storage = DataStoreTokenStorage()

scheduler.scheduled_job(
    IntervalTrigger(minutes=10), id="delete_outdated_tokens_datastore"
)(datastore_storage.delete_outdated_tokens)


def get_datastore_token_storage() -> TokenStorage:
    return datastore_storage
