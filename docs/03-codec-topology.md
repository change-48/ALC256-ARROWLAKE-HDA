# ALC256 拓扑与控件表（本机实测）

来源：`sudo vhda_msgbuf` 读取 `VoodooHDADevice` 内部消息缓冲（不受 dmesg 被 itnwm/tcp 日志冲掉的影响）。
系统 macOS 26.7.2，控制器 `8086:7728`，codec address 0。

## 编解码器

```
HDA Codec #0: Realtek ALC256
Codec ID: 0x10ec0256
    Vendor: 0x10ec   Device: 0x0256   Revision: 0x00   Stepping: 0x02
PCI Subvendor: 0x20811ee7
AFG nid=1  startNode=2  endNode=37  total=35
GPIO: 0x40000003  NumGPIO=3 NumGPO=0 NumGPI=0 GPIWake=0 GPIUnsol=1
```

## 应用 layout 97 之后的引脚

| nid | pin config | 角色 | 连接 |
| --- | --- | --- | --- |
| `0x12` | `0x90a60130` | Internal Microphone | Fixed / Internal |
| `0x14` | `0x90170111` → 补丁后 `0x90170112` | Speaker | Fixed / Internal |
| `0x19` | `0x04811040` | Line-in | Jack 1/8 / External |
| `0x1B` | `0x90170110` | Speaker | Fixed / Internal |
| `0x21` | `0x04211020` | Headphones | Jack 1/8 / External |

`0x13 / 0x18 / 0x1A / 0x1E` 保持 `0x400000f0`（未连接），解析器随后把对应控件禁用。

`0x14` 与 `0x1B` 的差别只在 seq（1 / 0）。补丁把 `0x14` 挪到 seq 2，
是因为耳机合并会占用 seq 1（见 [`02-voodoohda-pinseq.md`](02-voodoohda-pinseq.md)）。

## 音频路径（最终）

```
Playback:
  nid=27 [pin: Internal Speakers]  <- nid=3 [audio output]  DAC3   bindSeq=3
  nid=33 [pin: Headphones]         <- nid=3 [audio output]  DAC3   bindSeq=3
  nid=20 [pin: Internal Speakers]  <- nid=2 [audio output]  DAC2   bindSeq=4

Record:
  nid=8  [audio input]  <- nid=35 [audio mixer] [src: mix]
       + <- nid=25 [pin: Line In]            [src: line]
       + <- nid=29 [beep widget]
       + <- nid=18 [pin: Internal Microphone][src: monitor]
```

- 输出被拆成两颗 DAC：DAC3 喂 `0x1B` + 耳机，DAC2 喂 `0x14` → 设备因此报 4 声道；
- 输入是 `0x12`(内置麦) + `0x19`(外接) 合并成一个关联，所以只显示为 `Line In`。

## 控件（决定音量能不能调）

```
Master Volume (OSS: vol)
   +- control  0 (nid   2 out): -65/+0dB (88 steps)
   +- control  7 (nid  20 out): vol, pcm mute
   +- control 11 (nid  27 out): vol, pcm mute
   +- control 13 (nid  33 out): vol, pcm mute

PCM Volume (OSS: pcm)
   +- control  0 (nid   2 out): -65/+0dB (88 steps)
   +- control  1 (nid   3 out): -65/+0dB (88 steps)
```

结论：pin 只有 mute 能力（`0x14/0x1B/0x21` 都没有增益级），真正的增益在两颗 DAC 上；
而 `Master Volume` 只挂 DAC2，`PCM Volume` 才同时挂 DAC2 + DAC3。

## Stream 能力

```
Playback:  PCM cap 0x000e0060  -> 16/20/24 bit, 44.1/48 kHz
Record:    PCM cap 0x000e0560  -> 16/20/24 bit, 44.1/48/96/192 kHz
DAC: 3 2      ADC: 8
```

采样率上限 48 kHz（这颗 codec 的常规能力，非本机限制）。
