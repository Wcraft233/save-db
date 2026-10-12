#!/usr/bin/env python3
"""SaveDB CI：校验 db/**/*.json 分片 + graylist.json，并合并出 savedb.json。

用法：python tools/validate_db.py [merged 输出路径，默认 savedb.json]
退出码：0 通过；1 校验失败。

校验项：
- JSON 合法、字段结构完整（appid / name / save_paths / stats）
- 文件名 == <appid>.json，分片目录 == appid 前三位，appid 全库唯一
- pattern 必须是 root 相对路径：无盘符、无反斜杠、无 .. 上溯、无用户目录段（隐私红线）
- root 编号在 0..12 已知集合内（集合外只警告，便于未来扩展）

合并规则（与 SteamSweep 端 gen_savedb / savedb.rs 完全一致）：
- appid → {"n": name, "p": [路径后缀...]}
- 后缀 = root 文本前缀 + pattern 去尾部 "/**" 后的小写相对路径
- root 0/1 太泛化，不出后缀
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

ROOT_PREFIX = {
    2: "documents/",
    3: "appdata/local/",
    6: "appdata/roaming/",
    9: "saved games/",
    11: "documents/steam cloud/",
    12: "appdata/locallow/",
}
KNOWN_ROOTS = set(range(13))
VALID_VERDICTS = {"save", "not-save", "unknown", "unsure"}


def validate_pattern(pat, errors, where):
    if not isinstance(pat, str) or not pat.strip():
        errors.append(f"{where}: pattern 为空或非字符串")
        return
    if "\\" in pat:
        errors.append(f"{where}: pattern 含反斜杠（统一用正斜杠）：{pat!r}")
    if ":" in pat or pat.startswith("/") or pat.startswith("~"):
        errors.append(f"{where}: pattern 疑似绝对路径（隐私红线）：{pat!r}")
    parts = [p for p in pat.split("/") if p]
    if any(p == ".." for p in parts):
        errors.append(f"{where}: pattern 含 .. 上溯：{pat!r}")
    # 注：用户名的泄露只可能经由绝对路径发生（上方已拦截），
    # 裸 "user"/"users" 段是常见游戏目录名（如 desperados iii/user/**），不拦截。


def validate_shard(path, errors, warnings, seen):
    rel = path.relative_to(REPO)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"{rel}: JSON 解析失败：{e}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{rel}: 顶层必须是对象")
        return None

    appid = data.get("appid")
    if not isinstance(appid, int) or isinstance(appid, bool) or appid <= 0:
        errors.append(f"{rel}: appid 缺失或非正整数")
        return None
    if path.stem != str(appid):
        errors.append(f"{rel}: 文件名 {path.name} 与 appid {appid} 不一致")
    if path.parent.name != str(appid)[:3]:
        errors.append(f"{rel}: 分片目录应为 db/{str(appid)[:3]}/，实际在 db/{path.parent.name}/")
    if appid in seen:
        errors.append(f"{rel}: appid {appid} 重复（另见 {seen[appid]}）")
    seen[appid] = str(rel)

    name = data.get("name")
    if name is not None and not isinstance(name, str):
        errors.append(f"{rel}: name 必须是字符串或 null")
        name = None

    sps = data.get("save_paths")
    if not isinstance(sps, list) or not sps:
        errors.append(f"{rel}: save_paths 缺失或为空数组")
        return appid, name, []

    suffixes = []
    for i, sp in enumerate(sps):
        where = f"{rel} save_paths[{i}]"
        if not isinstance(sp, dict):
            errors.append(f"{where}: 必须是对象")
            continue
        root = sp.get("root")
        if not isinstance(root, int) or isinstance(root, bool):
            errors.append(f"{where}: root 缺失或非整数")
            continue
        if root not in KNOWN_ROOTS:
            warnings.append(f"{where}: root={root} 不在已知集合 0..12（请确认是否笔误）")
        pat = sp.get("pattern")
        validate_pattern(pat, errors, where)
        verdict = sp.get("verdict")
        if verdict is not None and verdict not in VALID_VERDICTS:
            warnings.append(f"{where}: verdict={verdict!r} 不在常用集合 {sorted(VALID_VERDICTS)}")
        fs = sp.get("files_seen")
        if fs is not None and (not isinstance(fs, int) or isinstance(fs, bool) or fs < 0):
            errors.append(f"{where}: files_seen 必须是非负整数")
        if isinstance(pat, str) and root in ROOT_PREFIX:
            d = pat[:-3] if pat.endswith("/**") else pat
            suf = ROOT_PREFIX[root] + d.lower()
            if suf not in suffixes:
                suffixes.append(suf)

    stats = data.get("stats")
    if stats is not None:
        ok = (
            isinstance(stats, dict)
            and isinstance(stats.get("seen", 0), int)
            and isinstance(stats.get("deleted", 0), int)
        )
        if not ok:
            errors.append(f"{rel}: stats 结构异常（需要 seen/deleted 整数）")

    return appid, name, suffixes


def validate_graylist(errors):
    path = REPO / "graylist.json"
    if not path.exists():
        errors.append("graylist.json 缺失")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"graylist.json: JSON 解析失败：{e}")
        return
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        errors.append("graylist.json: entries 缺失或为空数组")
        return
    seen = set()
    for e in entries:
        if not isinstance(e, str) or not e.strip():
            errors.append(f"graylist.json: 非法条目 {e!r}")
            continue
        if e != e.lower():
            errors.append(f"graylist.json: 条目必须小写：{e!r}")
        if e in seen:
            errors.append(f"graylist.json: 条目重复：{e!r}")
        seen.add(e)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "savedb.json"
    errors, warnings = [], []
    seen = {}
    merged = {}

    shards = sorted((REPO / "db").glob("*/*.json"))
    if not shards:
        errors.append("db/ 下没有任何分片")
    for sp in shards:
        r = validate_shard(sp, errors, warnings, seen)
        if r is not None:
            appid, name, suffixes = r
            merged[str(appid)] = {"n": name, "p": suffixes}

    validate_graylist(errors)

    for w in warnings:
        print(f"WARN  {w}")
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        print(f"\n校验失败：{len(errors)} 个错误，{len(warnings)} 个警告")
        sys.exit(1)

    merged = dict(sorted(merged.items(), key=lambda kv: int(kv[0])))
    out.write_text(json.dumps(merged, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total_p = sum(len(v["p"]) for v in merged.values())
    print(f"OK：{len(shards)} 个分片，{len(merged)} 个游戏，{total_p} 条路径后缀 → {out}")


if __name__ == "__main__":
    main()
