#!/usr/bin/env python3
"""把本仓库记录的改动应用到一个 VoodooHDA BL 变体上（可重复执行）。

用法：
    python3 scripts/apply-patch.py /path/to/VoodooHDA_BL.kext
    python3 scripts/apply-patch.py /path/to/VoodooHDA_BL.kext --dry-run

改动项（与 docs/02-voodoohda-pinseq.md 一一对应）：
  1. IOPCIMatch             -> 0x77288086     只绑 8086:7728
  2. IOProbeScore           -> 99000
  3. LayoutId               -> 97             ALC256 双扬声器引脚表
  4. NodesToPatch           -> nid 0x14 的 pin config 改 0x90170112（解耳机合并撞号）
  5. VolumeChangeFix / MuteFix -> true        音量走 SOUND_MIXER_PCM（覆盖两颗 DAC）
  6. VoodooHDAVerboseLevel  -> 2              排障用，稳定后可改 1

只改 Info.plist，不动可执行文件；原文件会先备份为 Info.plist.bak。
"""

import plistlib
import shutil
import sys
from pathlib import Path

TARGET_PCIMATCH = "0x77288086"
TARGET_PROBE = 99000
TARGET_LAYOUT = 97
TARGET_VERBOSE = 2


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry = "--dry-run" in sys.argv
    if not args:
        print(__doc__)
        return 2

    kext = Path(args[0])
    plist = kext / "Contents" / "Info.plist"
    if not plist.is_file():
        print(f"找不到 {plist}")
        return 2

    with plist.open("rb") as f:
        info = plistlib.load(f)

    pers = info.get("IOKitPersonalities", {})
    key = next((k for k in pers if "VoodooHDA" in k), None)
    if key is None:
        print("Info.plist 里没有 VoodooHDA 人格，确认这是 VoodooHDA 的 kext")
        return 2

    per = pers[key]
    changes = []

    def setv(k, v):
        if per.get(k) != v:
            changes.append(f"{k}: {per.get(k)!r} -> {v!r}")
            per[k] = v

    setv("IOPCIMatch", TARGET_PCIMATCH)
    setv("IOProbeScore", TARGET_PROBE)
    setv("LayoutId", TARGET_LAYOUT)
    setv("VoodooHDAEnableVolumeChangeFix", True)
    setv("VoodooHDAEnableMuteFix", True)
    setv("VoodooHDAVerboseLevel", TARGET_VERBOSE)

    want_patch = [{
        "Codec": 0,
        "Comment": "ALC256: move speaker 0x14 to seq 2 so HP merge (seq 1) does not collide",
        "Config": "0x90170112",
        "Enable": "1",
        "Node": 20,
    }]
    if per.get("NodesToPatch") != want_patch:
        changes.append(f"NodesToPatch: {per.get('NodesToPatch')!r} -> 1 条补丁")
        per["NodesToPatch"] = want_patch

    if not changes:
        print("已经是目标配置，无需改动。")
        return 0

    print("将应用以下改动：")
    for c in changes:
        print("  -", c)

    if dry:
        print("（--dry-run，未写入）")
        return 0

    shutil.copy2(plist, plist.with_suffix(".plist.bak"))
    with plist.open("wb") as f:
        plistlib.dump(info, f, fmt=plistlib.FMT_XML, sort_keys=False)
    print(f"已写入 {plist}（原文件备份为 Info.plist.bak）")
    print("提醒：改完 kext 后重启；若无声，先看 docs/02-voodoohda-pinseq.md 的排障顺序。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
