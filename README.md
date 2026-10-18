# px4-llm-sim2hitl

**繁體中文** | [English](README.en.md)

（英文版是翻譯；兩者不一致時以本中文版為準）

飛控開發套件：MATLAB/Simulink 飛機模型 → 轉成 C → SITL（精簡 PX4）→ 客製 PX4 韌體 → 實體飛控（Pixhawk）HITL。用 AI 開發時，AI 的工作規則在 [AGENTS.md](AGENTS.md)。

![流程總覽：需求與規格 → SITL 電腦模擬 → HITL 實體飛控；人選下一步，AI 做技術](images/overview.svg)

**範例飛機是 SkySurfer**（固定翼）：`model/`、`hitl/aircraft/skysurfer/`、模型版本名 `skysurfer-…` 與 `SkySurfer_Core` 這些是飛機本身。套件叫 `px4-llm-sim2hitl`：資料夾用全名（`~/.cache/px4-llm-sim2hitl`、`~/.local/share/px4-llm-sim2hitl/venv`、`~/.config/px4-llm-sim2hitl`），環境變數用短名 `SIM2HITL_*`（環境變數不能有減號）。換成自己的飛機見第 1.1 段。

> 狀態：從舊的 macOS 專案搬到 Ubuntu 已完成，整套流程跑通（見最後一節）。

## 這套專案的精神

**這不是一套自動化工具，也不應該變成一套想包辦所有開發情境的自動化；它是讓你的 AI 一開始就懂這個流程的交接。** 從飛機模型、PX4 原始碼、SITL、編譯燒錄到實體飛控，這條路怎麼走、哪裡有坑、什麼已經驗證過、怎樣才算對，都寫在文件（這份 README、[AGENTS.md](AGENTS.md)、各資料夾的 README）和現成的檢查裡。AI 讀完就接得上，不必每次從頭摸索整個流程，可以把時間和 token 花在真正要做的事：幫你除錯、幫你開發。

打個比方：AI 每開一次新對話，都像第一天上班的新同事。這包是前人留下的交接：系統怎麼運作、哪裡有坑、哪些已經驗證過、做事的規矩，還有一條實際走通過的基本路線（模型 → SITL → 燒錄 → HITL）。交接不會替他把工作做完，也不會列出他將來遇到的每一種狀況；它讓他第一天就能把心思放在你的問題上，遇到新狀況也知道從哪裡下手。處理完的新經驗和跟你談定的規則寫回交接，下一個新同事就更快上手。

- **先有理解，才有工具**：指令和腳本只是把已經想通的步驟固定下來。文件寫的是「為什麼這樣做、坑在哪裡」，例如記憶卡讀取的錯誤、地面模型不會讓飛機轉動、風什麼時候開始吹。這樣 AI 遇到問題才知道去哪裡查，也不會為了讓事情成功就繞過安全檢查硬做。
- **目的**：把這包交給別人，讓他和他的 AI 能從改飛機模型、開發飛控，一路做到編譯、燒錄與 HITL。
- **簡單、輕量、同一份來源**：每件事只放一個地方；能沿用現有程式與檢查就沿用；不為了可能用不到的情況預先加東西。
- **AI 講白話**：技術細節由 AI 查、AI 處理；只有目標、選擇與成功條件問人。
- **第 1 段最重要**：AI 先讀鎖定版本的 PX4 原始碼，把可行的接法用白話攤開和人討論，由人選；再建議先做「最小打通」，讓整條路先通、記錄下來，之後的修改交給自動化。
- **第 3 段一條龍**：編譯 → 燒錄 → 身分核對 → 參數 → 開機檔 → HITL → 飛控記錄，一個指令跑完；開始前先告訴人 FC 上現在是什麼，然後一律重新燒錄（只改外部模組時，FC 回報的版本編號可能不變，分不出新舊）。
- **自動化跟著開發慢慢長出來**：工具是理解的副產品。同一件事做了兩三次，AI 就建議把它變成專案裡的指令或腳本，由人決定；越用越省 token。
- **環境不寫死、驗收標準寫死**：路徑、編譯器、MATLAB、PX4 原始碼樹自動找、可指定，換平台時請 AI 查官方文件；量尺（版本鎖、檢查容差、4 ms、負載門檻）不隨環境改。
- **不分權限等級**：每段結束時問「下一步 1／2／3」，段內不逐項詢問；但 runtime 的安全檢查（FC 身分、未解鎖、讀回、恢復）不可繞過，見 AGENTS 第 3 節。
- **提醒，不擋**：非預設的飛行參數照跑並記錄；看起來不對的地方告訴人，由人決定。
- **SITL 與 HITL 用同一把尺**：同一份情境、同一支判定程式、同一種記錄（ULog）；兩邊的差異本身就是要找的資訊。

## 流程

1. **需求與規格**：先談清楚要做什麼、怎樣算成功。
   - 1.1 飛機模型與配平（換飛機或改模型時）
   - 1.2 算法、部署與驗收
2. **SITL（電腦模擬）**：反覆模擬，結果存成 `trace.csv`＋ULog（MATLAB 可直接讀）。
3. **HITL（自動編譯、燒錄、測試）**
   - 3.1 手動 HITL（`./runbridge`＋QGC）
   - 3.2 出場檢查：QGC 關掉 HITL 後確認舵面有輸出（尚未完成）

## 環境準備（第一次）

只在 **Ubuntu 24.04 x86-64** 驗證過。下面每一項都寫了「為什麼要」與「驗證機（Ubuntu）的做法」；做法只是例子，換平台或版本時，**請 AI 先查該項的官方文件**確認正確做法再裝。

| 項目 | 為什麼要 | Ubuntu 24.04 的做法（例子） | 怎麼確認 |
|---|---|---|---|
| Python 環境 | runtime、測試、SITL、分析 | 安裝 [uv](https://docs.astral.sh/uv/)，再 `./runbridge --setup`（venv 在 `~/.local/share/px4-llm-sim2hitl/venv`） | `./runbridge --check-python` |
| MATLAB | 只有改飛機模型（第 1.1 段產碼）才需要：R2026b＋Simulink＋Simulink Coder＋Embedded Coder＋Aerospace Blockset。不需要 Java | MathWorks 安裝程式；建議接上 MATLAB MCP，讓 AI 能直接操作 | `matlab` 在 PATH，或設 `SIM2HITL_MATLAB_ROOT` |
| C 編譯器 | plant 與 HIL 函式庫 | 系統內建 gcc（`CC` 可指定別的） | `cc --version` |
| PX4 原始碼與工具鏈 | SITL 與編韌體；版本鎖在 [px4/px4_lock.json](px4/px4_lock.json) | 下載鎖定的 tag 到專案外，`python3 px4/check_px4_tree.py --path <樹> --remember`；工具鏈用 PX4 官方腳本 `bash <樹>/Tools/setup/ubuntu.sh --no-sim-tools`（不裝 Gazebo；會用 sudo）。官方說明：PX4 文件 “Ubuntu Development Environment” | `python3 px4/check_px4_tree.py` 為 PASS |
| **即時排程權限** | 4 ms 迴圈的 worker 執行緒要用即時排程（Linux：SCHED_FIFO，優先權 2）。沒有權限也能跑，但時間餘裕變小：驗證機 600 s 負載最慢晚到 3.7 ms（門檻 4 ms），有權限時 0.47 ms | 桌面程式由 systemd 使用者服務啟動，`/etc/security/limits.d` 管不到；改用 systemd，兩個檔都要：`/etc/systemd/system/user@<UID>.service.d/rtprio.conf` 寫入 `[Service]` 與 `LimitRTPRIO=10`（使用者管理程式本身的上限），以及 `/etc/systemd/user.conf.d/rtprio.conf` 寫入 `[Manager]` 與 `DefaultLimitRTPRIO=10`（它啟動桌面程式時套用的值；只設第一個，實測重開機後桌面程式仍是 0），`sudo systemctl daemon-reload`，再重新登入。暫時只給一個程序：`sudo prlimit --pid <PID> --rtprio=10:10`。官方說明：systemd.exec(5) 的 `LimitRTPRIO=`、sched(7) | `ulimit -r` ≥ 2；`./runbridge status` 的 `scheduler.time_constraint_result` 為 0 |
| 序列埠 | 連 Pixhawk（USB CDC-ACM） | 使用者加入 `dialout` 群組；停用 ModemManager（它會試探新插上的序列埠）：`sudo systemctl disable --now ModemManager` | `ls -l /dev/ttyACM*`、`groups` |
| QGC | 人看飛控、手動操作（3.1） | 官方 GitHub 發布的 AppImage（驗證機：v5.1.5，`~/Applications/`，核對官方公布的 SHA-256）；系統套件照 QGC 官方 Linux 說明（驗證機補裝 `libfuse2t64 gstreamer1.0-plugins-bad gstreamer1.0-libav libxcb-cursor0`）。**關掉 USB 自動連線**，只用 UDP 14550 連 runtime，否則會和 owner 搶飛控序列埠：設定檔 `~/.config/QGroundControl/QGroundControl.ini` 的 `[AutoConnect]` 把 `autoConnectPixhawk`、`autoConnectSiKRadio`、`autoConnectRTKGPS`、`autoConnectLibrePilot`、`autoConnectZeroConf` 設 `false`、`autoConnectUDP=true`（QGC 第一次啟動建好設定檔、關閉後再改；或在 QGC 的 Application Settings → Comm Links 取消勾選） | QGC 開著時 `lsof -p <QGC PID>` 只見 UDP 14550、不見 `/dev/ttyACM*` |

## 常用指令

```sh
./runbridge --help                    # 所有動作
./runbridge update-model --generate   # 第一段：MATLAB 產碼 → model/generated（要 MATLAB）
./runbridge update-model              # 第二段：編譯、四道檢查、發布模型 release（不需要 MATLAB 連線）
./runbridge bridge                    # 開 owner（持有模型與序列埠）；QGC 用 UDP 連
./runbridge status                    # owner 狀態
./runbridge takeoff --altitude 100 --after template_offboard   # 3.1：模型在地面運行時自動起飛 → Hold → OFFBOARD（範本，FC 要是 02_template）→ Hold（QGC 的選單切不到固定翼的 Offboard）
./runbridge deploy-test --release deploy/<配方>           # 第 3 段：只看計畫（FC 上現在是什麼、會做什麼）
./runbridge deploy-test --release deploy/<配方> --flash   # 平常用這個：必要時編韌體 → 燒錄 → 參數 → 開機檔 → hitl-run
./runbridge deploy-test --release deploy/<配方> --reuse   # 只在人明確要求時：沿用 FC 上的韌體，參數 → 開機檔 → hitl-run
```

## 已知問題

- **模型與 PX4 參數不吻合（空速偏高）**：PX4 的 `FW_THR_TRIM=0.6`，這個飛機模型在 15 m/s 平飛只需要約 0.115 的油門。結果是原生盤旋與 SITL 的空速都在 20–30 m/s（目標 15 m/s），HITL 中 TECS 要爬高時空速衝高、高度衝過頭（範本的高度判定因此 FAIL）。照 [AGENTS](AGENTS.md) 的原則先查模型（推力、阻力、重量），再決定模型要修，還是這架飛機的 PX4 參數本來就要配合實機。
- **3.2 出場檢查還沒做**：`deploy/00_native` 的基準參數沒有指定實體舵機輸出（`PWM_MAIN_FUNC*`、`PWM_AUX_FUNC*` 全為 0）、`GPS_1_CONFIG=0`、空速計驅動未開；關掉 HITL 不會有任何輸出。需要實機的接線與參數。
- **一般使用者的即時權限**：見「環境準備」的即時排程權限；沒有時能跑，但時間餘裕小。

## 驗證紀錄（2026-10-18，Ubuntu 24.04）

| 項目 | 結果 |
|---|---|
| 模型 release `skysurfer-6d1cf7a3…`（改名後；改名前 `f53eee94…`） | 四道檢查 PASS；核心與 C 真值對參考資料的誤差和改名前一位不差；對 macOS 錄的參考資料，除了靜止時沒有定義的攻角／側滑角，差 ≤ 6.2e-15 |
| 離線測試 | 14 個檔全部 OK（2026-10-18，改名後）。`test_runbridge_fake` 的恢復測試原本在機器很忙時會誤判（等狀態的輪詢趕不上假飛控 2.3 s 的重開），改成整個恢復期間都送 QGC 流量後，28 核全滿也 PASS |
| 600 s 負載（不開視窗） | PASS；有即時權限時最慢晚到 0.47 ms |
| SITL | 編譯 PASS；參考情境 `stabilized_steps` 的指標和 macOS 紀錄相同；速度：1000 次（每次模擬 60 s）實測 140.8 s，加大批次約 55 s；範本 `guidance_template` PASS |
| ULog 與 MATLAB | SITL 與 HITL 的 ULog 都能用 MATLAB `ulogreader` 畫（`analysis/matlab/ulog_overview_plot.m`，不需要 Java），也能轉 CSV（`analysis/ulog_export.py`） |
| HITL（實體 FC） | 00_native 基準 `hitl-run` PASS（2026-10-17 UTC）：盤旋 60 s、2.78 圈；23,039 步 0 次晚到、最慢 0.79 ms；USB 寫入最慢 0.26 ms；FC 量到感測器 250.009 Hz |
| 第 3 段一條龍 | `deploy/01_sdfix`（原生＋記憶卡修正）用 `deploy-test` 燒錄並跑完：FC 回報 NuttX `8d3ed2a2…`（可預期的那個）；寫參數 0 個；`hitl-run` 七部分全 PASS，盤旋 60.13 s、2.78 圈，23,104 步 0 次晚到、最慢 0.19 ms；飛控記錄（10.9 MB）下載兩次相同、嚴格解析 PASS |
| 範本 `02_template`（HITL，2026-10-18） | 一條龍全 PASS（重編、燒錄、身分、參數、開機檔）；**FC 接受模組在韌體內自己發的 OFFBOARD 訊號**。動作改成進 OFFBOARD 15 s 後轉 30°、35 s 後爬 10 m、共 60 s，盤旋高度判定改以開始盤旋的高度 ±15 m 之後：飛行 PASS；航向 +29.1°（不超越、15.2 s 安定）、最大傾角 14°；**高度衝過頭 33%**（SITL 0%）、OFFBOARD 結束前未回到 ±0.5 m，判定 FAIL。同時空速從 21 衝到 28 m/s：TECS 加能量時油門過多（`FW_THR_TRIM=0.6` 對模型的約 0.115），屬於模型與 PX4 參數不吻合，待查 |
| 3.1 手動 HITL（2026-10-18，FC 是 `02_template`） | QGC 只連 UDP；QGC 的模式選單切不到固定翼的 Offboard，改用 `./runbridge takeoff --altitude 100 --after template_offboard`。結果和自動測試幾乎相同：航向 +29.0°（15.4 s 安定）、最大傾角 14.2°、高度衝過頭 31% → 範本判定 FAIL（同上，模型與參數不吻合）；0 次晚到；停模型、`recover` 後未解鎖、`SYS_HITL=1`、無待恢復 |
| 交接時的 FC | 2026-10-18 07:22 UTC 用 `deploy-test --flash` 從 `02_template` 刷回 `01_sdfix`：全 PASS（盤旋 60.0 s、2.79 圈、0 次晚到），開機檔已移除；紀錄見 [deploy/01_sdfix](deploy/01_sdfix/README.md) |
| 改名 `px4-llm-sim2hitl`（2026-10-18） | 套件不再借用飛機名：資料夾全名、環境變數 `SIM2HITL_*`、PX4 模組 `plant_sim`／`guidance_template`、plant 函式字頭 `plant_`；紀錄不寫本機路徑。MATLAB 重新產碼只差時間戳記與暫存路徑；新模型版本四道檢查 PASS；離線測試全過；SITL 兩個情境和改名前相同（範本 PASS）；`02_template` 重編後 NuttX `8d3ed2a2…` 不變；FC（01）`hitl-run` 七部分全 PASS：盤旋 60.07 s、2.77 圈、0 次晚到、最慢 0.20 ms，記錄下載兩次相同、嚴格解析 PASS |
| 風（2026-10-19） | 模型的風開成外部接口（定常風，或風切＋陣風＋亂流；預設離地後才吹），SITL 與 HITL 同一個 `wind` 格式（`plant/wind.py`），說明在 [plant README](plant/README.md)「風」、AI 對使用者的說明清單在 AGENTS。原始 slx：Dryden 亂流取消註解（原本因地面空速 0 除以零而關掉）、空速輸入加 5 m/s 下限、雜訊間隔 0.1 s → 4 ms。無風時結果和之前逐位元相同；三組 Simulink 對照（含全部風都開）原始模型與核心副本逐位元相同；四道檢查 PASS（`skysurfer-1c2b65fe…`，HIL 函式庫的 wind case 和 Simulink 一致）；離線測試全過；SITL 參考情境與範本和之前相同，`wind_steady`、`wind_low_altitude` 照預期 |
| 有風實機 HITL（2026-10-19，FC 是 `01_sdfix`） | 場景 `hitl/scenarios/wind_steady_5.json`（地面開始＋定常風 5 m/s 從北方吹來，離地 5 m 後 5 s 漸進）；手動流程：`recover` → `model-start --scenario` → `takeoff --altitude 100` → 盤旋 60 s → `model-stop` → `recover --hil-force-disarm`。流程：盤旋 60 s、1.87 圈、0 次晚到（最慢 1.13 ms）、序列埠 0 錯；恢復後未解鎖、`SYS_HITL=1`、無待恢復；飛控記錄（第 53 筆，比飛行前最新的 52 新）下載兩次相同、嚴格解析 PASS。風：PX4 的 EKF（約每秒一筆）在爬升中約 20 s 估到 4.7 m/s，100 m 以上平均 5.01 m/s 從 0°（真值 5.00 m/s 從 0°）；空速計選擇器自己的風估計約 40 s 後到 5 m/s 附近。和前一次無風（2026-10-18，01）並排：圈數 1.87／2.77、半徑 78／83 m、高度 98–102／100–113 m、盤旋空速平均 17.3／24.3 m/s（有風這次後段約 15.5）、飛控記錄在解鎖瞬間有一段 24 ms 空缺／無；只列差異，沒有事先講好的判定 |
| 乾淨目錄試跑 | 2026-10-18（改名後）：從 git 拉到新資料夾、獨立快取、不連 MATLAB：`update-model` 建出**相同的 build-id** `skysurfer-6d1cf7a3…`、四道檢查 PASS；離線測試全過；**從零重編 `01_sdfix`**：PX4 `d6f12ad1…`、NuttX `8d3ed2a2…`、韌體大小都和 FC 上的相同（`.px4` 含建置時間，所以檔案 SHA 不同）；紀錄裡沒有本機路徑 |
| 收尾 | 核心精神已寫進本 README（「這套專案的精神」）；乾淨目錄試跑完成；上 GitHub：https://github.com/rhyne1012/px4-llm-sim2hitl（2026-10-18） |
