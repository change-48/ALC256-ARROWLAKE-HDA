# ALC256-ARROWLAKE-HDA

在 macOS 26（Tahoe）上，把 **Intel Arrow Lake-H HDA 控制器（`8086:7728`）背后的 Realtek ALC256**
从"系统报告里一个音频设备都没有"推进到 **内置扬声器出声、音量可调、双声道正常**。

> 这不是教程，是一次真实的排查记录：先走 AppleHDA 正路（失败，附证据），
> 再退回 VoodooHDA，被自己的引脚序号撞号卡了一轮，最后靠驱动内部日志拆开。
> 每一步的判据都写在文里，没有一条是"试试看"。

---

## 硬件与系统

| 项 | 值 |
| --- | --- |
| 机器 | Honor 笔记本（黑苹果，OpenCore 1.0.8 引导），SMBIOS 伪装 `MacBookPro16,2` |
| CPU | Intel Core Ultra 7 255H（Arrow Lake-H） |
| HDA 控制器 | `pci8086,7728`，subsystem `1ee7:2081`，**PCI class code `0x040100`** |
| 编解码器 | Realtek **ALC256**（`0x10EC0256`，rev `0x00`，step `0x02`），codec address 0 |
| Windows 侧硬件 ID | `HDAUDIO\FUNC_01&VEN_10EC&DEV_0256&SUBSYS_1EE72082` |
| 系统 | macOS 26.7.2（25G332），Darwin 25.6.0 |
| 相关组件 | Lilu 1.7.3、AppleALC 1.9.9（最终禁用）、VoodooHDA 3.7.0 BL（最终启用） |

声卡型号不是猜的：从 Windows 分区只读取证，`setupapi.dev.log` 与驱动 INF（`oem73.inf`）双向对上
`VEN_10EC&DEV_0256&SUBSYS_1EE72082`；进入 macOS 后 `vhda_msgbuf` 又独立读出 `Codec ID: 0x10ec0256`。

---

## 最终结果

```
Internal Speakers:
  Default Output Device: Yes
  Output Channels: 4
  Current SampleRate: 48000
  Transport: Built-in
Line In:
  Default Input Device: Yes
  Input Channels: 2
```

| 能力 | 状态 |
| --- | --- |
| 内置扬声器出声 | ✅ |
| 系统音量滑块改变响度 | ✅ |
| 静音 | ✅ |
| 双声道 | ✅ |
| 耳机孔自动切换 | ⚠️ 未验证 |
| 内置麦克风 | ⚠️ 与外部麦合并，只显示为 `Line In` |

整套东西都在 EFI 分区里（OpenCore 注入），**不改系统卷、不需要重建内核集合、升级 macOS 不会被冲掉**。

---

## 仓库内容

| 路径 | 内容 |
| --- | --- |
| [`dist/VoodooHDA_BL.kext`](dist/) | 已按本文改好的 kext（**只改 `Info.plist`，可执行文件未动**），附 `SHA256SUMS` 与出处说明 |
| [`scripts/apply-patch.py`](scripts/apply-patch.py) | 把同样的改动应用到你自己手里的 VoodooHDA BL 变体（幂等、先备份、支持 `--dry-run`） |
| [`scripts/audio-check.sh`](scripts/audio-check.sh) | 一键自检：驱动 / 设备 / HDEF 属性 / 实例数 / 音量 / 驱动内部日志 |
| [`config/`](config/) | OpenCore `Kernel → Add` 条目、`DeviceProperties` 片段、kext 键值对照表 |
| [`docs/`](docs/) | 路线 A 证据链、路线 B 两个坑（附源码行号）、codec 拓扑与控件表 |
| [`third_party/`](third_party/) | VoodooHDA 的 BSD-2-Clause 许可全文 |

二进制在仓库里的理由：这套配置能不能复现，很大程度取决于**改的是哪一份 kext**。
BL 变体的 `IOAudioFamily` 是编译进本体的，不同来源的 build 细节不同，光给一份 plist 片段
容易对不上。所以这里放的是"出处 + 哈希 + 只改 plist"的完整副本，并同时保留 `apply-patch.py`，
两条路都通。上游许可见 [`third_party/`](third_party/)。

---

## 两条路线

### 路线 A：AppleHDA / AppleALC —— 此控制器上不通

macOS 26 从 beta 2 起删掉了 `AppleHDA.kext`（本机 `/System/Library/Extensions` 里确实没有），
AppleALC 只负责"给 AppleHDA 打补丁"，没有补丁对象就什么也做不了 —— 系统报告里音频设备为空。

试过 [laobamac/SimpleHDA](https://github.com/laobamac/SimpleHDA) 1.0.1（OpenCore 注入原版 AppleHDA 600.2）：

- 注入是**成功**的：`SimpleHDAState = stack-registered`，`AppleHDAController` / `AppleHDAWorkLoop` /
  `AppleHDA8086_9D70Controller` 这些类都注册进了内核；
- 但 `AppleHDAController` **实例数恒为 0**，HDEF 下没有子节点，`IOHDACodecDevice = 0`；
- 找到一处硬伤：HDEF 的 `class-code = <00010400>`（class 04 / subclass **01** / progIF 00 = `0x040100`），
  而 `AppleHDAController` 的匹配条件是 `IOPCIClassMatch = 0x04020000&0xFFFE0000`，只吃 **0x0402 / 0x0403**；
- 交叉验证：Windows 里这块控制器的主硬件 ID 就是 `PCI\VEN_8086&DEV_7728&CC_0401`，
  Windows 靠 Intel 的 **IntcAudioBus**（`oem14.inf`）驱动它，不是传统 HD Audio 总线；
- 用 `DeviceProperties` 把 `class-code` 伪造成 `<00030400>`（ioreg 确认已生效）→ **仍然是 0 实例**。

同代硬件已有公开结论：[watchthelight-labs/WTLAudio](https://github.com/watchthelight-labs/WTLAudio)
（Arrow Lake-HX `8086:7F50`、ALC257、Tahoe 26.7.2）明确写了 Tahoe 移除 AppleHDA 后
`alcid=` 路线不存在，改走自包含的 VoodooHDA。本文这台是同一代控制器，结论一致。

细节与完整证据链：[`docs/01-applehda-path.md`](docs/01-applehda-path.md)

### 路线 B：VoodooHDA —— 通了，但要修两个坑

VoodooHDA 自带 HDA 解析器，不需要 AppleHDA。踩到两个坑：

**坑 1：输出关联被自己的去重逻辑关掉（无声）**

layout 97 给出双扬声器 `0x14`(seq 1) + `0x1B`(seq 0) + 耳机 `0x21`(assoc 2)。解析器会把耳机
合并进"最后一个固定扬声器"的关联，序号取 `spkSeq + 1`：

```
Jack sensing: merged HP Out nid=33 into association 1 seq=1 (with Speaker nid=27)
Duplicate pin 1 (33) in association 1! Disabling association.
Association 0 (1) out (disabled):
```

耳机被塞到 seq=1，可 `0x14` 本来就是 seq=1 → 撞号 → 整条输出关联禁用 → 只剩输入。

修法：用 `NodesToPatch` 把 `0x14` 的序号挪到 2（`0x90170111` → `0x90170112`），给耳机让位。
`NodesToPatch` 在 AppleALC 引脚表**之后**应用，能覆盖。

**坑 2：音量滑块不动响度**

codec 拓扑里两条 DAC 分头喂不同的脚：`DAC3 → 0x1B + 耳机`，`DAC2 → 0x14`。
而 `Master Volume` 只挂 `nid 2`（DAC2），`PCM Volume` 才同时挂 `nid 2 + nid 3`。
系统音量走的是 `SOUND_MIXER_VOLUME` → 只改 DAC2，而实际出声走 DAC3。

修法：`VoodooHDAEnableVolumeChangeFix = true`，让 `volumeChanged()` 改走 `SOUND_MIXER_PCM`
（`VoodooHDAEngine.cpp:1060` 的 fix 分支），两条 DAC 一起调。

细节与源码行号：[`docs/02-voodoohda-pinseq.md`](docs/02-voodoohda-pinseq.md) ·
拓扑与控件表：[`docs/03-codec-topology.md`](docs/03-codec-topology.md)

---

## 生效配置

全部改动集中在两处：`EFI/OC/Kexts/VoodooHDA_BL.kext/Contents/Info.plist` 与 `EFI/OC/config.plist`。

| 位置 | 键 | 值 | 作用 |
| --- | --- | --- | --- |
| kext | `IOPCIMatch` | `0x77288086` | 只绑这块控制器，不抢 HDMI 音频 |
| kext | `IOProbeScore` | `99000` | 高于 Apple 的驱动 |
| kext | `LayoutId` | `97` | ALC256 双扬声器引脚表 |
| kext | `NodesToPatch` | `Codec 0 / Node 20 / 0x90170112` | 解 seq 撞号 |
| kext | `VoodooHDAEnableVolumeChangeFix` | `true` | 音量改走 PCM，覆盖两颗 DAC |
| kext | `VoodooHDAEnableMuteFix` | `true` | 静音 |
| kext | `VoodooHDAVerboseLevel` | `2` | 排障用，稳定后可降 1 |
| config | `Kernel → Add[9]` | `VoodooHDA_BL.kext`，Min 25.0.0 / Max 25.99.99 | 注入 |
| config | `Kernel → Add` | `AppleALC` / `SimpleHDA` = `Enabled: false` | 不与 VoodooHDA 抢设备 |
| config | `DeviceProperties → HDEF` | `layout-id = 97`、`voodoo-layout-id = 61 00 00 00` | 双保险 |
| config | `boot-args` | `voodoo-layout-id=97`、`msgbuf=33554432` | boot-arg 优先级最高 |

现成的 plist 片段：[`config/kernel-add.plist`](config/kernel-add.plist) ·
[`config/device-properties.plist`](config/device-properties.plist) ·
键值说明：[`config/voodoohda-keys.md`](config/voodoohda-keys.md)

---

## 复现步骤

1. **拿到 kext**（二选一）：
   - 直接用 [`dist/VoodooHDA_BL.kext`](dist/)（先 `shasum -a 256 -c SHA256SUMS` 校验）；
   - 或者自己找一份 VoodooHDA 3.7.0 **BL** 变体（内嵌 `IOAudioFamily`、可被 OpenCore 注入），
     然后 `python3 scripts/apply-patch.py /path/to/VoodooHDA_BL.kext`。
     注意 LE 变体依赖系统 `IOAudioFamily`，引导阶段注入会因 `Vtable patching failed` /
     `Invalid Parameter` 失败。
2. 放进 `EFI/OC/Kexts/`，`Kernel → Add` 加一条（顺序在 Lilu 之后即可，`AppleALC`/`SimpleHDA` 关掉），
   条目照抄 [`config/kernel-add.plist`](config/kernel-add.plist)。
3. 若用的是 `dist/` 里的 kext，**这一步已经做完**；否则用 `apply-patch.py` 改
   `LayoutId`、`NodesToPatch`、两个 Fix 开关（[`config/voodoohda-keys.md`](config/voodoohda-keys.md) 有对照表）。
4. `DeviceProperties` 给 HDEF 加 `voodoo-layout-id`，boot-args 加同名参数。
5. 重启，跑 `scripts/audio-check.sh` 看设备；出声不对就 `sudo vhda_msgbuf` 读驱动内部日志。

---

## 排障方法（比结论更值钱的部分）

1. **别信 dmesg。** 这台机器的内核缓冲被 `itlwm` 和 `tcp_connection_summary` 在 20 分钟内冲干净，
   `msgbuf` 从 1 MB 加到 32 MB 也没用 —— 最早只留到 `t=1137s`。要用驱动自己的环形缓冲。
2. **`vhda_msgbuf`** 通过 `VoodooHDADevice` 的用户客户端 `IOConnectMapMemory64`
   (`kVoodooHDAMemoryMessageBuffer = 0x2000`) 直接读驱动内部消息，完全不受内核缓冲影响。
   今天的两个根因（关联去重、音量 DAC 分离）都是它给出来的。
3. **改 layout 之前先确认 layout 真的生效。** 这台第一次用 layout 13 毫无变化，原因是
   `layout-id = 7`（AppleALC 为 AppleHDA 注入的）优先级更高，而 ALC256 没有 layout 7 →
   解析器退回 BIOS 引脚（全是 `0x400000f0` = 未连接）→ 只剩 `Line In`。
4. **匹配失败 ≠ 启动失败。** ioreg 里类名有 `=0` 的条目说明类已注册（代码进去了），
   不代表有实例（没 attach）；两者要分开查。

---

## 出处

- [laobamac/SimpleHDA](https://github.com/laobamac/SimpleHDA) —— Tahoe 上恢复原版 AppleHDA 栈，本文路线 A 用了它的 1.0.1
- [watchthelight-labs/WTLAudio](https://github.com/watchthelight-labs/WTLAudio) —— 同代 Arrow Lake-HX 控制器在 Tahoe 上走 VoodooHDA 的公开结论
- [CloverHackyColor/VoodooHDA](https://github.com/CloverHackyColor/VoodooHDA) —— 驱动本体（BSD-2-Clause）
- [acidanthera/AppleALC Wiki: Supported codecs](https://github.com/acidanthera/AppleALC/wiki/Supported-codecs) —— ALC256 的 layout 清单
- [olarila: VoodooHDA problemas comuns](https://olarila.com/topic/145-voodoohda-problemas-comuns/) —— `VoodooHDAEnableVolumeChangeFix` 等开关的原始说明

## 许可

文档与脚本 MIT；VoodooHDA 本体为 BSD-2-Clause，请遵循其原始许可。
