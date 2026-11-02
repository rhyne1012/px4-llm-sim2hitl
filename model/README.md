# model：SkySurfer 飛機模型（唯一來源）

**`FW_SkySurfer_HIL.slx` 是這個專案唯一的飛機 `.slx`，也是轉碼的錨點。** 精簡 SITL、HITL 和 `sitl/trim.py`（配平、線性化）跑的都是從它產生的同一份 C（`generated/`）。不要另存第二份 slx；要比較或備份就用 git。slx 根層的說明框和模型的 Description 也寫著這件事。換成自己的飛機時，照樣只留一份 slx，並把這一頁改成那架飛機的。

## 檔案

| 檔案 | 內容 |
|---|---|
| `FW_SkySurfer_HIL.slx` | 飛機模型本身（錨點） |
| `FW_SkySurfer_InitialFunction.m` | 參數：質量、慣量、重心 `CG_m`、力矩參考點 `XREF_m`、參考長度、舵效、氣動修正、推力、地面、選 AVL／VSP。slx 的 InitFcn 每次模擬或產碼前都會執行它 |
| `import_aerostates_avl.m`、`m_05.mat`、`m_1.mat` | AVL 氣動表（由 [aircraft/avl](../aircraft/avl/README.md) 產生），飛的是這一份 |
| `import_aerostates_vsp.m`、`Skysurfer.mat` | VSP 氣動表（由 [aircraft/vsp](../aircraft/vsp/README.md) 產生），只用來比較（`useAVL_VSP = 1` 才會用） |
| `model_local_folders.m` | 讓 Simulink 的快取與產生的檔案放在專案外 |
| `generated/` | 產生的 C 和 Simulink 參考結果。建置產物，**不手改** |

## 改模型的流程

1. 改 slx 或上面的 `.m`／`.mat`。
2. `./runbridge model-cycle`：產碼 → 比對生成碼 → 發布並跑四道檢查 → 配平與線性模型 → 重錄參考資料 → 重編精簡 SITL。沒打算改飛機時 `numeric_change` 必須是 false：參考資料一個陣列都不變、Simulink 參考結果也相同。只改方塊名字時生成碼的識別字會變，報告標 `code_changed_only`；改到參考情境沒跑的路徑（例如 `useAVL_VSP = 0` 時的 VSP 表）也是這樣，由人判斷是哪一種。這個資料夾裡的 `.md` 不算模型來源，改這一頁不用重新產碼。
3. HITL 不在 model-cycle 裡，要人和 FC。

產碼的 builder（`plant/core/build_core.m`）用 **SID** 找方塊，所以方塊可以改名；但根層的 `Controls`／`CoreSnapshot` 埠名、`SETTING1` 裡的初值與風的常數（換成輸入時用）、`CoreSnapshot` 的欄位名稱都不能動，動了要一起改 builder 和 `plant/include/plant_core.h`。

## 模型結構

```
Controls[16] → Actuator_Mapping → UAV → CoreSnapshot[72]
UAV
├─ ACTUATOR          命令 → 舵面角（AVL 正負號）、舵機 20/(s+20)、500 °/s；油門 5/(s+5)
├─ SETTING1          初值與模擬設定（builder 會把其中的常數換成根層輸入）
└─ Airframe
   ├─ Aerodynamic     AVL_CD … AVL_Cn ＋ AVL_Forces_Moments（飛的，穩定軸）
   │                  VSP_CD … VSP_Cn ＋ VSP_Forces_Moments（比較用，風軸）
   │                  Effectiveness_AIL_R／AIL_L／ELE／RUD（舵效）、Select_AVL_VSP_Force／Moment
   ├─ Propulsion、Ground Model、Environment（Gravity、Wind）
   ├─ Mass_and_Initial_State
   ├─ 6DoF            Attitude_Kinematics、Mass_Inertia、Angular_Acceleration
   └─ Measurement     Air_Data（α、β、空速）
```

## 和實飛對過的修正在哪裡

都在 `FW_SkySurfer_InitialFunction.m`（尾翼角在 AVL 幾何）。下面的任務頁是衍生專案的私有紀錄，框架看得到的依據整理在 [sim_to_flight.md](../hitl/sim_to_flight.md) 第 6 點：

- 舵效：升降舵 0.8、副翼 0.9（2026-11-02，風標飛測（衍生專案 px4-skysurfer-sim2hitl 的 `docs/tasks/20261102_ft_vane.md`））、方向舵 0.9 → 0.6（沒驗證）。
- 側滑滾轉：AVL 的 `Cltot` 加 `dClb_flight` = −0.105 /rad（風標飛測（衍生專案 px4-skysurfer-sim2hitl 的 `docs/tasks/20261102_ft_vane.md`））。
- 阻力：`CD_fix_AVL` 0.030。
- 水平尾翼 `ANGLE` 1.2°：不是幾何角（量到的安裝角差約 0），是代表推力力矩等效應的等效值（氣動檢討（衍生專案 px4-skysurfer-sim2hitl 的 `docs/tasks/20261102_aero_review.md`））。
- 質量、慣量、重心：[plant README](../plant/README.md)「重心與氣動作用點」。

## 2026-11-02 的整理

只改名、加說明框，數值不變（在衍生專案用 `model-cycle` 確認：參考資料一個陣列都沒變、配平不變。框架這邊同一個 commit 還改了 Clβ 與副翼，沒有只改名的那一次）：`UAV/UAV` → `UAV/Airframe`；`Subsystem` → `Mass_and_Initial_State`；6DoF 的 `Subsystem`／`Subsystem1`／`Subsystem2` → `Attitude_Kinematics`／`Mass_Inertia`／`Angular_Acceleration`；Measurement 的 `Subsystem` → `Air_Data`；氣動的 `CD`、`CY`、`CL`、`Cl`、`Cm`、`Cn` → `AVL_*`，`CDD`、`CSS`、`CLL`、`CMl`、`CMm`、`CMn` → `VSP_CD`、`VSP_CS`、`VSP_CL`、`VSP_Cl`、`VSP_Cm`、`VSP_Cn`，兩個力與力矩方塊 → `AVL_Forces_Moments`、`VSP_Forces_Moments`，`Aeroelasticity_*` → `Effectiveness_*`，兩個 Switch → `Select_AVL_VSP_Force`／`Moment`。Goto／From 標籤（`[CDD]` 等）沒有改。

## 2026-11-03：VSP 路徑的方向舵

VSP 路徑原本在 `Rud_deg` 進六個 `VSP_*` 方塊前各接一個增益 −1，用來補舊 `Skysurfer.mat` 相反的方向舵正負號。2026-11-02 的新表已經和 AVL 的 `d04` 同號，這六個 −1 反而讓 `useAVL_VSP = 1` 時方向舵反向（每單位方向舵的 Cn 約 −0.04／rad，AVL 是 +0.04）。已拿掉，現在兩條路徑一樣直接接 `Rud_deg`；VSP 路徑的說明框也記了這件事。飛的 AVL 路徑不變（參考資料與 Simulink 參考結果相同）。
