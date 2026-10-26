# analysis：判定與指標

> 用途：SITL 與 HITL 共用的分析程式：判定、指標、ULog 工具。
> 什麼時候讀：要判讀結果、寫或改判定程式、看 ULog 時。HITL 的紀錄先讀什麼，見 [hitl README](../hitl/README.md)「看結果先讀什麼」。
> 可以跳過：只跑流程、不看細節時。
> 小節：檔案表｜ULog 工具包（SITL、HITL、實機共用）

SITL 與 HITL 共用的分析程式。Python 用專案的 venv（`PY="$(./runbridge where python)"`，`./runbridge --setup` 建的；這些程式要 numpy）。

| 檔案 | 用途 |
|---|---|
| [response.py](response.py) | 搖桿階躍情境的響應指標（定義見程式開頭的說明）：基準與其斜率、尾窗平均與其斜率、變化量、峰值、上升時間（10→90 %）、安定時間（5 % 帶；未安定為 null）、roll／pitch 的絕對設定值與 `change_error`（相對）、`abs_error`（絕對）、越過絕對設定值的超越量；資料不完整就 `valid=false`、exit 2 |
| [hitl_trace.py](hitl_trace.py) | HITL 的 `host/wire.bin` 轉成 SITL 欄位的 trace（`response.py --hitl-log` 呼叫） |
| [ulog.py](ulog.py) | ULog 讀檔（只用 numpy）：各主題的 structured array、info（`ver_hw`、`ver_sw`）、參數、dropout、log 訊息；`intervals()` 算記錄間隔 |
| [replay_compare.py](replay_compare.py) | ULog 重播的輸出比對與輸入記錄品質（`sitl/run_sitl.py --replay` 呼叫；做法見 [sitl README](../sitl/README.md)） |
| [loop_tracking.py](loop_tracking.py) | 繞圈任務（例如跑道）飛得怎樣：偏離航線（往外為正）、轉彎的滾轉命令峰值、各直線段地速、逆向飛的時間、CAS／高度範圍、EKF 估的風。直線段是航點圍成的迴圈裡最長的兩段（離兩端各 25 m、離線 50 m 內），轉彎是超出直線段兩端的部分，所以航點移動（例如在 QGC 微調後匯入）也適用。預設取第二段 Mission（第一段是爬升後的進場），`--all` 取全部。`--ulog <LOG.ulg> --mission hitl/missions/example_loop.json` |
| [flight_review.py](flight_review.py) | 一趟飛行的檢視圖：航跡疊衛星底圖（航點與接受半徑、依飛行模式上色、Offboard 依序編號、所有趟在 Mission／Offboard 時的範圍框），以及 setpoint 對實際值（滾轉、俯仰、高度、空速、正在飛去的航點），可以把其他趟疊上去（`--compare`）、另外放大一塊（`--zoom W,E,S,N`）。另印一份 JSON：每趟的範圍、FC 收到的航點和航線檔差多少、home 在空中被改了幾次。沒有航線檔時，航點用 FC 實際飛去的目標。畫圖要 matplotlib 和 Pillow（專案 venv 沒有；Ubuntu 24.04 可以用系統的 `python3`，套件 `python3-matplotlib`、`python3-pil`，中文字型 `fonts-noto-cjk`）；`--no-plots` 只用 numpy。衛星圖塊（Esri World Imagery，拍攝日期不明）第一次下載後快取在 `<cache>/map_tiles/`；`--no-map` 不用網路 |

```sh
"$PY" -B analysis/response.py \
    --trace <run>/instance_0/trace.csv --scenario sitl/scenarios/stabilized_steps.json --out metrics.json
```

- 輸入是 `trace.csv`（plant 真值、搖桿、五路 controls，[sitl README](../sitl/README.md)）與情境檔；設定值換算用 `deploy/00_native/` 的 `FW_MAN_R_MAX`、`FW_MAN_P_MAX`。
- roll／pitch 階躍看姿態角；設定值由 trace 裡的搖桿算（所以 SITL 與 HITL 同一套），另讀 `FW_PSP_OFF`。yaw 搖桿在 Stabilized 是經由偏航角速度設定值驅動方向舵，看機體偏航角速度 r，主要看峰值；之後因方向穩定性衰減，沒有超越量，`settled` 也剛好在漂移門檻附近，不拿來驗收。
- 「尾窗平均」是階躍最後 30 % 的平均，不一定是穩態；`tail_slope_per_s` 大或 `settled=false` 時，`abs_error` 只代表窗口結束時還差多少。
- 資料品質：時間軸要有限且嚴格遞增；每個窗口（階躍前 1 s、階躍、尾窗，以及那一軸的搖桿在階躍前 1 s 到階躍結束）都要有限值、相鄰樣本間隔 ≤ `--max-gap`（預設 0.05 s）且涵蓋整個窗口；不合格的階躍 `valid=false` 並列出 `problems`，exit 2。JSON 不寫 NaN（算不出的值是 null）。
- SITL 重跑結果不逐位元相同（PX4 work queue 先後不固定），比對兩次結果時用容差；參考情境 3 次重跑的指標差 ≤ 0.004°／0.004 s（舊機器上量的）。
- **HITL**：runtime 不記 plant 真值，所以從飛行 log 目錄裡 `host/wire.bin`（或 `wire.bin`）的 MAVLink 轉 trace（這種飛行用 `hitl/commands/stabilized_steps.py`，Ubuntu 上還沒飛過）：

  ```sh
  "$PY" -B analysis/response.py --hitl-log <飛行 log 目錄> --scenario sitl/scenarios/stabilized_steps_hitl.json --out <目錄>/metrics.json
  ```

  - 會在 `--out` 旁邊寫 `hitl_trace.csv`、`hitl_scenario.json`（實測的階躍時間），再算指標；輸出另含 `hitl_conversion`（各階躍與名目時間的差、樣本數、序列期間各來源的最大間隔）。
  - 來源：FC 回傳的 `ATTITUDE`（100 Hz，**EKF2 姿態與濾波後角速度**；SITL 是 plant 真值）、`LOCAL_POSITION_NED`（高度 = −z，EKF2 原點以上）、`VFR_HUD`（**CAS**，100 m 時比 TAS 低約 0.5 %）、`HIL_ACTUATOR_CONTROLS`（controls[0..4]）；搖桿用實際寫給 FC 的 `MANUAL_CONTROL`。每個封包都驗 CRC，跨 record 的封包會接起來。
  - 階躍時間用量的：飛手序列以 50 Hz tick 推進，每個動作最多晚一個 tick。序列起點是第一個等於情境基準桿量的 MANUAL_CONTROL；送出的桿量必須和情境一致到 1/1000，不一致就報錯，不會默默對錯時間。

## ULog 工具包（SITL、HITL、實機共用）

SITL 預設會記 ULog（`sitl/run_sitl.py`，`--no-ulog` 可關），HITL 由 `hitl-run` 從 FC 下載，實機飛行的 SD 卡上也是同一種檔案。

| 工具 | 用途 |
|---|---|
| [ulog.py](ulog.py) | Python 讀檔（只用 numpy）：各主題的 structured array、參數、log 訊息、dropout |
| [ulog_strict.py](ulog_strict.py) | 嚴格解析整份檔案（每則訊息格式正確、剛好結束在檔尾），抓下載損壞 |
| [ulog_export.py](ulog_export.py) | 轉成 CSV（每個主題一個檔＋參數＋訊息），給沒有 UAV Toolbox 的 MATLAB（`readtable`）、試算表或其他工具；`--list` 先看有哪些主題 |
| [matlab/ulog_overview_plot.m](matlab/ulog_overview_plot.m) | MATLAB（UAV Toolbox 的 `ulogreader`，不需要 Java）的總覽圖範例：航向、高度與 TECS 目標、傾角與側向加速度目標、空速與 TECS 空速目標，OFFBOARD 期間灰底。複製後畫自己模組需要的主題 |
| [template_check.py](template_check.py) | `guidance_template` 範例的自動判定（讀 ULog）；新模組照它寫自己的。資料不能判（壞值、缺段、樣本太少、時間倒退、估測標示無效）就判不通過並寫出原因，壞資料不會得到 PASS；窗口檢查和 `response.py` 共用 `window_problems`。高度階躍的基準是 `tecs_status` 的高度目標，記錄裡沒有這個主題時改用實測高度，兩者的數字不能直接比：報告的 `altitude_base_source` 寫明用了哪一個（例：SD 卡上的 `etc/logging/logger_topics.txt` 沒列 `tecs_status`） |

常用主題：`vehicle_local_position`（位置、速度、`ref_alt`）、`vehicle_attitude`（`q`）、`airspeed_validated`、`vehicle_status`（`nav_state`，14 = OFFBOARD）、`tecs_status`（高度與空速的目標和內部狀態）、`fixed_wing_lateral_setpoint`／`fixed_wing_longitudinal_setpoint`、`actuator_servos`／`actuator_motors`、`log_message`（模組的 `PX4_INFO`）。SITL 的狀態是真值，HITL 與實機是 FC 上 EKF 的估測。

**建議使用者這樣用（AI 要主動說明好處，由使用者決定）**：

- **同一種格式**：SITL、HITL、實機都是 ULog，同一支程式就能把三者疊在一起比。
- **看得到 PX4 內部**：除了飛機怎麼動，還有每一層的目標與控制器狀態，找原因快。例：一張總覽圖就看出 TECS 空速目標 15 m/s、實際 25–30 m/s（`FW_THR_TRIM` 與模型不吻合），SITL 與 HITL 都一樣。
- **分工**：AI 用 Python 自動判定（`*_check.py`），人用 MATLAB 的圖直覺檢查、做報告。
- **大量模擬**：SITL 很快（數字見 [sitl README](../sitl/README.md)），可以掃參數、跑蒙地卡羅，再統計。
- **通用**：PX4 生態的 Flight Review、PlotJuggler、pyulog 都讀得到，方便和別人分享。
- **代價**：預設記錄設定下，一次 60 s 的 SITL ULog 約 14 MB。大量批次建議 `--no-ulog`（只留 `trace.csv`），只替挑出來的幾次記 ULog，或用 `--logger-topics` 只記需要的主題。
