# px4-llm-sim2hitl：給 AI 的工作規則

專案是什麼、流程、環境準備與指令見 [README](README.md)。本檔只寫 AI 怎麼工作。

**這些文件就是你對這個流程的理解**：先讀，不要從頭摸索整個流程；把時間花在幫使用者除錯和開發。開發中學到新的坑、和使用者談定的規則，寫回對應的文件，下一個 AI 就不用重學。

## 讀法

- 先讀本檔。README 只讀「這套專案的精神」「流程」「常用指令」「已知問題」「驗證矩陣」；`README.en.md` 是給人看的英文翻譯，不用讀。
- 其他文件照第 6 節的地圖按任務讀，地圖寫了什麼時候必讀。讀一條規則，要連同它底下的例外一起讀。
- 引用規則時寫編號加短標題，例如「S2 恢復與單一 owner」。
- context 被壓縮或換人接手時：重讀本檔和目前任務的必讀文件；從紀錄找回任務、讀過的版本和還缺的證據，不靠摘要下結論。哪些權限確認過，照 P1 記在 AI 自己的記憶或筆記。
- 寫回：規則寫回本檔或 `agents/` 對應的檔；事實寫進對應資料夾的 README；驗證與事件寫進 [records/verification.md](records/verification.md)。推翻舊結論時照 E3 回頭改正。

## 下結論之前

**結論和證據一樣大。** 跟人說「通過了」、寫報告、把經驗寫回文件之前，先想三件事：

1. **E1 這次要證明什麼**：分清楚是唯讀分析、探索，還是照事先講好的規則驗收；要證明的是接法打通（模組真的有作用）、要求達標，還是比原生好。報告只對那一件下結論。驗收時必要的資料缺了，寫「證據不足」，不換一個量得到的量來代替原本的要求；看到結果才想到的標準，不冒充事先的驗收。標準本身錯了可以改，但留下原結果、改的理由與新標準下的結論。人同意的探索照做，但同意不會讓證據變多。
2. **E2 證據撐到哪裡**：沒看到差異，只代表測過的範圍裡沒有差異；原生模式也有的現象，只說明它不是新模組才有，不能排除新模組的影響；SITL 與 HITL 共用同一個飛機模型，兩邊一致不證明模型像真飛機。證據不夠時把話說小，或針對缺的那一塊補一個檢查，不擴大成全部重跑。
3. **E3 什麼改變會讓它失效**：寫回文件的結論附上依據（哪次測試、哪份紀錄）與範圍（版本、配方、FC、模式），寫明換了哪些要重查。觀察、推測的原因、目前的處置分開寫；原因沒確認就寫「可能」。新證據推翻舊結論時，回頭改掉舊的那句並註明更正，不只在別處加新的。

這個專案踩過的例子：2026-10-19 有風的 HITL 紀錄寫 FC 是 `01_sdfix`，其實跑的是另一個專案的空投韌體（油門配平不同），和無風那次的比較因此混了配平，三天後才在 README 更正——拿到「FC 是 X」的紀錄，先讀回核對再用。範本 README 曾因為「原生模式也偏快」，寫下「空速偏高不是範本造成的」，話說得比證據多。

## 1. 和使用者合作

- **C1 講白話**。技術細節由 AI 自己查、自己處理；只有需要使用者做決定時才說，一次一件。講太細就失去這套專案的意義。
- **C2 照 README 的流程分段走**。**每段結束時問「下一步 1／2／3」**，段內不逐項詢問權限。
- **C3 確認流程或工具能用時，用最少的案例**（例如兩局、一趟）；統計是另一件事，另外提、由人決定。
- **C4 停下來說明**：遇到 runtime 的安全檢查擋下、原因不明的 FAIL、或需要人手（重插 USB、斷電、拆槳）時，停下來說明，不自行繞過或重試。
- **C5 每一項要求都寫明由哪一邊回答**：兩邊都量得到、量法相同的，兩邊都量、並排比；只有一邊能回答的寫明原因（例如 OFFBOARD 怎麼退出要靠 Commander，精簡 SITL 沒有）。沒量到寫「沒測」，資料缺了或不能判寫「證據不足」，都不能當通過。判通過／不通過只用**事先和人講好的規則**；沒講好的不宣告通過或失敗，但要給有依據的判讀：哪裡值得注意、哪些數字不能照字面讀（例如還沒安定時的尾段平均）、下一步建議看什麼；門檻由人定。總結分開寫「流程跑完」和「各項要求」，不要用一個 PASS 代表全部。比較時寫明 SITL 是真值、HITL 是 FC 的 EKF 估測，以及兩邊的取樣時間。比對程式先核對一個不靠比對本身的量（例如開局那一刻兩邊的位置相同、自己算的結束距離等於系統回報的），輸入一律從紀錄拿，不用「應該送了什麼」；對不上就寫在報告最上面，不要只輸出數字。
- **C6 建議人隨著開發慢慢建立自己的自動化**：同一件事手動做了兩三次（例如一段飛行動作、一種判定、一串檢查；也包括 AI 自己寫的一次性腳本，複製第二份時就該提），就建議把它變成專案裡的指令或腳本，放在現有的位置（起飛後動作放 `hitl/commands/`、判定放 `analysis/`、配方的 `hitl.json` 指定要跑哪些），之後一個指令跑完、AI 只讀結果。越用越省 token，也越不容易出錯。只在真的重複時才建議，不預先做；由人決定要不要做。

### 第 1 段「需求與規格」：最重要，先和人把整個工作流程談完

搬到 [agents/stage1.md](agents/stage1.md)：先聽、1.1 飛機模型與配平、1.2 算法、部署與驗收（PX4 接法、一頁規格）、最小打通，以及本地化、ULog 兩個建議。**談需求、寫一頁規格、換飛機、新算法，或開始自己的專案、fork 時必讀。** 每一項要求由哪一邊回答，留在上面的 C5。

### 風

使用者提到風、或情境裡有 `wind` 時，先讀 [agents/wind.md](agents/wind.md)：要先用白話告訴使用者的 8 點，以及哪些由使用者決定。

### PX4 v1.17.0 的記憶卡讀取問題

飛控記錄或 SD 卡讀取有疑問、做自建韌體配方、升級 PX4 時，先讀 [px4 README](px4/README.md)「記憶卡讀取問題」（自建韌體的配方都要套修正，要告訴使用者）。

## 2. 接手時先查平台

- 查平台、路徑、環境檢查，以及工具層面的權限（永久權限、即時排程、AI 工具的允許清單）怎麼做，見 [agents/platform.md](agents/platform.md)。**第一次在這台電腦用、換平台、權限被擋或要新的權限時必讀。**
- **P0 接上一塊這套流程沒用過的 FC**（例如在 QGC 或 ArduPilot 用過）：先完整讀回存檔，FC 上的殘留設定與 SD 卡內容照 [fc README](fc/README.md)「接手一塊用過的飛控」處理；`param-deploy` 只寫 `set`，殘留值會讓部署被擋或核對 FAIL。改 FC 上不屬於配方的值、刪 SD 卡上的檔案，都先問人。
- **P1 人說「我給你權限」，這個專案底下就是綠燈**：每一種動作（刷機、起飛、改參數、跑負載等）第一次做之前問一次，之後同一種動作先告知再做，不等回答。哪些已經確認過，記在 AI 自己的記憶或筆記（那是這台機器、這個人的事，不寫進專案）。下面三種每次都要等人回答：
  1. 收不回來或對外的：merge、刪檔、改系統設定（要 sudo 的）。推到 GitHub 的 PR 分支只告知。
  2. 新的或不正常的：新編的韌體或新算法第一次上 FC、失敗後要重試、runtime 的安全檢查擋下（照第 1 節停下來說明）。
  3. 本來就是人的決定：通過標準怎麼訂、什麼時候 merge。
- **P2 寫入與解鎖前先說**：工具權限設好之後，照上面的綠燈規則，AI 寫入 FC、解鎖前一律先說一聲（第一次等回答，之後告知就做），第 3 節的安全檢查照舊。
- **P3 時間敏感的測試前**：要跑時間敏感的測試（負載、HITL）前，AI 先查 `ulimit -r`：這只是作業系統的即時排程條件，不代表使用者已經同意那個動作。動作本身照上面的綠燈規則（第一次等回答，之後告知就做；三種例外每次等回答）；`ulimit -r` 是 0 就給人 [agents/platform.md](agents/platform.md) 裡「即時排程權限」那一條的指令。沒有即時權限、機器又忙時一定會晚到（2026-10-20：P 核心被別的計算佔滿，93 s 的飛行晚了 11 拍、最慢 16 ms）。時間敏感的測試前，其他重的工作要停或避開；同一台機器上別的 AI session 要等它自己一輪做完才看得到訊息，不能只靠訊息請它暫停。

## 3. 安全底線（不可繞過）

- **S1 寫入對象與內容要確定**：寫參數、開機檔、燒錄前確認 FC 身分、未解鎖；寫入後讀回。不確定是否成功就停，不繼續到解鎖。
- **S2 恢復與單一 owner 不能繞過**：不刪恢復記號（`recovery.json`）、寫參數交易記號（`param_deploy.json`）、`owner.lock`、`host.json`；不用重開程式或換資料夾繞過未完成的恢復。runtime 的狀態資料夾跟著程式所在的路徑，換資料夾或換電腦前，先在原處恢復並關閉 owner。
- **S3 只做隔離實體動力的 HITL**：HITL 時螺旋槳已拆或電調不供電，第一次使用前請人確認。3.2 出場檢查完成前，自動流程不關 HITL（`SYS_HITL`）、不測實體致動器。
- **S4 任務自己的實機測試**：優先用 `hitl-run`（配方的 `hitl.json` 指定起飛後動作 `after` 與判定 `check`）。非自己寫不可時，要做到和 `hitl-run` 一樣的三件事，並在報告裡和飛行結果分開寫：飛控記錄的編號比飛行前最新的那筆新（否則不算本次，就算下載兩次相同、解析也過）；測試中臨時改的參數最後還原並讀回；標準 `recover` 完成（未解鎖、`SYS_HITL` 為預期值、沒有待恢復）。
- **S5 失敗要留證據**：測試或實機流程失敗時，保留那次的 console、wire、timing、status 與資料夾，告訴人在哪裡，再分析原因；修好後的新結果另外存，不覆蓋舊的失敗。
- **S6 不用 `rm -rf` 大量刪除**。
- **S7 遠端操作時**，現場沒人能重插 USB 或斷電：刷機或恢復卡在需要人手時就停下來等。

## 4. 不變量

- **I1 唯一 plant 來源**：`model/` 的 `.slx`＋初始化＋氣動 MAT／importer＋preload。轉出的 C（`model/generated/`）是建置產物，不手改；改模型後重新產碼。
- **I2 單一 owner**：同時只有一個程序持有模型與序列埠；其他指令經本機 IPC 和它溝通。
- **I3 通道**：`controls[0..4]` = 左副翼／右副翼／升降舵／方向舵／油門。
- **I4 4 ms 迴圈不呼叫 Python 或 LLM**；runtime 是最終安全判斷者，不要為了讓操作成功而放寬它的前置條件。
- **I5 停模型 ≠ PX4 已恢復**：送過感測器資料後，待恢復狀態會持久化，要 `recover` 完成才算恢復。
- **I6 實體 HITL 不准在空中起始**。
- **I7 發布模型 release 只是離線證據**，不會自動開始 HIL、解鎖、切模式或重開 FC。

## 5. 改了什麼，要跑什麼

下表是上限，不是每次都全跑：先說這次修改可能影響哪些行為，再挑最能證明改錯了的檢查（通常一個就夠；影響到幾種行為就各挑一個），加上第 3 節的安全底線；同一批改動的檔案不重疊時，合在一起測一次。省略下游的測試要**先有理由，數字只是佐證**：例如產碼只關掉指令集擴充、算式沒動，再核對到核心與參考資料的每個誤差都和上一版一位不差，下游的配平、SITL、離線測試、HITL 算出的數字就不會不同，不必為了數字再跑。說不出理由、只有參考案例的數字相同時，只代表測過的案例沒變，參考情境沒飛到的範圍（例如某段側滑角）照樣可能不同：針對那一塊檢查，或寫明沒驗。數字相同不代表跑得一樣快：改到編譯方式（例如編譯選項）或換了電腦時，時序另外用下表 runtime 那一列的 300 s 負載測試確認。

| 改了 | 要跑 |
|---|---|
| 飛機模型（`model/`） | `./runbridge update-model --generate`（MATLAB）→ `./runbridge update-model` → 配平；刻意改了模型就照第 1.1 段（[agents/stage1.md](agents/stage1.md)）重錄參考資料。發布新的模型 release（或回退）後，下一次跑 SITL 前先重跑 `sitl/build_sitl.py`：SITL 執行檔用絕對路徑連到 plant library，不重編會用到舊模型。slx 改了也重轉 `model_r2026a/` 的 R2026a 備份（見那裡的 README） |
| `plant/` 的 C、`hitl/` 的 `native/`、`interface/`、`aircraft/`、`update.py` | `./runbridge update-model`（四道檢查）→ 離線測試 |
| `hitl/host/` 等 runtime 程式 | 離線測試；影響時序時加跑 300 s 負載（背景跑，不接飛控）：先查 `ulimit -r`，有權限就直接跑並告訴人，沒有就給人第 2 節（[agents/platform.md](agents/platform.md) 裡「即時排程權限」那一條）的指令；結果有疑慮再跑 600 s。報告寫實際跑了幾秒 |
| `sitl/`、`modules/` | `sitl/build_sitl.py` → `sitl/run_sitl.py` → `analysis/response.py` |
| 韌體、參數、開機檔（`deploy/<配方>/`、`modules/`、`px4/patches/`） | 第 3 段：**一律重新燒錄** `./runbridge deploy-test --release deploy/<配方> --flash`（必要時先編韌體 → 燒錄 → 身分核對 → 參數 → 開機檔 → hitl-run）；燒錄前告訴人 FC 上現在是什麼（不加旗標就是只看計畫）。只改外部模組時 FC 回報的版本編號可能不變、分不出新舊，所以不沿用 FC 上的韌體；`--reuse` 只在人明確要求時用。只編韌體：`./runbridge build-firmware --release deploy/<配方>` |
| `images/overview.svg`（README 最上面的流程總覽圖） | 圖上的字以中文為準（中文大字、英文小字），中英文 README 共用這一張；README 的流程或分工改了，圖也跟著改。改字後跑 `python3 images/embed_fonts.py images/overview.svg` 重新嵌入思源黑體子集（需要 fontTools、brotli 與系統的 Noto Sans CJK），同樣的字跑出同樣的檔案。視覺規則：墨灰＋一個跳色（朱紅）；實心色塊＝人決定、空心框＝自動化／AI；實線＝流程、虛線＝回頭修改 |
| `README.md`（中文，權威） | 同一次 commit 更新英文翻譯 `README.en.md`，並把它開頭記的 README.md SHA-256 換成新的（`sha256sum README.md`）；來不及翻譯時，在 `README.en.md` 開頭標明落後。英文只是翻譯，兩者不一致時以中文為準；其他文件只有中文 |

離線測試與負載（`PY` = venv 的 python：`PY="$(./runbridge where python)"`）：

```sh
OUT=<新的空資料夾>; mkdir -p "$OUT"
for f in hitl/tests/test_*.py deploy/test_*.py analysis/test_*.py; do n=$(basename "$f" .py); if "$PY" -B "$f" > "$OUT/$n.log" 2>&1; then echo "OK   $f"; else echo "FAIL $f（完整輸出 $OUT/$n.log）"; fi; done
"$PY" -B hitl/tests/run_load.py <新的空資料夾> --duration 300   # 有疑慮再 600
```

每個檔看自己的結束碼，任何一個 FAIL 都不算整組通過；完整輸出留在 `$OUT`，失敗時照第 3 節保留證據再分析。機器很忙時偶發的失敗要單獨重跑確認，兩次結果都寫進報告；原因查清楚以前叫「原因未明的失敗」，不叫假 FAIL，後一次通過不抹掉前一次；停掉負載後重跑通過，只說明負載很可能是原因，還不算查清楚。機器忙造成時序沒達標，是那個條件下的真實結果。

## 6. 在哪裡

**地圖**：什麼時候必讀什麼。

| 什麼時候（必讀） | 先讀 | 必要時再讀 |
|---|---|---|
| 第一次在這台電腦用、換平台、權限被擋或要新的權限 | [agents/platform.md](agents/platform.md) | [platforms/](platforms/ubuntu.md)、[px4 README](px4/README.md) |
| 談需求、寫一頁規格、換飛機、新算法（第 1 段）；開始自己的專案或 fork | [agents/stage1.md](agents/stage1.md) | [plant README](plant/README.md)、[範本 README](modules/src/guidance_template/README.md) |
| 使用者提到風、情境有 `wind` | [agents/wind.md](agents/wind.md) | plant README「風」 |
| 分析結果、比較 SITL 與 HITL、寫報告、把結論寫回文件 | 本檔「下結論之前」與 C5 | [analysis README](analysis/README.md)、[records/verification.md](records/verification.md) |
| 每次 HITL 或負載測試前 | 本檔 P3 與第 3 節 | [hitl README](hitl/README.md) |
| 同一件事做到第二、三次 | 本檔 C6 | [hitl/commands](hitl/commands/README.md)、analysis README |
| 飛控記錄或 SD 卡讀取有疑問、做自建韌體配方、升級 PX4 | [px4 README](px4/README.md)「記憶卡讀取問題」 | [deploy/01_sdfix](deploy/01_sdfix/README.md) |
| 改模型或 plant | [plant README](plant/README.md)（照開頭的小節目錄讀） | 第 5 節 |
| 跑或改 SITL | [sitl README](sitl/README.md)（照開頭的小節目錄讀） | analysis README |
| HITL、QGC 手動飛、看 HITL 紀錄 | [hitl README](hitl/README.md) | [hitl/commands](hitl/commands/README.md)、[hitl/autotakeoff](hitl/autotakeoff/README.md) |
| 換飛控、接手用過的飛控 | [fc README](fc/README.md) | fc/<板子>.md、deploy/<配方>/README |
| 編韌體、patch、換 PX4 版本 | [px4 README](px4/README.md) | — |
| 引用過去的驗證或數字 | [records/verification.md](records/verification.md) | 證據資料夾 |
| context 被壓縮、換人接手 | 本檔「讀法」 | 目前任務的必讀文件 |

**資料夾**：

| 資料夾 | 內容 |
|---|---|
| `model/` | 飛機模型來源；`generated/` 是轉好的 C 與 Simulink 參考結果 |
| `model_r2026a/` | 同一個模型的 R2026a 備份（給只有 R2026a 的電腦），不是模型來源，不會自動更新 |
| `images/` | README 用的圖（`overview.svg`）與嵌字工具 `embed_fonts.py` |
| `agents/` | 按任務讀的 AI 工作規則，從本檔搬出去：`stage1.md`（第 1 段）、`wind.md`（風）、`platform.md`（平台與工具權限）；什麼時候必讀見上面的地圖 |
| `records/` | 驗證紀錄帳本 `verification.md`：每一次驗證的做法、數字、範圍與更正（README「驗證矩陣」只寫結果） |
| `platforms/` | 各平台的理解：`ubuntu.md` 是驗證機（Ubuntu 24.04）每一項環境準備的理由與做法，`macos.md` 是和 Ubuntu 不同的平台行為、怎麼確認；不是安裝腳本 |
| `fc/` | 各飛控的理解（目前是 `cubeorangeplus.md`）：換一塊飛控要查的事、接手用過的飛控、和 6C 不同的地方；不是安裝腳本 |
| `aircraft/` | 飛機的氣動來源：`avl/` 是產生氣動表的 AVL 幾何、質量檔與轉表程式（不在 `model/` 裡，改它不影響模型版本） |
| `plant/` | plant 核心包裝、C 真值、C 感測器、各自的檢查程式、錄製的參考資料 |
| `sitl/` | 精簡 PX4 的 plant 模組 `plant_sim`、情境、配平、ULog 重播；`sitl_fc_lockstep.md` 是衍生專案用電腦版 PX4 當飛控與 lockstep 的經驗與建議（框架還沒有這些程式） |
| `modules/` | 自己的 PX4 模組（同一份原始碼編進 SITL 與韌體；`guidance_template` 是範例，見它的 README「照著做一個自己的模組」）。韌體只編配方 `recipe.modules` 列的模組；SITL 要在 `sitl/px4_external/src/` 加包裝並列進那裡的 `CMakeLists.txt` |
| `hitl/` | runtime（owner、worker、`hitl-run`）、起飛與起飛後動作腳本、`flight_test.json`（預設飛行與判定）、模型 release；`workflow_lessons.md` 是衍生專案的流程與工具經驗與建議（哪幾點已經搬進框架，寫在它的開頭） |
| `deploy/` | 部署配方，每塊飛控一組：Pixhawk 6C 是 `00_native`（原生韌體＋參數，可隨時刷回）、`01_sdfix`（原生＋記憶卡修正 patch）、`02_template`（01＋範例模組 `guidance_template`＋開機檔＋`hitl.json` 指定的起飛後動作與判定）；Cube Orange+ 是同樣三層的 `*_cubeorangeplus`（`hil` 板子變體，見 `fc/`）。自建配方的 `firmware/firmware.json` 的 `recipe` 寫要套的 patch 與 `modules/` 的模組；怎麼編、patch 怎麼 commit、FC 回報的 hash 怎麼核對，見 [px4 README](px4/README.md)「編 FC 韌體」 |
| `px4/` | PX4 版本鎖、原始碼樹核對、修正 patch |
| `analysis/` | 響應指標、ULog 讀檔與嚴格解析、重播比對、繞圈任務的航線追蹤、飛行檢視圖（衛星底圖與 setpoint） |
| `hitl/missions/` | 繞圈任務（航線）的定義與工具 `mission.py`：一份定義產生 QGC `.plan` 和 MAVLink 上傳項目，QGC 改過的 plan 也能匯入回來；範例 `example_loop.json` |
