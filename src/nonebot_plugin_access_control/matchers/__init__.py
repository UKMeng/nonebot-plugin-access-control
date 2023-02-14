from argparse import Namespace
from datetime import timedelta
from io import StringIO
from typing import Optional, cast

from nonebot import on_shell_command
from nonebot.exception import ParserExit
from nonebot.internal.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State

from .handle_error import handle_error
from .parser import parser
from ..service import Service, get_service_by_qualified_name
from ..utils.tree import get_tree_summary


def parse_integer(text: str, full: bool = True) -> int:
    num = 0
    for c in text:
        c_ord = ord(c) - ord('0')
        if 0 <= c_ord <= 9:
            num = num * 10 + c_ord
        else:
            if full:
                raise ValueError(f'\'{text}\' cannot parse as an integer')
            break
    return num


cmd = on_shell_command("ac", parser=parser, permission=SUPERUSER)


@cmd.handle()
@handle_error()
async def _(matcher: Matcher, state: T_State):
    args = state["_args"]
    if isinstance(args, ParserExit):
        await matcher.finish(args.message)

    args = cast(Namespace, args)
    if args.subcommand is None or args.subcommand == 'help':
        await handle_help(matcher)
    elif args.subcommand == 'permission':
        if args.action == 'allow':
            await handle_permission_allow(matcher, args.subject, args.service)
        elif args.action == 'deny':
            await handle_permission_deny(matcher, args.subject, args.service)
        elif args.action == 'rm':
            await handle_permission_rm(matcher, args.subject, args.service)
        elif args.action == 'ls':
            await handle_permission_ls(matcher, args.subject, args.service)
    elif args.subcommand == 'limit':
        if args.action == 'add':
            await handle_limit_add(matcher, args.subject, args.service, args.limit, args.span)
        elif args.action == 'rm':
            await handle_limit_rm(matcher, args.id)
        elif args.action == 'ls':
            await handle_limit_ls(matcher, args.subject, args.service)
    elif args.subcommand == 'service':
        if args.action == 'ls':
            await handle_service_ls(matcher, args.service)


help_text = """
/ac help：显示此帮助

/ac permission allow --sbj <主体> --srv <服务>：为主体启用服务
/ac permission deny --sbj <主体> --srv <服务>：为主体禁用服务
/ac permission rm --sbj <主体> --srv <服务>：为主体删除服务权限配置
/ac permission ls：列出所有已配置的权限
/ac permission ls --sbj <主体>：列出主体已配置的服务权限
/ac permission ls --srv <服务>：列出服务已配置的主体权限
/ac permission ls --sbj <主体> --srv <服务>：列出主体与服务已配置的权限

/ac limit add --sbj <主体> --srv <服务> --limit <次数> --span <时间间隔>：为主体与服务添加限流规则（按照用户限流）
/ac limit rm <规则ID>：删除限流规则
/ac limit ls：列出所有已配置的限流规则
/ac limit ls --sbj <主体>：列出主体已配置的限流规则
/ac limit ls --srv <服务>：列出服务已配置的限流规则
/ac limit ls --sbj <主体> --srv <服务>：列出主体与服务已配置的限流规则

/ac service ls：列出所有服务与子服务层级
/ac service ls --srv <服务>：列出服务的子服务层级
""".strip()


async def handle_help(matcher: Matcher):
    await matcher.send(help_text)


async def _get_service(matcher: Matcher, service_name: str) -> Service:
    service = get_service_by_qualified_name(service_name)

    if service is None:
        await matcher.finish("service not found")
    else:
        return service


async def handle_permission_allow(matcher: Matcher, subject: str, service_name: str):
    service = await _get_service(matcher, service_name)
    await service.set_permission(subject, True)
    await matcher.send("ok")


async def handle_permission_deny(matcher: Matcher, subject: str, service_name: str):
    service = await _get_service(matcher, service_name)
    await service.set_permission(subject, False)
    await matcher.send("ok")


async def handle_permission_rm(matcher: Matcher, subject: str, service_name: str):
    service = await _get_service(matcher, service_name)
    await service.remove_permission(subject)
    await matcher.send("ok")


async def handle_permission_ls(matcher: Matcher, subject: Optional[str], service_name: Optional[str]):
    if service_name is None:
        service_name = 'nonebot'
    service = await _get_service(matcher, service_name)

    if subject is None:
        permissions = [x async for x in service.get_all_permissions()]
    else:
        permissions = [await service.get_permission(subject)]

    if len(permissions) != 0:
        # 按照服务全称、先allow再deny、subject排序
        permissions = sorted(permissions, key=lambda x: (x.service.qualified_name, x.allow, x.subject))
        with StringIO() as sio:
            for p in permissions:
                sio.write(p.service.qualified_name)

                if p.allow:
                    sio.write(" allow ")
                else:
                    sio.write(" deny ")

                sio.write(p.subject)
                if p.service.qualified_name != service_name:
                    sio.write(f" (inherited from {p.service.qualified_name})")
                sio.write('\n')
            msg = sio.getvalue().strip()
    else:
        msg = "empty"
    await matcher.send(msg)


async def handle_limit_add(matcher: Matcher,
                           subject: str,
                           service_name: str,
                           limit: str,
                           time_span: str):
    if (time_span.endswith('s')
            or time_span.endswith('sec')
            or time_span.endswith('second')
            or time_span.endswith('seconds')):
        time_span = timedelta(seconds=parse_integer(time_span, full=False))
    elif (time_span.endswith('m')
          or time_span.endswith('min')
          or time_span.endswith('minute')
          or time_span.endswith('minutes')):
        time_span = timedelta(minutes=parse_integer(time_span, full=False))
    elif (time_span.endswith('h')
          or time_span.endswith('hour')
          or time_span.endswith('hours')):
        time_span = timedelta(hours=parse_integer(time_span, full=False))
    elif (time_span.endswith('d')
          or time_span.endswith('day')
          or time_span.endswith('days')):
        time_span = timedelta(days=parse_integer(time_span, full=False))
    else:
        await matcher.send("请指定时间单位（sec/min/hour/day）")

    limit = parse_integer(limit)
    if limit == 0:
        await matcher.send('限流次数必须大于0')
    else:
        service = await _get_service(matcher, service_name)
        await service.add_rate_limit_rule(subject, time_span, limit)
        await matcher.send('ok')


async def handle_limit_rm(matcher: Matcher, rule_id: str):
    rule_id = parse_integer(rule_id)
    await Service.remove_rate_limit_rule(rule_id)
    await matcher.send('ok')


async def handle_limit_ls(matcher: Matcher, subject: Optional[str], service_name: Optional[str]):
    if service_name is None:
        service_name = 'nonebot'
    service = await _get_service(matcher, service_name)

    if subject is None:
        rules = [x async for x in service.get_rate_limit_rules()]
    else:
        rules = [x async for x in service.get_rate_limit_rules(subject)]

    if len(rules) != 0:
        with StringIO() as sio:
            for rule in rules:
                sio.write(f"#{rule.id} {rule.service.qualified_name} "
                          f"limit {rule.subject} to {rule.limit} time(s)"
                          f"every {rule.time_span.total_seconds()}s\n")
            await matcher.send(sio.getvalue().strip())
    else:
        await matcher.send("empty")


async def handle_service_ls(matcher: Matcher, service_name: Optional[str]):
    if service_name is None:
        service_name = 'nonebot'
    service = await _get_service(matcher, service_name)
    summary = get_tree_summary(service, lambda x: x.children, lambda x: x.name)
    await matcher.send(summary)
