"""Command-line entry point: query one dormitory's room / air-conditioning balance."""

import argparse
import json
import sys
from typing import List, Optional

from . import __version__
from .auth import load_credentials
from .client import AhutElectricityClient


def _format_result(res: dict) -> str:
    label = f"{res.get('type', '')}电量"
    if res.get("success"):
        data = res["data"]
        return (
            f"{label}: 剩余 {data['remain_amp']:.2f} 度"
            f"（累计购电 {data['all_amp']:.2f}，累计用电 {data['used_amp']:.2f}）"
        )
    return f"{label}: 查询失败 [Code {res.get('code')}] {res.get('msg')}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ahut-electricity",
        description=(
            "查询安徽工业大学宿舍房间 / 空调剩余电量（非官方接口）。"
            "账号密码从环境变量 AHUT_USERNAME / AHUT_PASSWORD 或 config.json 读取。"
        ),
    )
    parser.add_argument("building", help="楼栋编号或名称，如 26、K1、东校区K1号学生宿舍楼")
    parser.add_argument("room", help="3 位房间号，如 101")
    parser.add_argument("--campus", help="校区：NewS/东校区 或 OldS/本部；楼栋名唯一时可省略")
    parser.add_argument(
        "--type",
        choices=("both", "room", "air"),
        default="both",
        help="查询类型：both（默认）、room（房间）、air（空调）",
    )
    parser.add_argument("--cookie", help="直接使用浏览器 Cookie（EF.WAP.Auth=...; EF.SessionId=...），不登录")
    parser.add_argument("--config", help="config.json 路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出原始结果")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    username = password = None
    if not args.cookie:
        username, password = load_credentials(args.config)
        if not (username and password):
            print(
                "未找到账号密码：请设置环境变量 AHUT_USERNAME / AHUT_PASSWORD、"
                "提供 config.json，或使用 --cookie。",
                file=sys.stderr,
            )
            return 2

    client = AhutElectricityClient(
        cookies=args.cookie,
        username=username,
        password=password,
        auto_login=False,
    )
    if not args.cookie:
        login_res = client.login()
        if not login_res.get("success"):
            print(f"登录失败 [Code {login_res.get('code')}] {login_res.get('msg')}", file=sys.stderr)
            return 1
        client.auto_login = True

    campus = args.campus or ""
    try:
        if args.type == "both":
            res = client.query_both(campus, args.building, args.room)
            results = [res["room"], res["air"]]
        else:
            results = [client.query_balance(campus, args.building, args.room, elec_type=args.type)]
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], ensure_ascii=False, indent=2))
    else:
        first = results[0]
        print(f"{first.get('building_name')} {first.get('room_no')}")
        for res in results:
            print(_format_result(res))

    return 0 if all(r.get("success") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
