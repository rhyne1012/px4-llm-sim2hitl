# px4-llm-sim2hitl

**繁體中文** | [English](README.en.md)

（英文版是翻譯；兩者不一致時以本中文版為準）

飛控開發套件：MATLAB/Simulink 飛機模型 → 轉成 C → SITL（精簡 PX4）→ 客製 PX4 韌體 → 實體飛控（Pixhawk）HITL。用 AI 開發時，AI 的工作規則在 [AGENTS.md](AGENTS.md)。

![流程總覽：需求與規格 → SITL 電腦模擬 → HITL 實體飛控；人選下一步，AI 做技術](images/overview.svg)

**範例飛機是 SkySurfer**（固定翼）：`model/`、`hitl/aircraft/skysurfer/`、模型版本名 `skysurfer-…` 與 `SkySurfer_Core` 這些是飛機本身。套件叫 `px4-llm-sim2hitl`：資料夾用全名（Linux 是 `~/.cache/px4-llm-sim2hitl`、`~/.local/share/px4-llm-sim2hitl/venv`、`~/.config/px4-llm-sim2hitl`；這台機器實際的位置用 `./runbridge where` 查），環境變數用短名 `SIM2HITL_*`（環境變數不能有減號）。換成自己的飛機見第 1.1 段。

> 狀態：從舊的 macOS 專案搬到 Ubuntu 已完成，整套流程跑通（見「驗證矩陣」與 [records/verification.md](records/verification.md)）。2026-10-20 換到第二塊飛控 Cube Orange+ 也走完一輪；換飛控要查的事見 [fc/](fc/README.md)。

## 怎麼開始

**把這個網址貼給你的 AI 就好。** 它會讀這份 README 和 [AGENTS](AGENTS.md)，接下來你只要說想做什麼。

- **只想了解**：任何能讀網頁的 AI 都可以，問它「這是什麼、能幫我做什麼」。
- **要動手開發**：用能在你電腦上執行指令的 AI（例如 Claude Code、Codex），一樣貼網址，請它下載到你電腦上一個固定的資料夾（之後不要搬；要搬先照 AGENTS 恢復）。
  - 第一次：說「照 README 的環境準備，幫我把這台電腦設好」。它會一項一項查，要 sudo 或權限時請你貼一次。**完整流程只在 Ubuntu 24.04（x86-64）驗證過**；macOS（Apple Silicon）驗證到 SITL（見「驗證矩陣」與 [platforms/macos.md](platforms/macos.md)）；其他系統沒測過，AI 會照官方文件試，但可能要多花時間踩坑。
  - 之後：直接說你想做什麼，例如「我想換成我的飛機」「我想做一個新的導引算法」。它會從第 1 段「需求與規格」開始跟你談。
- **AI 要夠力**：要能讀完很長的文件、自己寫程式、自己跑指令並看懂結果。模型太小或推理開太低，容易跳過文件自己猜。測試過可以用：GPT-6.1 sol（推理 medium）。

開場白範例：「請把 https://github.com/rhyne1012/px4-llm-sim2hitl 下載到 ~/Developer，先讀 README 和 AGENTS，然後跟我談第 1 段：我想……」

## 這套專案的精神

**這不是一套自動化工具，也不應該變成一套想包辦所有開發情境的自動化；它是讓你的 AI 一開始就懂這個流程的交接。** 從飛機模型、PX4 原始碼、SITL、編譯燒錄到實體飛控，這條路怎麼走、哪裡有坑、什麼已經驗證過、怎樣才算對，都寫在文件（這份 README、[AGENTS.md](AGENTS.md)、各資料夾的 README）和現成的檢查裡。AI 讀完就接得上，不必每次從頭摸索整個流程，可以把時間和 token 花在真正要做的事：幫你除錯、幫你開發。

打個比方：AI 每開一次新對話，都像第一天上班的新同事。這包是前人留下的交接：系統怎麼運作、哪裡有坑、哪些已經驗證過、做事的規矩，還有一條實際走通過的基本路線（模型 → SITL → 燒錄 → HITL）。交接不會替他把工作做完，也不會列出他將來遇到的每一種狀況；它讓他第一天就能把心思放在你的問題上，遇到新狀況也知道從哪裡下手。處理完的新經驗和跟你談定的規則寫回交接，下一個新同事就更快上手。

- **先有理解，才有工具**：指令和腳本只是把已經想通的步驟固定下來。文件寫的是「為什麼這樣做、坑在哪裡」，例如記憶卡讀取的錯誤、地面模型不會讓飛機轉動、風什麼時候開始吹。這樣 AI 遇到問題才知道去哪裡查，也不會為了讓事情成功就繞過安全檢查硬做。
- **結論和證據一樣大**：每個結論都說得出依據（哪次測試、哪份紀錄）和範圍（版本、配方、FC、模式）；證據少就把話說小，而不是多跑測試。沒看到差異不等於沒有差異；SITL 與 HITL 用同一個飛機模型，兩邊一致不證明模型像真飛機；條件變了，舊結論要重查。AI 怎麼做見 [AGENTS](AGENTS.md)「下結論之前」。
- **目的**：把這包交給別人，讓他和他的 AI 能從改飛機模型、開發飛控，一路做到編譯、燒錄與 HITL。
- **簡單、輕量、同一份來源**：每件事只放一個地方；能沿用現有程式與檢查就沿用；不為了可能用不到的情況預先加東西。
- **AI 講白話**：技術細節由 AI 查、AI 處理；只有目標、選擇與成功條件問人。
- **第 1 段最重要**：AI 先讀鎖定版本的 PX4 原始碼，把可行的接法用白話攤開和人討論，由人選；再建議先做「最小打通」，讓整條路先通、記錄下來，之後的修改交給自動化。
- **第 3 段一條龍**：編譯 → 燒錄 → 身分核對 → 參數 → 開機檔 → HITL → 飛控記錄，一個指令跑完；開始前先告訴人 FC 上現在是什麼，然後一律重新燒錄（只改外部模組時，FC 回報的版本編號可能不變，分不出新舊）。
- **自動化跟著開發慢慢長出來**：工具是理解的副產品。同一件事做了兩三次，AI 就建議把它變成專案裡的指令或腳本，由人決定；越用越省 token。
- **環境不寫死、驗收標準寫死**：路徑、編譯器、MATLAB、PX4 原始碼樹自動找、可指定，換平台時請 AI 查官方文件；量尺（版本鎖、檢查容差、4 ms、負載門檻）不隨環境改。
- **不分權限等級**：每段結束時問「下一步 1／2／3」，段內不逐項詢問；但 runtime 的安全檢查（FC 身分、未解鎖、讀回、恢復）不可繞過，見 AGENTS 第 3 節。
- **提醒，不擋**：非預設的飛行參數照跑並記錄；看起來不對的地方告訴人，由人決定。
- **SITL 與 HITL 用同一把尺**：同一份情境、同一支判定程式、同一種記錄（ULog）；兩邊的差異本身就是要找的資訊。「同一把尺」是同一項要求的定義、基準與判定方式相同；只有兩邊都量得到的要求才並排比，例如精簡 SITL 沒有 EKF 與 Commander，OFFBOARD 怎麼退出只有 HITL 能回答。

## 流程

1. **需求與規格**：先談清楚要做什麼、怎樣算成功。
   - 1.1 飛機模型與配平（換飛機或改模型時）
   - 1.2 算法、部署與驗收
2. **SITL（電腦模擬）**：反覆模擬，結果存成 `trace.csv`＋ULog（MATLAB 可直接讀）。
3. **HITL（自動編譯、燒錄、測試）**
   - 3.1 手動 HITL（`./runbridge`＋QGC）
   - 3.2 出場檢查：QGC 關掉 HITL 後確認舵面有輸出（尚未完成）

## 環境準備（第一次）

完整流程只在 **Ubuntu 24.04 x86-64** 驗證過（各平台驗證到哪一段見「驗證矩陣」；macOS 的平台差異見 [platforms/macos.md](platforms/macos.md)）。下面列出要準備什麼、怎麼確認；每一項為什麼要、驗證機（Ubuntu）的做法，見 [platforms/ubuntu.md](platforms/ubuntu.md)。做法只是例子，換平台或版本時，**請 AI 先查該項的官方文件**確認正確做法再裝。

| 項目 | 怎麼確認 |
|---|---|
| Python 環境 | `./runbridge --check-python` |
| MATLAB | `matlab` 在 PATH，或設 `SIM2HITL_MATLAB_ROOT` |
| C 編譯器 | `cc --version` |
| PX4 原始碼與工具鏈 | `python3 px4/check_px4_tree.py` 為 PASS |
| **即時排程權限** | `ulimit -r` ≥ 2；`./runbridge status` 的 `scheduler.time_constraint_result` 為 0 |
| 序列埠 | `ls -l /dev/ttyACM*`、`groups` |
| QGC | QGC 開著時 `lsof -p <QGC PID>` 只見 UDP 14550、不見 `/dev/ttyACM*` |

**同一台機器放兩份**（例如套件和自己的 fork）：runtime 的狀態跟著資料夾路徑，本來就分開；下面這些預設兩份共用，要分開就設環境變數。暫存資料夾（`SIM2HITL_CACHE`）；SITL 編譯資料夾（PX4 樹裡的 `build/px4_sitl_default_sim2hitl`，`SIM2HITL_SITL_SUFFIX`）——不分開的話，一邊重編，另一邊的 SITL 就跑到這一邊的機體，不會報錯；同時跑 SITL 時的 PX4 編號（`run_sitl.py --instance-base`）；韌體建置樹（`<PX4 樹>-build`，`SIM2HITL_PX4_BUILD_TREE`；共用時不要兩邊同時編）。FC 只有一個：同一時間只能一份開 owner，換之前先在原處 `recover` 並關 owner。

## 常用指令

```sh
./runbridge --help                    # 所有動作
./runbridge where                     # 這台機器實際的位置（venv 的 python、cache、PX4 樹、模型 release）；where python 只印一項
./runbridge update-model --generate   # 第一段：MATLAB 產碼 → model/generated（要 MATLAB）
./runbridge update-model              # 第二段：編譯、四道檢查、發布模型 release（不需要 MATLAB 連線）
./runbridge bridge                    # 開 owner（持有模型與序列埠）；QGC 用 UDP 連
./runbridge status                    # owner 狀態
./runbridge model-start              # 3.1：模型在地面開始運行（要先確認沒有待恢復、status 的 missing_conditions 是空的）；--scenario <場景> 換場景
./runbridge takeoff --altitude 100 --after template_offboard   # 3.1：模型在地面運行時自動起飛 → Hold → OFFBOARD（範本，FC 要是 02_template）→ Hold（QGC 的選單切不到固定翼的 Offboard）
./runbridge deploy-test --release deploy/<配方>           # 第 3 段：只看計畫（FC 上現在是什麼、會做什麼）
./runbridge deploy-test --release deploy/<配方> --flash   # 平常用這個：必要時編韌體 → 燒錄 → 參數 → 開機檔 → hitl-run
./runbridge deploy-test --release deploy/<配方> --reuse   # 只在人明確要求時：沿用 FC 上的韌體，參數 → 開機檔 → hitl-run
```

手動 HITL（3.1）的順序：`bridge` 開 owner → `status` 確認恢復完成、啟動條件齊全 → `model-start` → 確認模型在地面運行 → `takeoff`（之後可以用 QGC 的搖桿接手，要點哪裡見 [hitl README](hitl/README.md)「用 QGC 搖桿手動飛」）。結束後 `model-stop`，再照 [hitl README](hitl/README.md) 的恢復規則 `recover`（在空中結束的要加 `--hil-force-disarm`），最後 `shutdown` 關 owner。

## 已知問題

- **K1 模型與 PX4 參數不吻合（空速偏高）**：PX4 的 `FW_THR_TRIM=0.6`，這個飛機模型在 15 m/s 平飛只需要約 0.115 的油門。已經觀察到：原生盤旋與 SITL 的空速都在 20–30 m/s（目標 15 m/s）；HITL 中 TECS 要爬高時空速衝高、高度衝過頭，範本的高度判定因此 FAIL。油門配平的差距是可能的原因之一，但兩者的因果與影響多大還沒確認。另一條線索：2026-10-19 有風的 HITL，FC 剛好跑著油門配平 0.115 的韌體（見 [records/verification.md](records/verification.md) V13 的更正），盤旋空速平均 17.3 m/s、後段約 15.5，比配平 0.6 時接近目標；這支持油門配平的假設，但那次同時有風、韌體也不同，不算證明。照 [AGENTS](AGENTS.md) 的原則先查模型（推力、阻力、重量），再決定模型要修，還是這架飛機的 PX4 參數本來就要配合實機。
- **K2 3.2 出場檢查還沒做**：`deploy/00_native` 的基準參數沒有指定實體舵機輸出（`PWM_MAIN_FUNC*`、`PWM_AUX_FUNC*` 全為 0）、`GPS_1_CONFIG=0`、空速計驅動未開；關掉 HITL 不會有任何輸出。需要實機的接線與參數。
- **K3 一般使用者的即時權限**：見「環境準備」的即時排程權限；沒有時能跑，但時間餘裕小。

## 驗證矩陣

只寫哪一段、哪個平台、哪天驗證過；每格只有 PASS、FAIL 或沒測，沒測的不算支援。

| 階段 | Linux（Ubuntu 24.04 x86-64） | macOS（27.0.1 arm64） |
|---|---|---|
| 原始碼樹與環境核對 | PASS（2026-10-18；2026-10-20 第二台） | PASS（2026-10-20） |
| 產碼（MATLAB R2026b） | PASS（2026-10-20，關掉指令集擴充後重跑） | PASS（2026-10-20） |
| 模型發布（四道檢查、60 秒節拍） | PASS（2026-10-20；同日第二台沒有 MATLAB，用專案的最小標頭檔也 PASS） | PASS（2026-10-20） |
| 配平 | PASS（2026-10-20，和上一版每一位相同） | PASS（2026-10-20，每一位相同） |
| SITL 參考情境與範本 | PASS（2026-10-20；第二台也 PASS） | PASS（2026-10-20，指標相同） |
| SITL 多實例 | PASS（2026-10-18，1000 次） | PASS（2026-10-20，第一批有 1 個卡住，見 macOS 文件） |
| 離線 runtime 測試 | PASS（2026-10-20；第二台 15 個檔全過） | PASS（2026-10-20，194 個） |
| 韌體編譯 | PASS（2026-10-18，6C；2026-10-20，Cube Orange+） | 沒測 |
| 實機迴路（HITL） | PASS（2026-10-18，6C；2026-10-20 6C 沒有即時權限、機器忙時時序 FAIL，見 [records/verification.md](records/verification.md) V14；2026-10-20 Cube Orange+ 三個配方 PASS，沒有即時權限、機器閒置） | 沒測 |

飛控（Pixhawk 6C、Cube Orange+）各驗證到哪裡，見 [fc README](fc/README.md)「驗證過的飛控」。

每一格的做法、數字、範圍與更正見 [records/verification.md](records/verification.md)（每筆有編號，例如 V14）。

## 驗證紀錄

逐次的做法、數字、範圍與更正，搬到 [records/verification.md](records/verification.md)（每筆一個編號）。
