# 路线 A：AppleHDA / AppleALC 为什么在这块控制器上不通

记录时间：2026-11-10。系统 macOS 26.7.2（25G332）。

## 1. 起点：系统里没有 AppleHDA

```
$ ls -d /System/Library/Extensions/AppleHDA.kext
ls: No such file or directory
$ kmutil showloaded --list-only | grep -iE "AppleHDA|AppleALC"
  60  0  as.vit9696.AppleALC (1.9.9)
```

`AppleALC` 在，`AppleHDA` 不在（Tahoe 从 beta 2 起移除，支持列表里剩下带 T2 的 Intel Mac
走 `BridgeAudioController`，不需要 AppleHDA）。AppleALC 的全部工作就是给 AppleHDA 打补丁，
没有补丁对象 → 系统零音频设备：

```
$ system_profiler SPAudioDataType
Audio:
    Devices:
```

## 2. 注入原版 AppleHDA（SimpleHDA 1.0.1）

[laobamac/SimpleHDA](https://github.com/laobamac/SimpleHDA) 是 Lilu 插件，通过 OpenCore 注入
原版 AppleHDA 600.2（取自 15.8 KDK 24H23），不改系统卷、不重建 KC。

按 README：`Kernel → Add` 顺序 **Lilu → AppleALC → SimpleHDA**，`MinKernel 25.0.0 /
MaxKernel 25.99.99`，`DisableLinkeditJettison = true`（1.0.1 起不再强制 `keepsyms=1`）。

结果分两层看：

**注入成功（栈起来了）**

```
$ ioreg -l -w0 | grep SimpleHDA
  "SimpleHDAState"   = "stack-registered"
  "SimpleHDAVersion" = "1.0.1"
  "SimpleHDALocale"  = "zh_CN"
```

类也确实注册进内核（`ior` 的 `IOKitDiagnostics.Classes` 里能看到，`=0` 表示 0 个实例）：

```
"AppleHDAController"=0
"AppleHDAControllerUserClient"=0
"AppleHDAWorkLoop"=0
"AppleHDA8086_9D70Controller"=0
"IOHDACodecDevice"=0
```

**但控制器不 attach**

- HDEF 下没有子节点，`AppleHDAController` 实例恒为 0；
- 没有 `IOHDACodecDevice`，AppleALC 连编解码器都看不到，layout 怎么改都没意义。

> 顺带排除一个误判：类名带 `=0` 是"已注册、零实例"，不是"没加载"。前者说明代码进去了，
> 后者说明没进去 —— 这两件事必须分开查，否则会一直往"kext 没注入成功"的错误方向使劲。

## 3. 找到匹配层的硬伤：class code 是 0x040100

```
$ ioreg -rn HDEF -w0 | grep -E '"(class-code|IOName|device-id|subsystem-id)"'
  "class-code"   = <00010400>
  "IOName"       = "pci8086,7728"
  "device-id"    = <28770000>
  "subsystem-id" = <81200000>
```

`<00010400>` 按 class-code 的字节序（progIF / subclass / class / rev）解读为
**class 04 / subclass 01 / progIF 00 = `0x040100`**。用同一台机器的 iGPU 校准过字节序：

```
IGPU: "class-code" = <00000300>   → class 0x03 / subclass 0x00 = 0x030000  ✓
```

而 `AppleHDAController` 的匹配键是 `IOPCIClassMatch = 0x04020000 & 0xFFFE0000`，
掩码把最低一位 subclass 抹掉，也就是**只认 0x0402 / 0x0403**。`0x0401` 不在范围内。

这不是 macOS 这边被谁改的 —— Windows 侧的主硬件 ID 就是：

```
PCI\VEN_8086&DEV_7728&CC_0401
  -> Configured [oem14.inf:PCI\VEN_8086&DEV_7728&CC_0401,IntcAudioBus.NT]
```

固件/BIOS 上报的就是 `0401`，Windows 靠 Intel 的 **IntcAudioBus**（新的 Audio Bus 驱动，
不是传统 `hdaudbus`）才把它驱动起来。macOS 如实读出这个值，然后 AppleHDA 就不看它。

## 4. 试着伪造 class code

`DeviceProperties → PciRoot(0x0)/Pci(0x1f,0x3)` 加：

```xml
<key>class-code</key>
<data>AAADBAA=</data>   <!-- 00 03 04 00 = 0x040300 -->
```

注入生效（ioreg 确认）：

```
"class-code" = <00030400>
"layout-id"  = <07000000>
"alc-layout-id" = <61000000>
```

**但 `AppleHDAController` 仍然是 0 实例。** 两种解释都成立且无法在本机进一步区分：

1. IOKit 匹配读的是 PCI 配置空间里的真实 class code，不吃 DeviceProperties 的同名属性；
2. 匹配上了，但 `start()` 在 `0x7728` 上失败（这类"类在、实例无"的表现和 start 失败一致）。

想用内核日志区分，失败于取证环境：dmesg 被 `itlwm` + `tcp_connection_summary` 冲干净
（`msgbuf` 从 1 MB 加到 32 MB 仍只留到 `t=1137s`），统一日志里没有内核 HDA 记录，
`kmutil unload` SimpleHDA 被内核拒绝（`kext is in use or retained`）。

## 5. 为什么判定"不通"而不是"还没调对"

- 同代硬件已有公开结论：[WTLAudio](https://github.com/watchthelight-labs/WTLAudio) 针对
  Arrow Lake-HX `8086:7F50`（Tahoe 26.7.2）写得很直白：Tahoe 移除 AppleHDA 后 AppleALC 的
  `alcid=` 路线不存在，只能用自包含的 VoodooHDA。`0x7728` 与 `0x7F50` 同属这一代
  "Intel Smart Sound / IntcAudioBus" 控制器。
- AppleALC 的 controller patch 列表（[Wiki: Supported codecs](https://github.com/acidanthera/AppleALC/wiki/Supported-codecs)）
  收录到 800 系列 `0x7F50` 为止，**没有 `0x7728`**。
- VoodooHDA 用 `IOPCIPrimaryMatch 0x77288086` 精确绑上去后，能正常读到 ALC256 并跑起引擎
  —— 说明硬件本身有标准 HDA 寄存器接口，只是 AppleHDA 这条栈在 Tahoe 上认不了它。

结论：AppleHDA 路线的成本从"调 layout"变成了"改 AppleALC/AppleHDA 的控制器支持"，
不划算。切 VoodooHDA 后 30 分钟内出声。

## 残留物（本机）

- `Kexts/AppleALC.kext`、`Kexts/SimpleHDA.kext` 保留在 EFI 里但 `Enabled: false`，
  等哪天官方支持了这颗控制器，开回来即可；
- `kdk_applehda.plist`（AppleHDA 600.2 的 Info.plist 备份）留在工作区。
