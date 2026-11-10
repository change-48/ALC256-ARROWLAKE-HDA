# 路线 B：VoodooHDA 的两个坑（引脚序号撞号 / 音量 DAC 分离）

`VoodooHDA_BL.kext` 3.7.0（BL 变体：把 Apple `IOAudioFamily` 编进本体，
`OSBundleLibraries` 只剩 KPI + `IOPCIFamily`，所以能被 OpenCore 在引导阶段注入）。

`IOPCIMatch = 0x77288086`（精确到 device id，避免把 iGPU / 独显的 HDMI 音频函数一起抓走）。

---

## 坑 1：输出关联被解析器自己的去重逻辑关掉

### 现象

驱动加载正常、引擎存在，但只有一个输入设备，没有任何输出：

```
$ kmutil showloaded | grep Voodoo
  83  0  org.voodoo.driver.VoodooHDA (3.7.0)

$ system_profiler SPAudioDataType
Line In:  Input Channels 2 / Voodoo / Built-in
```

### 取证：读驱动内部日志

内核 dmesg 不可用（见 README 排障一节），改用 `vhda_msgbuf` 走用户客户端读驱动的环形缓冲：

```
HDA Codec #0: Realtek ALC256
HDA Codec ID: 0x10ec0256    PCI Subvendor: 0x20811ee7
AppleALC: applying 3 extra verbs for codec=0x10ec0256 layout=97
```

layout 97 的引脚确实被应用了：

```
nid 18 0x90a60130  Internal Microphone
nid 20 0x90170111  Speaker  Fixed Analog  Internal     <- 0x14
nid 25 0x04811040  Line-in   Jack 1/8     External     <- 0x19
nid 27 0x90170110  Speaker  Fixed Analog  Internal     <- 0x1B
nid 33 0x04211020  Headphones Jack 1/8    External     <- 0x21
```

然后就断在这里：

```
Jack sensing: merged HP Out nid=33 into association 1 seq=1 (with Speaker nid=27)
Parsing pin associations...
Duplicate pin 1 (33) in association 1! Disabling association.
2 associations found:
Association 0 (1) out (disabled):
 Pin nid=27 seq=0
 Pin nid=33 seq=1
Association 1 (3) in:
 Pin nid=18 seq=0
 Pin nid=25 seq=1
```

### 机制

`Parser.cpp` 里两步：

1. **合并**（`~2796`）：取"最后一个 固定 扬声器"作为 `spkWidget`，把耳机挪进它的关联，
   序号固定取 `spkSeq + 1`：

```c
if (hpAssoc != spkAssoc) {
    UInt32 newSeq = spkSeq + 1;
    ...
    dumpMsg("Jack sensing: merged HP Out nid=%d into association %d seq=%d (with Speaker nid=%d)\n", ...);
}
```

本机 `spkWidget` 是 `0x1B`（seq 0），于是耳机被塞到 **seq 1**。

2. **去重**（`~1092`）：同一关联里序号已经被人占了就整条禁用：

```c
if (assocs[cnt].pins[seq] != 0) {
    dumpMsg("Duplicate pin %d (%d) in association %d! Disabling association.\n", ...);
    assocs[cnt].enable = 0;
}
```

而 layout 97 里 `0x14` 本来就是 **assoc 1 / seq 1** → 撞车 → 整条输出关联 disabled。
所以扬声器、耳机全没了，只剩输入关联（3）里的 `Line In`。

一句话：**layout 97 的双扬声器序号排布（seq 1 + seq 0）与 VoodooHDA 的耳机合并规则
（占用 seq 1）天然冲突。**

### 修法

`Info.plist → IOKitPersonalities → VoodooHDA → NodesToPatch`：
把 `0x14`（nid 20）的 pin config 从 `0x90170111` 改成 `0x90170112`，即序号 1 → 2：

```xml
<key>NodesToPatch</key>
<array>
  <dict>
    <key>Codec</key><integer>0</integer>       <!-- cad -->
    <key>Node</key><integer>20</integer>       <!-- nid 0x14 -->
    <key>Config</key><string>0x90170112</string>
    <key>Enable</key><string>1</string>        <!-- bit0 = 写 pin config -->
  </dict>
</array>
```

`NodesToPatch` 在 AppleALC 引脚表**之后**应用（解析日志里 "AppleALC: applying..." 在前、
"Nodes patching" 在后），所以能覆盖。

结果：`assoc 1 = {0x1B seq0, 0x21 seq1(合并来的), 0x14 seq2}` 三针不撞号 → 关联成立 →
`Internal Speakers` 输出引擎出现。

> 备选方案（未采用）：把 0x1B 改成独立关联（类似 layout 14 的 `as=4`），
> 代价是两个扬声器分成两个设备，听感上不如合并成一个。

---

## 坑 2：音量滑块不动响度

出声之后发现音量无效。控件表（`vhda_msgbuf` 的 `DUMPING Volume Controls`）：

```
Master Volume (OSS: vol)
   +- control  0 (nid   2 out):  -65/+0dB (88 steps)
   +- control  7 (nid  20 out):  vol, pcm mute      <- 只有 mute，无增益级
   +- control 11 (nid  27 out):  vol, pcm mute
   +- control 13 (nid  33 out):  vol, pcm mute

PCM Volume (OSS: pcm)
   +- control  0 (nid   2 out):  -65/+0dB (88 steps)
   +- control  1 (nid   3 out):  -65/+0dB (88 steps)
   ...
```

路径：

```
nid=27 [Internal Speakers]  <- nid=3 [DAC]     DAC3
nid=33 [Headphones]         <- nid=3 [DAC]     DAC3
nid=20 [Internal Speakers]  <- nid=2 [DAC]     DAC2
```

- `Master Volume` 只挂 **nid 2 (DAC2)**；
- 实际出声走 **DAC3**（0x1B + 耳机）；
- 三个 pin 只有 mute 能力，没有增益级，所以调不了。

macOS 音量滑块走 `SOUND_MIXER_VOLUME` → 只写 DAC2 → 听感不变。
（软件侧其实是好的：`IOAudioControlValue` 会跟着系统音量变，我实测 set volume 45 → 67、
20 → 45，动了，只是没写到出声那条路上。）

### 修法

`VoodooHDAEngine.cpp:1060 volumeChanged()`：

```c
case SOUND_MIXER_VOLUME:
    if (volumeControl->getChannelID() == 1) {
        if (mEnableVolumeChangeFix) {
            mDevice->audioCtlOssMixerSet(pcmDevice, SOUND_MIXER_PCM, newValue, newValue);
        } else {
            mDevice->audioCtlOssMixerSet(pcmDevice, SOUND_MIXER_VOLUME, newValue, pcmDevice->right[0]);
        }
    }
    ...
if (mEnableVolumeChangeFix) {          // cue8chalk: pin config 没设对时这个循环是必需的
    for (int n = 0; n < SOUND_MIXER_NRDEVICES; n++)
        mDevice->audioCtlOssMixerSet(pcmDevice, n, newValue, newValue);
}
```

打开 `VoodooHDAEnableVolumeChangeFix` 后，音量改走 `SOUND_MIXER_PCM` —— 这个 mixer
同时挂 `nid 2` 和 `nid 3`，两条 DAC 一起调。顺手打开 `VoodooHDAEnableMuteFix`。

结果：音量可调、静音可用、双声道正常。

---

## 最终 kext 关键键值

| 键 | 值 | 理由 |
| --- | --- | --- |
| `IOPCIMatch` | `0x77288086` | 只绑这块控制器 |
| `IOProbeScore` | `99000` | 高于 Apple 的驱动 |
| `LayoutId` | `97` | ALC256 双扬声器 + 耳机 + 内置麦 + LineIn |
| `NodesToPatch` | `{Codec 0, Node 20, 0x90170112, Enable 1}` | 解 seq 撞号 |
| `VoodooHDAEnableVolumeChangeFix` | `true` | 音量改走 PCM |
| `VoodooHDAEnableMuteFix` | `true` | 静音 |
| `VoodooHDAVerboseLevel` | `2` | 排障；稳定后可降 1 |
| `Vectorize` / `Boost` / `MixerValues` | 上游默认 | 未改动 |

`NodesToPatch` 里上游自带的两条示例条目（`Codec 4` / `Codec 2`）已把 `Enable` 置 `0`，
避免它们在某些机器上误命中。
