# 驗證紀錄帳本

> 用途：每一次驗證的做法、數字、範圍與更正。README 的「驗證矩陣」只寫結果，細節在這裡。
> 什麼時候讀：要引用過去的驗證或數字、要和以前的結果比、要確認某個結論的範圍時。
> 可以跳過：只想知道哪一段在哪個平台驗證過時（看 README 的驗證矩陣）。
> 2026-10-26 從 README「驗證紀錄（2026-10-18，Ubuntu 24.04）」的表（V01–V19）、[platforms/macos.md](../platforms/macos.md) 與 [fc/cubeorangeplus.md](../fc/cubeorangeplus.md) 的「實跑紀錄」（V20、V21）搬來，原文不改，只改了連結。V01–V19 沒寫日期的，是那張表的表頭：2026-10-18、Ubuntu 24.04。當時沒寫的範圍、失效條件與證據位置，沒有補推測。
> 新的紀錄加在最後，編號接下去；推翻舊結論時照 [AGENTS](../AGENTS.md) E3，在原處改正並註明更正。

| 編號 | 項目 |
|---|---|
| V01 | 模型 release `skysurfer-6d1cf7a3…`（改名後；改名前 `f53eee94…`） |
| V02 | 離線測試 |
| V03 | 600 s 負載（不開視窗） |
| V04 | SITL |
| V05 | ULog 與 MATLAB |
| V06 | HITL（實體 FC） |
| V07 | 第 3 段一條龍 |
| V08 | 範本 `02_template`（HITL，2026-10-18） |
| V09 | 3.1 手動 HITL（2026-10-18，FC 是 `02_template`） |
| V10 | 交接時的 FC |
| V11 | 改名 `px4-llm-sim2hitl`（2026-10-18） |
| V12 | 風（2026-10-19） |
| V13 | 有風實機 HITL（2026-10-19；FC 不是 `01_sdfix`，見本列最後的更正） |
| V14 | 可攜產碼（2026-10-20） |
| V15 | HITL 換模式（2026-10-20，FC 是 `01_sdfix`） |
| V16 | 第二台 Ubuntu、沒有 MATLAB（2026-10-20） |
| V17 | 換飛控：Cube Orange+（2026-10-20，同一台筆電） |
| V18 | 乾淨目錄試跑 |
| V19 | 收尾 |
| V20 | macOS（Apple M4、macOS 27.0.1）：從乾淨的原始碼樹到 SITL 多實例（2026-10-20） |
| V21 | Cube Orange+ 整輪的逐步結果（2026-10-20） |

## V01 模型 release `skysurfer-6d1cf7a3…`（改名後；改名前 `f53eee94…`）

四道檢查 PASS；核心與 C 真值對參考資料的誤差和改名前一位不差；對 macOS 錄的參考資料，除了靜止時沒有定義的攻角／側滑角，差 ≤ 6.2e-15

## V02 離線測試

14 個檔全部 OK（2026-10-18，改名後）。`test_runbridge_fake` 的恢復測試原本在機器很忙時會誤判（等狀態的輪詢趕不上假飛控 2.3 s 的重開），改成整個恢復期間都送 QGC 流量後，28 核全滿也 PASS

## V03 600 s 負載（不開視窗）

PASS；有即時權限時最慢晚到 0.47 ms

## V04 SITL

編譯 PASS；參考情境 `stabilized_steps` 的指標和 macOS 紀錄相同；速度：1000 次（每次模擬 60 s）實測 140.8 s，加大批次約 55 s；範本 `guidance_template` PASS

## V05 ULog 與 MATLAB

SITL 與 HITL 的 ULog 都能用 MATLAB `ulogreader` 畫（`analysis/matlab/ulog_overview_plot.m`，不需要 Java），也能轉 CSV（`analysis/ulog_export.py`）

## V06 HITL（實體 FC）

00_native 基準 `hitl-run` PASS（2026-10-17 UTC）：盤旋 60 s、2.78 圈；23,039 步 0 次晚到、最慢 0.79 ms；USB 寫入最慢 0.26 ms；FC 量到感測器 250.009 Hz

## V07 第 3 段一條龍

`deploy/01_sdfix`（原生＋記憶卡修正）用 `deploy-test` 燒錄並跑完：FC 回報 NuttX `8d3ed2a2…`（可預期的那個）；寫參數 0 個；`hitl-run` 七部分全 PASS，盤旋 60.13 s、2.78 圈，23,104 步 0 次晚到、最慢 0.19 ms；飛控記錄（10.9 MB）下載兩次相同、嚴格解析 PASS

## V08 範本 `02_template`（HITL，2026-10-18）

一條龍全 PASS（重編、燒錄、身分、參數、開機檔）；**FC 接受模組在韌體內自己發的 OFFBOARD 訊號**。動作改成進 OFFBOARD 15 s 後轉 30°、35 s 後爬 10 m、共 60 s，盤旋高度判定改以開始盤旋的高度 ±15 m 之後：飛行 PASS；航跡角 +29.1°（不超越、15.2 s 安定）、最大傾角 14°；**高度衝過頭 33%**（SITL 0%）、OFFBOARD 結束前未回到 ±0.5 m，判定 FAIL。同時空速從 21 衝到 28 m/s；可能是 TECS 加能量時油門給太多（`FW_THR_TRIM=0.6` 對模型的約 0.115），見「已知問題」，待查

## V09 3.1 手動 HITL（2026-10-18，FC 是 `02_template`）

QGC 只連 UDP；QGC 的模式選單切不到固定翼的 Offboard，改用 `./runbridge takeoff --altitude 100 --after template_offboard`。結果和自動測試幾乎相同：航跡角 +29.0°（15.4 s 安定）、最大傾角 14.2°、高度衝過頭 31% → 範本判定 FAIL（同上，模型與參數不吻合）；0 次晚到；停模型、`recover` 後未解鎖、`SYS_HITL=1`、無待恢復

## V10 交接時的 FC

2026-10-18 07:22 UTC 用 `deploy-test --flash` 從 `02_template` 刷回 `01_sdfix`：全 PASS（盤旋 60.0 s、2.79 圈、0 次晚到），開機檔已移除；紀錄見 [deploy/01_sdfix](../deploy/01_sdfix/README.md)

## V11 改名 `px4-llm-sim2hitl`（2026-10-18）

套件不再借用飛機名：資料夾全名、環境變數 `SIM2HITL_*`、PX4 模組 `plant_sim`／`guidance_template`、plant 函式字頭 `plant_`；紀錄不寫本機路徑。MATLAB 重新產碼只差時間戳記與暫存路徑；新模型版本四道檢查 PASS；離線測試全過；SITL 兩個情境和改名前相同（範本 PASS）；`02_template` 重編後 NuttX `8d3ed2a2…` 不變；FC（01）`hitl-run` 七部分全 PASS：盤旋 60.07 s、2.77 圈、0 次晚到、最慢 0.20 ms，記錄下載兩次相同、嚴格解析 PASS

## V12 風（2026-10-19）

模型的風開成外部接口（定常風，或風切＋陣風＋亂流；預設離地後才吹），SITL 與 HITL 同一個 `wind` 格式（`plant/wind.py`），說明在 [plant README](../plant/README.md)「風」、AI 對使用者的說明清單在 AGENTS。原始 slx：Dryden 亂流取消註解（原本因地面空速 0 除以零而關掉）、空速輸入加 5 m/s 下限、雜訊間隔 0.1 s → 4 ms。無風時結果和之前逐位元相同；三組 Simulink 對照（含全部風都開）原始模型與核心副本逐位元相同；四道檢查 PASS（`skysurfer-1c2b65fe…`，HIL 函式庫的 wind case 和 Simulink 一致）；離線測試全過；SITL 參考情境與範本和之前相同，`wind_steady`、`wind_low_altitude` 照預期

## V13 有風實機 HITL（2026-10-19；FC 不是 `01_sdfix`，見本列最後的更正）

場景 `hitl/scenarios/wind_steady_5.json`（地面開始＋定常風 5 m/s 從北方吹來，離地 5 m 後 5 s 漸進）；手動流程：`recover` → `model-start --scenario` → `takeoff --altitude 100` → 盤旋 60 s → `model-stop` → `recover --hil-force-disarm`。流程：盤旋 60 s、1.87 圈、0 次晚到（最慢 1.13 ms）、序列埠 0 錯；恢復後未解鎖、`SYS_HITL=1`、無待恢復；飛控記錄（第 53 筆，比飛行前最新的 52 新）下載兩次相同、嚴格解析 PASS。風：PX4 的 EKF（約每秒一筆）在爬升中約 20 s 估到 4.7 m/s，100 m 以上平均 5.01 m/s 從 0°（真值 5.00 m/s 從 0°）；空速計選擇器自己的風估計約 40 s 後到 5 m/s 附近。和前一次無風（2026-10-18，01）並排：圈數 1.87／2.77、半徑 78／83 m、高度 98–102／100–113 m、盤旋空速平均 17.3／24.3 m/s（有風這次後段約 15.5）、飛控記錄在解鎖瞬間有一段 24 ms 空缺／無；只列差異，沒有事先講好的判定。**更正（2026-10-22）**：本列原本寫 FC 是 `01_sdfix`。這次的飛控記錄顯示 FC 跑的是另一個專案的空投韌體（PX4 git `3f3644f3a0`、有 `DROP_*` 參數、`FW_THR_TRIM` 0.115；`01_sdfix` 是 `d6f12ad1c4`、0.6）；上面的手動流程沒有核對 FC 身分這一步。風的估測（EKF 對真值）不受影響；和無風那次並排的差距混了韌體與油門配平的不同，不能當成風造成的

## V14 可攜產碼（2026-10-20）

產碼關掉指令集擴充（MATLAB 對 Intel 預設用 SSE2，arm64 編不過；每一格其實就是一般的雙精度運算）。Simulink 參考結果逐位元相同；新 release `skysurfer-75a7ddff…` 四道檢查 PASS，核心與 C 真值對參考資料的每個誤差都和上一版一位不差；配平與 20 s 放手每一位相同；SITL 參考情境與範本和之前相同。HITL（`01_sdfix`，沒有即時權限）`hitl-run`：盤旋 60.1 s、2.78 圈、半徑 82 m，身分、參數前後、飛控紀錄、資料 PASS；時序 FAIL（23,297 步裡 11 步晚到，最慢 16 ms；當時 P 核心被別的計算佔滿）

## V15 HITL 換模式（2026-10-20，FC 是 `01_sdfix`）

驗證「飛起來以後 PX4 換模式，飛手不放手」：進 Hold 後從 QGC 那條路依序要求 Stabilized、Hold、Position、Hold，各約 30 s。飛控紀錄：模式照要求換，期間沒有 failsafe、沒有遙控斷訊、沒有 RTL；飛手在 Stabilized 平飛定高，其他模式送中立搖桿。紀錄是這趟的、沒有改參數、恢復完成

## V16 第二台 Ubuntu、沒有 MATLAB（2026-10-20）

新裝的 Ubuntu 24.04.5 筆電（18 執行緒，沒有 MATLAB、沒有即時排程權限）。uv＋venv；PX4 原樹被別的工作改過，另複製一份乾淨的 v1.17.0；PX4 的 Python 另建 venv 放 PATH。`update-model` 原本因找不到 MATLAB 停下（生成碼要 `rtw_solver.h`、`rtw_continuous.h`），改用專案的最小標頭檔（`plant/core/rtw/`）後四道檢查 PASS（`skysurfer-3cbb58ff…`），60 秒節拍 0 次晚到；對錄製參考資料最大誤差 6.2e-15（靜止時的攻角除外），和用 MATLAB 標頭檔的版本相同。SITL 參考情境的指標和紀錄差 ≤ 1 步（4 ms）／0.005°，範本 PASS；離線測試 15 個檔全過

## V17 換飛控：Cube Orange+（2026-10-20，同一台筆電）

三個配方（`*_cubeorangeplus`）一條龍全 PASS，交接時 FC 上是 `01_sdfix_cubeorangeplus`。原生：盤旋 60.16 s、2.78 圈、半徑 82.2 m、高度 99.8–113.2 m（6C 基準 60.06 s、2.78 圈、82.3 m、100.0–113.2 m），23,079 步 0 次晚到、最慢 0.35 ms（沒有即時權限、機器閒置）。範本：FC 接受模組自己發的 OFFBOARD；航向 +29.15°、高度 +9.39 m、超越 18 %，判定 PASS，但這張 SD 卡的記錄清單沒有 `tecs_status`，高度基準是實測高度（6C 用 TECS 目標），不能直接比。和 6C 不同而要改的：預設韌體沒有 `pwm_out_sim`（改用 `hil` 板子變體 patch）、FC 回報的 board_version 是 USB 產品碼 4184（不是 board id 1063）、出廠 ArduPilot bootloader 的 USB 名稱 `CubeOrange+-BL` 原本認不出來、用過的 FC 有 16 個殘留參數（以一次性配方改回）。細節見 [fc/cubeorangeplus.md](../fc/cubeorangeplus.md)
逐步的結果見 V21。

## V18 乾淨目錄試跑

2026-10-18（改名後）：從 git 拉到新資料夾、獨立快取、不連 MATLAB：`update-model` 建出**相同的 build-id** `skysurfer-6d1cf7a3…`、四道檢查 PASS；離線測試全過；**從零重編 `01_sdfix`**：PX4 `d6f12ad1…`、NuttX `8d3ed2a2…`、韌體大小都和 FC 上的相同（`.px4` 含建置時間，所以檔案 SHA 不同）；紀錄裡沒有本機路徑

## V19 收尾

核心精神已寫進本 README（「這套專案的精神」）；乾淨目錄試跑完成；上 GitHub：https://github.com/rhyne1012/px4-llm-sim2hitl（2026-10-18）

## V20 macOS（Apple M4、macOS 27.0.1）：從乾淨的原始碼樹到 SITL 多實例（2026-10-20）

原本在 [platforms/macos.md](../platforms/macos.md)「實跑紀錄」；驗證機見那份文件的開頭。

從乾淨的原始碼樹到 SITL 多實例，只有「產碼」這一步必須改來源，其餘都是環境設定。

| 步驟 | 做法 | 結果 |
| --- | --- | --- |
| 原始碼樹 | 另下載一份鎖定版本（含子模組，2.7 GB），放在外接 APFS 磁碟 | 乾淨度核對 PASS；原本那份是 git worktree，子模組狀態壞了，不能用 |
| 工具 | Homebrew 裝 uv、cmake、ninja、ccache | cmake 已是 4.4；PX4 v1.17 照樣能設定，只有棄用警告 |
| 專案 Python | uv 建 venv，放在 `~/Library/Application Support` | 15 秒；Python 3.12、arm64 |
| PX4 的 Python | 另建一個 venv 放在原始碼樹外，用 `PYTHON_EXECUTABLE` 指給 PX4 | 1 分 40 秒裝完 PX4 的需求套件 |
| 產碼 | 關掉指令集擴充，用 `matlab -batch` 重新產碼（2026-10-20 起套件的 `build_core.m` 預設就是這樣） | 0 個 SSE2 指令；Simulink 參考結果和 Linux 上產的逐位元相同 |
| 模型發布 | Apple clang 編譯，跑四道檢查 | 全部 PASS；60 秒節拍 0 次晚到；對參考資料最大誤差 2.2e-16 |
| 配平 | 配平工具（不需要 PX4） | 15、20、25 m/s 和紀錄的每一位都相同 |
| PX4 SITL 編譯 | ninja 平行編譯 | 39 秒（1113 步）；`-Werror` 沒有擋；編完原始碼樹仍乾淨 |
| 連結核對 | `otool -L` 看 PX4 執行檔 | 載入的是建置暫存區的函式庫，不是發布的那份（後來修好：install name 改成 `@rpath`，建置後自動核對） |
| 參考情境 | 60 秒的姿態階躍情境 | 指標和紀錄相同；0.31 秒跑完（194 倍即時） |
| 範本情境 | 70 秒的 OFFBOARD 範本 | PASS；0.40 秒（174 倍） |
| 多實例 | 25 個與 100 個同時跑 | 第一批 25 個：3 個重啟、1 個卡住到逾時；之後兩批 25 個與一批 100 個全過、0 次重啟（100 個 26.6 秒，265 倍）。之後偶爾仍有 1–2 個卡在啟動指令；執行器改成整組重啟、保留失敗的 log 後都能跑完 |

## V21 Cube Orange+ 整輪的逐步結果（2026-10-20）

原本在 [fc/cubeorangeplus.md](../fc/cubeorangeplus.md)「實跑紀錄」；驗證環境見那份文件的開頭。

| 步驟 | 結果 |
|---|---|
| FC 原本的狀態 | 本機自建的 PX4 v1.17.0 `hil` 變體（`ver all`：`Build uri: localhost`、`Build variant: hil`，2026-07-26）；`SYS_HITL=1`、機架 2100，但機身改成 3 個舵面（`CA_SV_CS_COUNT=3`，單副翼＋升降舵＋方向舵）、HIL 通道 201／202／203／101；SD 卡有實機用的記錄清單與 9/27–10/15 的飛行記錄。原參數存在 [deploy/00_native_cubeorangeplus/fc_params_20261020.params](../deploy/00_native_cubeorangeplus/fc_params_20261020.params) |
| 預設韌體（`cubepilot_cubeorangeplus_default`） | 編譯 PASS（98.10 %），但沒有 `pwm_out_sim`、參數名單沒有 `HIL_ACT_*`：不能用 |
| `hil` 變體（[patch](../px4/patches/px4_cubeorangeplus_hil_variant_pwm_out_sim.patch)） | 三個配方編譯 PASS：原生 98.46 %、＋記憶卡修正 98.46 %、＋範本模組 98.58 %（上限 1,966,080 bytes）；參數 1,979 個（＝預設 1,962＋17 個 `HIL_ACT_*`）；PX4 hash `c45268d056`（patch commit，可重現）、NuttX 原生 `fb2fadf6…`／修正版 `8d3ed2a2…`；每次約 100–180 s |
| 燒錄 | `px_uploader.py` 經出廠的 ArduPilot bootloader，第一次就成功，約 30 s；序列埠一直是 `/dev/ttyACM0` |
| 身分 | 修正後 PASS：FC 回報 board_version 4184、PX4 與 NuttX hash 都等於配方 |
| 接手 | FC 上 16 個值和配方不同（機身 5 個、HIL 通道與記錄 4 個、遙控模式槽與 EKF 等 7 個）；第一次部署因 `MAN_ARM_GESTURE` 被 PX4 改回 0 而 FAIL、自動回復；查明原因後第二次 PASS（15 個寫入，重開後讀回正確） |
| 原生一條龍（`00_native_cubeorangeplus`） | PASS：盤旋 60.16 s、2.78 圈、半徑 82.2 m、高度 99.8–113.2 m；23,079 步 0 次晚到，最慢 0.35 ms；序列埠 0 錯、最慢寫入 0.18 ms；飛控記錄第 23 筆（飛行前最新 22）7.0 MB，下載兩次相同、嚴格解析 PASS；恢復後未解鎖、`SYS_HITL=1` |
| 範本一條龍（`02_template_cubeorangeplus`） | PASS（燒錄、身分、參數、開機檔、`hitl-run` 八部分）：FC 接受模組在韌體內自己發的 OFFBOARD 訊號；OFFBOARD 61.0 s，航向 +29.15°（誤差 −0.85°、不超越、15.1 s 安定）、高度 +9.39 m（誤差 −0.61 m、超越 18 %、24.9 s 安定）、最大傾角 14.0°、空速 17.2–29.3 m/s，範本判定 PASS；盤旋 60.02 s、1.98 圈；41,069 步 0 次晚到、最慢 1.24 ms；飛控記錄第 24 筆 12.6 MB，下載兩次相同、嚴格解析 PASS。**判定的高度基準和 6C 不同**：這張 SD 卡的記錄清單沒有 `tecs_status`，判定程式改用階躍前的實測高度（6C 與 SITL 用 TECS 的高度目標），所以不能拿來和 6C 的「超越 33 %、FAIL」直接比；2026-10-20 起報告的 `altitude_base_source` 會寫明 |
| 原生＋修正一條龍（`01_sdfix_cubeorangeplus`，交接時 FC 上是它） | PASS：先刪掉 02 的開機檔再燒錄；盤旋 60.16 s、2.79 圈、半徑 82.1 m、高度 99.9–113.3 m；23,094 步 0 次晚到、最慢 0.29 ms；飛控記錄第 25 筆 7.0 MB，下載兩次相同、嚴格解析 PASS；結束後未解鎖、`SYS_HITL=1`、沒有待恢復 |

和 6C 的原生基準（`hitl/flight_test.json` 的 baseline，2026-10-17）並排：盤旋 60.16／60.06 s、圈數 2.78／2.78、半徑 82.2／82.3 m、最低 99.8／100.0 m、最高 113.2／113.2 m、最慢晚到 0.35／0.79 ms。兩邊 PX4 控制程式與模型相同，差的是 FC 的硬體與 EKF 的估測；沒有事先講好的判定，只列差異。
