from abc import ABC
from datetime import timedelta
from typing import Optional, Generic, TypeVar, Type, AsyncGenerator

from nonebot import Bot
from nonebot.internal.adapter import Event
from nonebot.internal.matcher import Matcher

from .impl.permission import ServicePermissionImpl
from .impl.rate_limit import ServiceRateLimitImpl
from .interface import IService
from .permission import Permission
from .rate_limit import RateLimitRule
from ..errors import AccessControlError, PermissionDeniedError, RateLimitedError
from ..event_bus import T_Listener
from ..subject import extract_subjects

T_ParentService = TypeVar('T_ParentService', bound=Optional["Service"], covariant=True)
T_ChildService = TypeVar('T_ChildService', bound="Service", covariant=True)


class Service(Generic[T_ParentService, T_ChildService],
              IService["Service", T_ParentService, T_ChildService],
              ABC):
    def __init__(self):
        self._permission_impl = ServicePermissionImpl[Service](self)
        self._rate_limit_impl = ServiceRateLimitImpl[Service](self)

    def __repr__(self):
        return self.qualified_name

    def travel(self):
        sta = [self]
        while len(sta) != 0:
            top, sta = sta[-1], sta[:-1]
            yield top
            sta.extend(top.children)

    def trace(self):
        node = self
        while node is not None:
            yield node
            node = node.parent

    def find(self, name: str) -> Optional["Service"]:
        for s in self.travel():
            if s.name == name:
                return s
        return None

    def patch_matcher(self, matcher: Type[Matcher]) -> Type[Matcher]:
        from ..access_control import patch_matcher
        return patch_matcher(matcher, self)

    async def check(self, bot: Bot, event: Event, acquire_rate_limit_token: bool = True) -> bool:
        try:
            await self.check_or_throw(bot, event, acquire_rate_limit_token)
            return True
        except AccessControlError:
            return False

    async def check_or_throw(self, bot: Bot, event: Event, acquire_rate_limit_token: bool = True):
        subjects = extract_subjects(bot, event)
        allow = await self.check_permission(*subjects)
        if not allow:
            raise PermissionDeniedError()

        if acquire_rate_limit_token:
            adapter_name = bot.adapter.get_name().split(maxsplit=1)[0].lower()
            user_id = f"{adapter_name}:{event.get_user_id()}"
            allow = await self.acquire_token_for_rate_limit(*subjects, user=user_id)

            if not allow:
                raise RateLimitedError()

    def on_set_permission(self, func: Optional[T_Listener] = None):
        return self._permission_impl.on_set_permission(func)

    def on_change_permission(self, func: Optional[T_Listener] = None):
        return self._permission_impl.on_change_permission(func)

    def on_remove_permission(self, func: Optional[T_Listener] = None):
        return self._permission_impl.on_remove_permission(func)

    async def get_permission(self, *subject: str, trace: bool = True) -> Optional[Permission]:
        return await self._permission_impl.get_permission(*subject, trace=trace)

    def get_all_permissions(self, *, trace: bool = True) -> AsyncGenerator[Permission, None]:
        return self._permission_impl.get_all_permissions(trace=trace)

    async def set_permission(self, subject: str, allow: bool):
        return await self._permission_impl.set_permission(subject, allow)

    async def remove_permission(self, subject: str) -> bool:
        return await self._permission_impl.remove_permission(subject)

    async def check_permission(self, *subject: str) -> bool:
        return await self._permission_impl.check_permission(*subject)

    def get_rate_limit_rules(self, *subject: str,
                             trace: bool = True) -> AsyncGenerator[RateLimitRule, None]:
        return self._rate_limit_impl.get_rate_limit_rules(*subject, trace=trace)

    def get_all_rate_limit_rules(self, *, trace: bool = True) -> AsyncGenerator[RateLimitRule, None]:
        return self._rate_limit_impl.get_all_rate_limit_rules(trace=trace)

    async def add_rate_limit_rule(self, subject: str, time_span: timedelta, limit: int):
        return await self._rate_limit_impl.add_rate_limit_rule(subject, time_span, limit)

    @classmethod
    async def remove_rate_limit_rule(cls, rule_id: int):
        return await ServiceRateLimitImpl.remove_rate_limit_rule(rule_id)

    async def acquire_token_for_rate_limit(self, *subject: str, user: str) -> bool:
        return await self._rate_limit_impl.acquire_token_for_rate_limit(*subject, user=user)
