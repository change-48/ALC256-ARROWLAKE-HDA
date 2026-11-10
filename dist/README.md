# dist/ —— 可直接用的 kext（含改动）

```
VoodooHDA_BL.kext/
  Contents/Info.plist          <- 已按本仓库记录改好
  Contents/MacOS/VoodooHDA_BL  <- 未改动，来自上游 build
SHA256SUMS
```

## 出处

| 项 | 值 |
| --- | --- |
| 上游 | [CloverHackyColor/VoodooHDA](https://github.com/CloverHackyColor/VoodooHDA) 3.7.0 |
| 变体 | **BL**（把 Apple `IOAudioFamily` 编进本体，`OSBundleLibraries` 只剩 KPI + `IOPCIFamily`），因此可以被 OpenCore 在引导阶段注入 |
| 打包来源 | chris1111 的 `VoodooHDA_BL.kext`（`CFBundleName = VoodooHDA_BL`，`BuildMachineOSBuild 24G830`） |
| 本仓库改动 | **只改 `Contents/Info.plist`**，可执行文件一字节未动（哈希见 `SHA256SUMS`） |
| 许可 | BSD-2-Clause，全文见 [`../third_party/VoodooHDA-BSD-2-Clause.txt`](../third_party/VoodooHDA-BSD-2-Clause.txt) |

改动明细（与 [`../docs/02-voodoohda-pinseq.md`](../docs/02-voodoohda-pinseq.md) 对应）：

| 键 | 原值 | 现值 |
| --- | --- | --- |
| `IOPCIMatch` | `0x77288086`（该定制版已是） | 保持 |
| `IOProbeScore` | `99000` | 保持 |
| `LayoutId` | `13` | **`97`** |
| `NodesToPatch` | 2 条示例条目（`Enable: 1`，`Codec 4` / `Codec 2`） | **1 条**：`Codec 0 / Node 20 / Config 0x90170112 / Enable 1` |
| `VoodooHDAEnableVolumeChangeFix` | `false` | **`true`** |
| `VoodooHDAEnableMuteFix` | `false` | **`true`** |
| `VoodooHDAVerboseLevel` | `1` | **`2`** |

## 用法

```sh
# 1. 校验
shasum -a 256 -c SHA256SUMS      # 在 dist/ 目录下执行

# 2. 放进 EFI
cp -R VoodooHDA_BL.kext /Volumes/EFI/EFI/OC/Kexts/

# 3. config.plist -> Kernel -> Add 增加一条（见 ../config/kernel-add.plist）
#    AppleALC.kext / SimpleHDA.kext 必须 Enabled = false

# 4. 重启
```

想用自己手里的 build，而不是这里的二进制：直接

```sh
python3 ../scripts/apply-patch.py /path/to/your/VoodooHDA_BL.kext
```

效果相同，且会自动备份 `Info.plist.bak`。

## 注意

- 这套配置是**为 ALC256 + 8086:7728 这一种组合**调出来的：`LayoutId 97` 的引脚表、
  `0x14` 序号的补丁，都建立在本文记录的那份 codec 拓扑上。换机器/换 codec 需要重新来一遍
  （流程见 README 的排障一节）。
- `NodesToPatch` 里 `Codec 0` 是 codec address，不是 codec id。多 codec 的机器要看清 `cad`。
- 这是内核扩展，注入失败或被别的音频栈抢占时可能没有声音（一般不会影响开机）。
  先确认 `kmutil showloaded | grep VoodooHDA` 有输出，再看 `system_profiler SPAudioDataType`。
