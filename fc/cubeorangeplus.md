# CubePilot Cube Orange+

> 用途：Cube Orange+ 和 6C 不同的地方、怎麼確認。
> 什麼時候讀：用 Cube Orange+，或換一塊新飛控想參考時。
> 可以跳過：只用 6C 時。
> 小節：實跑紀錄（已搬到帳本 V21）｜和 6C 不同的地方｜怎麼確認

2026-10-20，在一台 Cube Orange+（USB 直接接電腦）上把整輪走完後整理。換飛控的一般清單見 [fc README](README.md)。

結論：Cube Orange+ 可以跑完「編韌體 → 燒錄 → 身分 → 參數 → 開機檔 → HITL → 飛控記錄」，三個配方（原生、原生＋記憶卡修正、範本模組）的一條龍都 PASS，原生 PX4 的盤旋和 6C 的基準幾乎一樣。和 6C 不同、要先知道的有三件：**PX4 的預設韌體沒有 `pwm_out_sim`，不能做 HITL**（配方改用加了它的 `hil` 變體）；**FC 回報的板子身分是 USB 產品碼 4184，不是 board id 1063**；**出廠的 ArduPilot bootloader 叫 `CubeOrange+-BL`**，runtime 原本認不出它是 bootloader。

驗證環境：Cube Orange+（STM32H747、32 KiB FRAM、2 GB SD 卡、IO 處理器）、USB 供電（伺服軌 0.03 V，沒有電池）；Ubuntu 24.04.5 筆電（Dynabook，18 執行緒，沒有 MATLAB、沒有即時排程權限）；PX4 v1.17.0。

## 實跑紀錄

搬到 [records/verification.md](../records/verification.md) 的 V21。

## 和 6C 不同的地方

每一項寫 Cube 怎麼樣、影響、怎麼確認；「例」是這次實際遇到的。

### 預設韌體不能做 HITL

- v1.17.0 的 `boards/cubepilot/cubeorangeplus/default.px4board` 沒有任何模擬模組：`pwm_out_sim` 沒編進去。6C 的 board 開了 `SIMULATOR_SIH`，順帶選了 `pwm_out_sim`。
- 影響：`SYS_HITL=1` 開機時 rcS 的 `pwm_out_sim start -m hil` 失敗，沒有 HIL 輸出，參數名單也沒有 `HIL_ACT_*`。
- 做法：[px4/patches/px4_cubeorangeplus_hil_variant_pwm_out_sim.patch](../px4/patches/px4_cubeorangeplus_hil_variant_pwm_out_sim.patch) 加一個 `hil.px4board`（只有 `CONFIG_MODULES_SIMULATION_PWM_OUT_SIM=y`），make 目標 `cubepilot_cubeorangeplus_hil`。PX4 的控制程式不變；多 7 KB。
- 確認：建置目錄的 `boardconfig` 有 `CONFIG_MODULES_SIMULATION_PWM_OUT_SIM=y`；FC 上 `pwm_out_sim status` 有 `Param prefix: HIL_ACT`；`ver all` 是 `Build variant: hil`。
- 例：FC 原本跑的就是使用者自己編的 `hil` 變體，所以一開始讀回時 FC 有 `HIL_ACT_*`、用預設目標編出來的參數名單卻沒有，讀回判 INCOMPLETE（17 個 `not_in_list`）。

### 板子身分是 USB 產品碼

- PX4 的 `AUTOPILOT_VERSION.board_version` = `CONFIG_CDCACM_PRODUCTID` = 0x1058 = 4184；韌體與 bootloader 的 board id 是 1063。
- 影響：原本的核對拿 board id 比，Cube 一定判身分 FAIL；而 Cube 的原生韌體和 6C 的原生韌體 PX4、NuttX hash 相同，「FC 上是哪個配方」會把 Cube 誤認成 6C 的 `00_native`。
- 做法：`px4/build_firmware.py` 記下 `embedded.board_version`；`deploy/check_params.py` 與 `deploy-test` 的配方比對都比它（舊紀錄沒有時用 board_id，6C 兩者相同）。

### ArduPilot 的 bootloader

- 進 bootloader 時 USB 名稱是 `CubePilot CubeOrange+-BL`，VID/PID 和 PX4 韌體一樣（`2dae:1058`），USB 序號不同（韌體是 `0`）。
- 影響：runtime 原本只認 `bootloader` 與 `PX4 BL`，把它當成一般韌體。重開機時是另一層保護（USB 序號對不上已記住的韌體身分）讓 owner 沒有連上去；但 owner 剛好在 FC 停在 bootloader 時才啟動，就會連上去送 MAVLink。已修：`hitl/host/serial_helpers.py` 的 `BOOTLOADER_LABEL` 認得 `-BL` 結尾，runtime 與 `deploy-test` 共用。
- 例：參數部署的每次重開，bootloader 出現約 4.8 s；燒錄時約 30 s。`px_uploader.py` 讀不到版本（`Bootloader version: unknown`），燒錄正常。

### IO 處理器、安全開關、伺服軌

- 有 px4io（`cubepilot_io-v2`，韌體在 PX4 的 ROMFS，開機時核對 CRC，必要時更新；這次 CRC `0x0458fffe` 沒變）。HITL 時 px4io 照樣啟動；`PWM_MAIN_FUNC*` 都是 0，IO 的輸出停在 disarmed 值。
- px4io 一啟動就宣告安全開關存在；`CBRK_IO_SAFETY` 預設 22027，不用按。
- 確認動力隔離：`px4io status` 的 `voltage_v` 是伺服軌電壓，這次 0.033 V（沒供電）。HITL 沒有 `battery_status`，不能拿它判斷有沒有接電池。

### 開機腳本與參數

- `rc.board_defaults` 設 `SENS_EN_THERMAL 0`（關 IMU 加熱；6C 上同值但沒有腳本設，放在 `set`）、電源模組分壓（屬 `fc_owned`）；STM32H7 的架構預設和 6C 相同。配方的 `boot` 因此是 6 個。
- `set` 是 6C 的 HITL 值（`SYS_HITL`、`HIL_ACT_FUNC1..5`、`HIL_ACT_REV`、`SDLOG_PROFILE`），不含 6C 才有的 `MAV_1_CONFIG`、`MAV_1_FLOW_CTRL`。
- `fc_owned` 多一條 `^MAN_ARM_GESTURE$`：這台的遙控器設了解鎖開關（`RC_MAP_ARM_SW=5`），PX4 每次開機把 `MAN_ARM_GESTURE` 改成 0。自動飛手用 MAVLink 指令解鎖，不受影響。
- 飛行後 PX4 會改 `CAL_ACC*_OFF`、`CAL_BARO*_OFF`（屬 `fc_owned`，核對照常 PASS）。

### 記憶卡、FRAM、記錄

- SD 卡在 SDMMC1（STM32H7、開 D-cache），和 6C 同一個 NuttX 驅動，記憶卡修正（`01_sdfix_cubeorangeplus` 起）照樣適用。
- FRAM 32 KiB，`/fs/mtd_params` 1024 blocks。
- 從 ArduPilot 換過來留下的 `param_import_fail.*`：見 [fc README](README.md)「從 ArduPilot 換過來的飛控」。使用者要求刪除，2026-10-20 已刪（備份在 cache 的 `manual/ardupilot_leftovers/`）。
- 這張卡的 `etc/logging/logger_topics.txt`（實機的慣量飛行測試清單，32 個主題）取代了 `SDLOG_PROFILE=17`：飛控記錄 7.0 MB、27 種格式（6C 是 10.9 MB），`tecs_status` 不在清單裡。沒有動它；要和 6C 的記錄逐項比，先決定要不要換掉這份清單。

### 版本類型

- 板子變體的 patch commit 在 PX4 主 repo，FC 回報的版本從 1.17.0 release（`17891583`）變成 1.17.0 dev（`17891328`）。身分核對比 hash，不受影響。

## 怎麼確認

| 要確認的事 | 指令 | 這次的結果 |
|---|---|---|
| FC 上是什麼韌體 | MAVLink Console：`ver all` | `Build variant: hil`、PX4 `c45268d0…`、NuttX `fb2fadf6…` 或 `8d3ed2a2…` |
| HIL 輸出模組 | `pwm_out_sim status` | `Param prefix: HIL_ACT`，5 路 201、202、203、204、101 |
| bootloader 的 USB 名稱 | 燒錄時 `ls /dev/serial/by-id/` | `usb-CubePilot_CubeOrange+-BL_<序號>-if00` |
| 伺服軌有沒有電 | `px4io status` 的 `voltage_v` | 0.033 V |
| 參數存放 | `mtd status`、`param status` | `/fs/mtd_params` 32 KiB；988／1979 used |
| SD 卡的記錄清單 | `ls /fs/microsd/etc/logging` | 有 `logger_topics.txt` |
