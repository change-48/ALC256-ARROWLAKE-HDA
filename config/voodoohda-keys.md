# VoodooHDA 关键键值（本机最终值）

文件：`EFI/OC/Kexts/VoodooHDA_BL.kext/Contents/Info.plist`
路径：`IOKitPersonalities → VoodooHDA`

| 键 | 本机值 | 上游默认 | 说明 |
| --- | --- | --- | --- |
| `IOPCIMatch` | `0x77288086` | `0x04030000&0xffff0000`（class match） | 改成精确 device id：class match 会把 iGPU / 独显的 HDMI 音频函数一起抓走，且 probe score 高于 Apple 的驱动 |
| `IOProbeScore` | `99000` | `10000` | 压过 Apple 的匹配分数 |
| `IOProviderClass` | `IOPCIDevice` | 同 | — |
| `LayoutId` | `97` | `0` | 0 = 用 BIOS 引脚（本机全是 `0x400000f0` 未连接 → 只剩 Line In） |
| `NodesToPatch` | 1 条，见下 | 2 条示例（`Codec 4` / `Codec 2`） | 示例条目已置 `Enable 0` |
| `VoodooHDAEnableVolumeChangeFix` | `true` | `false` | 音量走 `SOUND_MIXER_PCM`，覆盖 DAC2+DAC3 |
| `VoodooHDAEnableMuteFix` | `true` | `false` | 静音 |
| `VoodooHDAEnableHalfVolumeFix` | `false` | — | 音量偏小时再考虑 |
| `VoodooHDAVerboseLevel` | `2` | `1` | 抓 codec 解析；稳定后降 1 |
| `Vectorize` / `Boost` / `MixerValues` / `Noise` | 上游默认 | — | 未改动 |

## NodesToPatch 条目

```xml
<key>NodesToPatch</key>
<array>
  <dict>
    <key>Codec</key><integer>0</integer>            <!-- cad（codec address），本机为 0 -->
    <key>Node</key><integer>20</integer>            <!-- nid 0x14 -->
    <key>Config</key><string>0x90170112</string>    <!-- 原 0x90170111，seq 1 -> 2 -->
    <key>Enable</key><string>1</string>             <!-- bit0 = 写 pin config -->
    <key>Comment</key><string>避开耳机合并占用的 seq=1</string>
  </dict>
</array>
```

`Enable` 是位掩码：`1` 写 pin config，`2` 写连接列表，`4` 写 widget type，
`8` 写 pin cap，`0x10` 启停 widget，`0x20`/`0x40` 选连接（源码 `Parser.cpp:620` 起）。

## boot-args

```
voodoo-layout-id=97      # 优先级最高，覆盖 PCI layout-id / 人格里的 LayoutId
msgbuf=33554432          # 排障用（本机实测仍会被 itlwm 刷掉，最终靠 vhda_msgbuf）
```

`voodoo-layout-id` 的取值顺序（`VoodooHDADevice.cpp` probe 段）：
属性 `voodoo-layout-id` → boot-arg `voodoo-layout-id` → PCI `layout-id` → 人格里的 `LayoutId`。

> 本机踩过的坑：AppleALC 会往 HDEF 注入 `layout-id = 7`（给 AppleHDA 用），
> 而 ALC256 没有 layout 7 → 解析器退回 BIOS 引脚 → 没有输出。
> 所以要么禁用 AppleALC，要么用 `voodoo-layout-id` 抢占优先级。
