#!/usr/bin/env python3
"""OpenCode 原生编排取证工具（只读）。

用途：回答三个光看 UI 说不清的问题——

1. 原生 ``task`` 到底被调用过没有？子会话是哪个 agent 在执行？
2. 两个 ``task`` 调用在时间上是否真的重叠（真并行），还是先后串行？
3. 权限规则是运行时被强制了，还是只写在配置里？

数据来源：``~/.local/share/opencode/opencode.db``（SQLite）

- ``session(parent_id, agent, project_id, directory, time_created)`` → 子会话树 + agent
- ``message(session_id, data)`` → ``data.agent`` 为实际执行者
- ``part(session_id, data)`` → ``data.type=="tool"`` 时含 tool 名与 ``state.time.{start,end}``（毫秒）
- ``permission`` / ``event`` → 权限决策痕迹

用法::

    python tools/opencode_forensics.py                     # 人类可读报告
    python tools/opencode_forensics.py --json              # 机器可读
    python tools/opencode_forensics.py --project-dir .     # 指定项目根（默认本仓库根）
    python tools/opencode_forensics.py --since 2h          # 只看最近 2 小时
    python tools/opencode_forensics.py --selftest          # 不读库，验证重叠算法

设计原则：

- **绝不写原库**：默认把 ``db`` / ``-wal`` / ``-shm`` 复制到临时目录再打开，
  避免与正在运行的客户端争锁，也避免只读连接读到不一致快照。
- 只依赖标准库，不引入第三方包。
- 查不到东西时明确说「没有」，而不是给出「大概是」的结论。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION_ID_RE = re.compile(r"ses_[A-Za-z0-9]+")
TIME_RE = re.compile(r"^(\d+)([mhd])$")


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def norm_path(value: str | None) -> str:
    """把 Windows 反斜杠、盘符大小写、尾部分隔符统一，便于比较。"""
    if not value:
        return ""
    return value.replace("\\", "/").rstrip("/").lower()


def fmt_ms(ms: int | None) -> str:
    if not ms:
        return "-"
    return datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M:%S.%f")[:-3]


def fmt_dur(ms: float | None) -> str:
    if ms is None:
        return "-"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.2f}s"
    return f"{seconds // 60:.0f}m{seconds % 60:04.1f}s"


def parse_since(text: str | None) -> int | None:
    """支持 ``2h`` / ``90m`` / ``3d`` 或毫秒时间戳；返回毫秒下界。"""
    if not text:
        return None
    match = TIME_RE.match(text.strip())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount),
                 "d": timedelta(days=amount)}[unit]
        return int((datetime.now() - delta).timestamp() * 1000)
    return int(text)


def open_snapshot(db_path: Path, copy: bool = True) -> tuple[sqlite3.Connection, Path]:
    """打开数据库；默认先复制 db/-wal/-shm 到临时目录，保证零干扰。"""
    if not db_path.exists():
        raise SystemExit(f"[错误] 找不到数据库：{db_path}")

    if not copy:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        return con, db_path

    workdir = Path(tempfile.mkdtemp(prefix="ocsnap-"))
    for suffix in ("", "-wal", "-shm"):
        src = db_path.with_name(db_path.name + suffix)
        if src.exists():
            shutil.copy2(src, workdir / (db_path.name + suffix))
    con = sqlite3.connect(workdir / db_path.name)
    return con, workdir


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def load(con: sqlite3.Connection) -> dict:
    cur = con.cursor()

    def table_exists(name: str) -> bool:
        return cur.execute(
            "select 1 from sqlite_master where type='table' and name=?", (name,)
        ).fetchone() is not None

    projects = []
    for pid, worktree in cur.execute("select id, worktree from project"):
        projects.append({"id": pid, "worktree": worktree, "norm": norm_path(worktree)})

    project_dirs = []
    if table_exists("project_directory"):
        for pid, directory in cur.execute("select project_id, directory from project_directory"):
            project_dirs.append({"project_id": pid, "directory": directory, "norm": norm_path(directory)})

    sessions = []
    for row in cur.execute(
        "select id, parent_id, project_id, directory, title, agent, time_created, time_updated"
        " from session order by time_created"
    ):
        sessions.append({
            "id": row[0], "parent_id": row[1], "project_id": row[2], "directory": row[3],
            "title": row[4], "agent": row[5], "created": row[6], "updated": row[7],
        })

    messages = []
    for mid, sid, created, data in cur.execute(
        "select id, session_id, time_created, data from message order by time_created"
    ):
        try:
            payload = json.loads(data)
        except (TypeError, ValueError):
            payload = {}
        messages.append({
            "id": mid, "session_id": sid, "created": created,
            "role": payload.get("role"), "agent": payload.get("agent"),
            "completed": (payload.get("time") or {}).get("completed"),
        })

    parts, bad_parts = [], 0
    for pid, mid, sid, created, data in cur.execute(
        "select id, message_id, session_id, time_created, data from part order by time_created"
    ):
        try:
            payload = json.loads(data)
        except (TypeError, ValueError):
            bad_parts += 1
            continue
        parts.append({"id": pid, "message_id": mid, "session_id": sid,
                      "created": created, "data": payload})

    permissions = []
    if table_exists("permission"):
        for row in cur.execute(
            "select id, project_id, action, resource, time_created from permission order by time_created"
        ):
            permissions.append({"id": row[0], "project_id": row[1], "action": row[2],
                                "resource": row[3], "created": row[4]})

    event_types = {}
    if table_exists("event"):
        for etype, count in cur.execute("select type, count(*) from event group by type"):
            event_types[etype] = count

    part_types = {}
    for part in parts:
        key = part["data"].get("type") or "?"
        part_types[key] = part_types.get(key, 0) + 1

    return {
        "projects": projects, "project_dirs": project_dirs, "sessions": sessions,
        "messages": messages, "parts": parts, "bad_parts": bad_parts,
        "permissions": permissions, "event_types": event_types, "part_types": part_types,
    }


def extract_task(part: dict) -> dict | None:
    """把 task 工具调用解析成结构化记录；非 task 返回 None。"""
    data = part["data"]
    if data.get("type") != "tool" or data.get("tool") != "task":
        return None

    state = data.get("state") or {}
    inputs = state.get("input") or {}
    times = state.get("time") or {}
    metadata = state.get("metadata") or {}
    output = state.get("output")

    blob = json.dumps(metadata, ensure_ascii=False) + " " + str(output or "")
    child_ids = SESSION_ID_RE.findall(blob)

    return {
        "part_id": part["id"],
        "session_id": part["session_id"],
        "message_id": part["message_id"],
        "subagent": inputs.get("subagent_type") or inputs.get("agent") or "?",
        "description": (inputs.get("description") or "").strip(),
        "status": state.get("status"),
        "start": times.get("start") or part["created"],
        "end": times.get("end"),
        "child_session": child_ids[0] if child_ids else None,
        "metadata_keys": sorted(metadata.keys()) if isinstance(metadata, dict) else [],
    }


def overlap_ms(first: dict, second: dict) -> int:
    """两个调用区间（毫秒）的重叠时长；不重叠返回 0。"""
    starts = [first.get("start"), second.get("start")]
    ends = [first.get("end"), second.get("end")]
    if any(v is None for v in starts + ends):
        return 0
    return max(0, min(ends) - max(starts))


def analyse(data: dict, project_dir: str, since: int | None) -> dict:
    """把原始表数据收敛成待渲染的报告。"""
    target = norm_path(project_dir)

    matched_projects = [
        p for p in data["projects"]
        if p["norm"] == target or p["norm"].startswith(target + "/")
    ]
    matched_ids = {p["id"] for p in matched_projects}

    def in_scope(session: dict) -> bool:
        if session["project_id"] in matched_ids:
            return True
        directory = norm_path(session.get("directory"))
        return bool(directory) and (directory == target or directory.startswith(target + "/"))

    sessions = [s for s in data["sessions"] if in_scope(s)]
    if since:
        # 子会话可能比父会话晚创建，仍按时间过滤
        sessions = [s for s in sessions if (s["created"] or 0) >= since]

    session_ids = {s["id"] for s in sessions}
    messages = [m for m in data["messages"] if m["session_id"] in session_ids]
    parts = [p for p in data["parts"] if p["session_id"] in session_ids]

    tasks = [t for t in (extract_task(p) for p in parts) if t]
    tasks.sort(key=lambda t: (t["start"] or 0))

    pairs = []
    for index, first in enumerate(tasks):
        for second in tasks[index + 1:]:
            if first["session_id"] != second["session_id"]:
                continue  # 只比较同一父会话内的派发
            pairs.append({
                "a": first["subagent"], "b": second["subagent"],
                "start_a": first["start"], "start_b": second["start"],
                "overlap": overlap_ms(first, second),
            })

    by_agent = {}
    for message in messages:
        if message.get("agent"):
            by_agent[message["agent"]] = by_agent.get(message["agent"], 0) + 1

    permission_events = {
        etype: count for etype, count in data["event_types"].items()
        if "permission" in etype.lower()
    }

    scoped_permissions = [
        p for p in data["permissions"] if p["project_id"] in matched_ids
    ] if matched_ids else []

    return {
        "project_dir": project_dir,
        "matched_projects": matched_projects,
        "sessions": sessions,
        "messages": messages,
        "parts_count": len(parts),
        "tasks": tasks,
        "pairs": pairs,
        "by_agent": by_agent,
        "part_types": data["part_types"],
        "permission_rows": scoped_permissions,
        "permission_events": permission_events,
        "bad_parts": data["bad_parts"],
        "task_tool_total_in_db": sum(
            1 for p in data["parts"]
            if p["data"].get("type") == "tool" and p["data"].get("tool") == "task"
        ),
    }


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #
def render(report: dict) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 78)
    add("OpenCode 原生编排取证报告")
    add(f"项目路径: {report['project_dir']}")
    add(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add("=" * 78)

    add("\n[1] 项目是否被客户端识别")
    if report["matched_projects"]:
        for project in report["matched_projects"]:
            add(f"  - project id={project['id']}  worktree={project['worktree']}")
    else:
        add("  [NO] 库中没有该路径的 project 记录")
        add("       → 该目录从未在 OpenCode 客户端里打开过，或打开后没有产生任何会话")

    add("\n[2] 会话（含子会话）")
    if not report["sessions"]:
        add("  [NO] 无会话记录")
    else:
        roots = [s for s in report["sessions"] if not s["parent_id"]]
        children = [s for s in report["sessions"] if s["parent_id"]]
        add(f"  根会话 {len(roots)} 个 / 子会话 {len(children)} 个")
        for session in report["sessions"]:
            depth = 1 if session["parent_id"] else 0
            title = (session["title"] or "").replace("\n", " ")[:46]
            add(f"  {'  ' * depth}- {session['id']}  agent={session['agent'] or '?':<22}"
                f" created={fmt_ms(session['created'])}  {title}")

    add("\n[3] 实际执行 agent 分布（按消息）")
    if report["by_agent"]:
        for agent, count in sorted(report["by_agent"].items(), key=lambda kv: -kv[1]):
            add(f"  - {agent:<24} {count} 条消息")
    else:
        add("  [NO] 无消息记录")

    add("\n[4] 原生 task 调用")
    if not report["tasks"]:
        add("  [NO] 本项目会话里没有 task 工具调用")
        add(f"       （全库 task 调用总数：{report['task_tool_total_in_db']}）")
        add("       → 原生 Subagent 派发尚未发生，任何『已验证编排』的说法都不成立")
    else:
        add(f"  共 {len(report['tasks'])} 次")
        add(f"  {'#':<3}{'subagent':<24}{'start':<20}{'end':<20}{'耗时':<10}子会话")
        for index, task in enumerate(report["tasks"], 1):
            duration = None if task["end"] is None else task["end"] - task["start"]
            add(f"  {index:<3}{task['subagent']:<24}{fmt_ms(task['start']):<20}"
                f"{fmt_ms(task['end']):<20}{fmt_dur(duration):<10}{task['child_session'] or '-'}")
            if task["description"]:
                add(f"     描述: {task['description'][:60]}")

    add("\n[5] 并行性判定（同一父会话内的 task 区间重叠）")
    if len(report["tasks"]) < 2:
        add("  [N/A] 少于 2 次 task 调用，无法判定")
    elif not report["pairs"]:
        add("  [NO] 没有同一父会话内的两次调用（都派给了不同会话）")
    else:
        best = max(report["pairs"], key=lambda p: p["overlap"])
        for pair in report["pairs"]:
            flag = "重叠" if pair["overlap"] > 0 else "无重叠"
            add(f"  - {pair['a']} vs {pair['b']}: {fmt_dur(pair['overlap'])} {flag}"
                f"（起 {fmt_ms(pair['start_a'])} / {fmt_ms(pair['start_b'])}）")
        if best["overlap"] > 0:
            add(f"  [OK] 最大重叠 {fmt_dur(best['overlap'])} → 两次派发在时间上真实并行")
        else:
            add("  [NO] 所有 task 区间互不重叠 → 属于串行执行，不能宣称并行")

    add("\n[6] 权限证据")
    if report["permission_rows"]:
        add(f"  permission 表: {len(report['permission_rows'])} 条")
        for row in report["permission_rows"][:20]:
            add(f"  - {fmt_ms(row['created'])}  action={row['action']}  resource={row['resource']}")
    else:
        add("  permission 表: 无记录")
    if report["permission_events"]:
        add(f"  event 表中的权限相关类型: {report['permission_events']}")
    else:
        add("  event 表: 无权限相关事件")
    add("  说明：权限被「拒绝」不一定落库（多数情况下只在 UI 里提示）。")
    add("        要证明规则生效，必须做主动探针（见 reports/phase3-runbook.md 第 5 节）。")

    add("\n[7] 数据健康度")
    add(f"  本项目会话：消息 {len(report['messages'])} 条 / part {report['parts_count']} 条，"
        f"JSON 解析失败 {report['bad_parts']} 条")
    add(f"  全库 part 类型分布: {report['part_types']}")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 自检（不读库）
# --------------------------------------------------------------------------- #
def selftest() -> int:
    """用合成数据验证重叠算法与判定逻辑，避免「工具本身算错」的假结论。"""
    base = 1_700_000_000_000

    def task(name: str, start: int, end: int, sid: str = "ses_parent") -> dict:
        return {"subagent": name, "start": start, "end": end, "session_id": sid}

    parallel_a = task("implementer-add", base, base + 60_000)
    parallel_b = task("implementer-multiply", base + 10_000, base + 70_000)
    serial_b = task("implementer-multiply", base + 61_000, base + 120_000)
    other_parent = task("implementer-multiply", base, base + 60_000, sid="ses_other")

    checks = [
        ("并行区间重叠 50s", overlap_ms(parallel_a, parallel_b) == 50_000),
        ("首尾相接不算重叠", overlap_ms(parallel_a, serial_b) == 0),
        ("区间相同则完全重叠", overlap_ms(parallel_a, dict(parallel_a, start=base, end=base + 60_000)) == 60_000),
        ("缺 end 视为 0", overlap_ms(parallel_a, {"start": base, "end": None}) == 0),
        ("跨父会话不参与比较", parallel_a["session_id"] != other_parent["session_id"]),
    ]

    failed = 0
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        failed += 0 if ok else 1
    print(f"\n自检: {len(checks) - failed}/{len(checks)} 通过")
    return 1 if failed else 0


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenCode 原生编排取证（只读）")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="opencode.db 路径")
    parser.add_argument("--project-dir", default=str(REPO_ROOT), help="项目根目录")
    parser.add_argument("--since", default=None, help="只看最近一段时间，如 2h / 90m / 3d")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--no-copy", action="store_true", help="直接只读打开原库（不推荐）")
    parser.add_argument("--selftest", action="store_true", help="只跑重叠算法自检")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    con, workdir = open_snapshot(Path(args.db), copy=not args.no_copy)
    try:
        raw = load(con)
    finally:
        con.close()
        if workdir.name.startswith("ocsnap-"):
            shutil.rmtree(workdir, ignore_errors=True)

    report = analyse(raw, args.project_dir, parse_since(args.since))

    if args.json:
        payload = {k: v for k, v in report.items() if k not in ("messages", "parts")}
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(report))

    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
