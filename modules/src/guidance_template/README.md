# guidance_template：把自己的算法放進 PX4 的一個例子

**這只是例子，讓人有個概念。** 真正要怎麼接，請 AI 在第 1 段先讀 PX4 原始碼，再和使用者討論方案（見 [AGENTS](../../../AGENTS.md) 第 1 段）。這裡示範的只是其中一種：在 OFFBOARD 模式裡，換掉固定翼控制鏈最上層的「導引」。

## 這個例子做什麼

- **接法**：模組編進韌體，自己發 OFFBOARD 訊號（`offboard_control_mode.velocity = true`），不需要外接任務電腦。PX4 進入 OFFBOARD 後，只把「導引」交給這個模組；高度與速度（`fw_lat_lon_control`）、姿態、角速度、控制分配都還是 PX4 原生的。
- **算法**（`GuidanceTemplate::guidance()`，換成你的就改這一段）：進入 OFFBOARD 時記下當下的航跡角與高度（航跡角 course = atan2(vE, vN)，是地面上的移動方向，不是機頭朝向 yaw；有側風時兩者不同）；15 秒後航跡角目標 +30°，35 秒後高度目標 +10 m（先直飛 15 秒，讓前一個模式（HITL 是傾斜的盤旋）的影響消失）。側向加速度 = 地速 × 0.2 × 航跡角誤差（傾角限 20°），高度交給 PX4 的 TECS，空速用預設值。
- **出事時**：位置資料無效或太舊，就停發 OFFBOARD 訊號，PX4 自己的「OFFBOARD 失聯保護」接手（`COM_OF_LOSS_T`、`COM_OBL_RC_ACT`）。沒有這個模組在跑時，PX4 根本不讓你切進 OFFBOARD。

## 驗收（這個例子自己的標準）

`analysis/template_check.py` 讀飛控記錄（SITL、HITL 用同一支）：航跡角變化和 30° 差 ≤ 3°、高度變化和 10 m 差 ≤ 1.5 m（看階躍後的尾段平均）、都要安定下來、最大傾角 ≤ 25°。「安定」是進入並維持在階躍量的 5 % 內，也就是航跡角 ±1.5°、高度 ±0.5 m，和前面的誤差門檻分開判斷。觀察時間兩邊不同：SITL 情境跑 70 s、HITL 的動作是 60 s，所以高度階躍後分別看 35 s 與 25 s，報告要寫明。SITL 的狀態是真值，HITL 是 FC 上 EKF 的估測，所以兩邊比的是表現，不要求逐點相同。資料不能判的時候（有壞值、缺一段、樣本太少、時間倒退、FC 標示估測無效）一律判不通過並寫出原因：壞資料不會得到 PASS。

| | 結果 |
|---|---|
| SITL（2026-10-18） | PASS：航向 +29.3°（上升 10.5 s、安定 14.5 s）、高度 +9.66 m、最大傾角 16.8° |
| HITL | 見 README 的狀態表 |

觀察：空速在兩邊都比 PX4 的目標（15 m/s）高很多（SITL 約 27 m/s）。原生模式的 HITL 盤旋也一樣偏快，所以這不是只有範本才會發生，但也不能因此排除範本、或它和原生控制器的交互有影響。可能的原因之一是 PX4 參數 `FW_THR_TRIM=0.6`，而這個飛機模型在 15 m/s 平飛只需要約 0.115 的油門；各因素的影響還沒確認，另外追查（README「已知問題」）。範本判定 PASS 不代表這個問題解決了。

高度判定的基準（要求本身還沒定）：記錄裡有 `tecs_status` 時，基準是階躍前 TECS 的高度目標，判的接近「最後有沒有到目標高度」（TECS 原本就有的高度偏差會算進誤差）；沒有時改用階躍前的實測高度，判的是「升高了多少」（原本的偏差不算）。兩者回答的問題不同，也還沒核對 TECS 的高度目標是否就是範本給的目標。這個例子要的是哪一種由使用者決定；在那之前，比較結果先看報告的 `altitude_base_source`，基準不同的 PASS／FAIL 不能直接比。

## 照著做一個自己的模組

1. 複製 `modules/src/guidance_template/` 成新名字，改掉檔名、類別名稱、`CMakeLists.txt` 的 `MODULE`／`MAIN`；在 `sitl/px4_external/src/` 照 `guidance_template/` 加一個同樣的包裝，並列進那裡的 `CMakeLists.txt`。
2. 改 `guidance()`（或依第 1 段討論的接法，改成要換的那一層）。
3. SITL：照 `sitl/scenarios/template_offboard.json` 寫自己的情境，`sitl/build_sitl.py` → `sitl/run_sitl.py --scenario ...` → 自己的判定程式（照 `analysis/template_check.py`）。判定程式要先確認資料能判，再算指標：照它用 `analysis/response.py` 的 `window_problems` 檢查每個窗口，資料不能判就判不通過、寫出原因。
4. 部署配方：照 `deploy/02_template/` 複製一份，`firmware/firmware.json` 的 `recipe.modules` 換成新模組，`sd/etc/extras.txt` 寫啟動指令，`hitl.json` 指定起飛後的動作（`hitl/commands/`）與判定程式。
5. `./runbridge deploy-test --release deploy/<新配方>` 先看計畫，再 `--flash`。
