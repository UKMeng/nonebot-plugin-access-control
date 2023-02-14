from abc import ABC, abstractmethod
from typing import Optional, Collection, Generic, Generator, Type, TypeVar

from nonebot import Bot
from nonebot.internal.adapter import Event
from nonebot.internal.matcher import Matcher

T_Service = TypeVar('T_Service', bound="IServiceBase", covariant=True)
T_ParentService = TypeVar('T_ParentService', bound=Optional["IServiceBase"], covariant=True)
T_ChildService = TypeVar('T_ChildService', bound="IServiceBase", covariant=True)


class IServiceBase(Generic[T_Service, T_ParentService, T_ChildService], ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError()

    @property
    def qualified_name(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def parent(self) -> Optional[T_ParentService]:
        raise NotImplementedError()

    @property
    def children(self) -> Collection[T_ChildService]:
        raise NotImplementedError()

    @abstractmethod
    def travel(self) -> Generator[T_Service, None, None]:
        raise NotImplementedError()

    @abstractmethod
    def trace(self) -> Generator[T_Service, None, None]:
        raise NotImplementedError()

    @abstractmethod
    def find(self, name: str) -> Optional[T_Service]:
        raise NotImplementedError()

    @abstractmethod
    def patch_matcher(self, matcher: Type[Matcher]) -> Type[Matcher]:
        raise NotImplementedError()

    @abstractmethod
    async def check(self, bot: Bot, event: Event, acquire_rate_limit_token: bool = True) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def check_or_throw(self, bot: Bot, event: Event, acquire_rate_limit_token: bool = True):
        raise NotImplementedError()
