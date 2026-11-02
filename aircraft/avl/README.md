# aircraft/avl：SkySurfer 氣動表的來源幾何

`model/m_05.mat`、`model/m_1.mat`（Mach 0.05、0.10 的 AVL 氣動表，`model/import_aerostates_avl.m` 讀取）由這裡的幾何算出。重心、力矩參考點、中性點與 MAC 的意思和換算見 [plant README「重心與氣動作用點」](../../plant/README.md)。這個資料夾不在 `model/` 裡，改這裡不影響模型版本；`model/` 底下任何檔案變動都要重新產碼。

| 檔案 | 內容 |
|---|---|
| `SkySurfer_wing2410_NDU.avl` | 產生現用氣動表的幾何：原作者幾何（SHA-256 `54a6eb4f…`）＋兩個相容性修改（左翼剖面改成 y 遞增；垂直尾翼翼尖弦長 0 → 1e-4 m）＋使用者 2026-10-15 量測的升降舵（鉸鏈舵，弦長 0.035 m，每側 y = 0–0.165 m）與方向舵（弦長 0.025 m）＋2026-11-02 的修正（左右主翼同一個 `COMPONENT`、尾翼與垂尾同一個 `COMPONENT`、左翼 `Sspace` 負號、水平尾翼 `ANGLE` 1.2° 估計值，見 [hitl/sim_to_flight.md](../../hitl/sim_to_flight.md) 第 6 點）。副翼沿用原作者幾何（約 30 % 弦長，沒有量測） |
| `sky_mass_20251130.mass` | 原作者的質量檔：1.3 kg、重心 AVL x = 0.05 m、慣量 0.023／0.029／0.05 kg·m²（模型曾用 Ixx × 2、Iyy × 3；2026-10-26 起改用第一次飛試的估計，現在是 0.023／0.040／0.063，見 [plant README](../../plant/README.md)「重心與氣動作用點」） |
| `run_table.py`、`table.json` | 一個指令：檢查幾何、重算、比較、轉表 |
| `build_avl_mat.m` | 把 AVL 的計算結果（AVL MCP 的 `result.json`）轉成 importer 讀的 MAT（每個 α 一個 93×6 cell：第 1 欄標籤，第 2–6 欄為 β −10、−5、0、5、10） |

`.avl` 檔頭寫的 `Xref` 是 0；算表時另外指定 0.05（等於質量檔的重心）。直接用 AVL 重算時，記得把 `Xref` 設成 0.05，否則力矩參考點和模型的 `XREF_m` 對不上。

**同一片翼或相連的面要放同一個 `COMPONENT`。** 沒放時 AVL 在面和面之間用有限渦核。2026-11-02 之前左右主翼是兩個獨立的面，雖然都接到 y = 0，效果卻像翼根有開口：升力斜率 4.60（修正後 4.99）、中性點 62.4 %（修正後 51.7 % MAC）、e 0.71（修正後 0.89），加密網格也不會好。寫成單一面加 `YDUPLICATE` 結果相同，但 L／R 副翼就不能各自獨立。

## 重新產生氣動表（換飛機或改幾何時）

```sh
"$PY" -B aircraft/avl/run_table.py --compare <舊的 result.json>   # 先看：檢查幾何、重算、列出差異，什麼都不寫
"$PY" -B aircraft/avl/run_table.py --write-mat                   # 確定了才寫進 model/（要 MATLAB）
./runbridge model-cycle                                           # model/ 改了，接著跑這個
```

- 幾何檢查找到「相接卻不在同一個 `COMPONENT`」的面時，不算也不寫（結束碼 1）；確定那是真的開口才加 `--ignore-lint`。關鍵字照 AVL 只看前四個字元（`SURF`、`SECT`、`COMP` 也認得）。
- 先看的數字用 α 0、5 與 β 0、5 的工況，舵面導數照這份幾何的名字（`elevator`、`rudder`、`aileron…`）讀；換了格點或舵面名字，那幾行就不印，不會擋住轉表。`build_avl_mat.m` 的 Mach 標籤、α 與舵面名單仍是這架飛機的，換飛機要一起改。
- 工況和參考值在 [table.json](table.json)：Mach 0.05、0.10 × α −10、−5、0、5、10、15 × β −10、−5、0、5、10；角速度與舵面為 0；Sref 0.238、Cref 0.2、Bref 1.41、`Xref` = 質量檔的重心；輸出 total、stability、body。換飛機就換這個檔。
- 工具經 [AVL MCP](https://github.com/rhyne1012/avl-mcp)（驗證時是 AVL 3.52）算，位置用 `SIM2HITL_AVL_MCP`、`SIM2HITL_AVL_BIN`、`SIM2HITL_AVL_WORK` 指定（沒設時找 `~/.local/share/AVL-MCP/` 底下的 AVL MCP 0.5.0 與 AVL 3.52，是衍生專案那台機器裝的位置；工作資料夾預設在 cache 的 `avl_runs/`）；側滑斜率用 β 格點相減。
- 手動轉表時是 MATLAB（在專案根目錄）：

```matlab
addpath('aircraft/avl');
build_avl_mat('<job>/result.json', 'model/m_05.mat', 'model/m_05.mat', 'm05');
build_avl_mat('<job>/result.json', 'model/m_1.mat',  'model/m_1.mat',  'm1');
```

- 第二個參數是讀列標籤用的模板（現用 MAT 即可）。舵面依名稱對應：d01 aileronR、d02 aileronL、d03 elevator、d04 rudder（和 Simulink 接線相同），不依 AVL 的宣告順序。
- `model/FW_SkySurfer_InitialFunction.m` 的 `XREF_m` 要對應算表用的 `Xref`（換算見 plant README），`cbar`、`b`、`S` 照參考值。

## 重現檢查（2026-10-15）

用原作者幾何（只做那兩個相容性修改）以同樣設定重算，和原本的 MAT 比：最大絕對差 6e-5（原 MAT 只有 5–6 位有效數字）。這只證明近似重現，不證明原 MAT 的確切產生過程；重算結果差很多時，不要直接替換 MAT。

2026-11-02：修正前再用 AVL MCP v0.5.0 重算 22 個工況（Mach 0.10），和當時的 MAT 最大差約 1e-13（總力矩用穩定軸的 `Cl'tot`、`Cn'tot`，和 importer 一致）。修正後的 MAT 就是這個資料夾現在的幾何算出來的（AVL MCP job `48ce1b06…`，60 工況）。

## 另一份：VSP 氣動表

模型裡還有一份 OpenVSP（VSPAERO）算的氣動表 `model/Skysurfer.mat`，由 `model/import_aerostates_vsp.m` 讀；`model/FW_SkySurfer_InitialFunction.m` 的 `useAVL_VSP` 設成 1 才會用。現在是 0（用 AVL），這包所有的檢查、SITL、HITL 都是 AVL。2026-11-02 起這份表由 [aircraft/vsp](../vsp/README.md) 用同一份平面形狀、同樣的工況與參考點重算。下面是**舊表**（2026-11-02 以前）的紀錄：

- 沒有幾何檔，也沒記當初的參考值（翼面積、參考弦長、力矩參考點），不能重算，也不能確認力矩參考點和 AVL 相同；
- 不知道有沒有用 2026-10-15 量測的升降舵、方向舵尺寸（那次只修了 AVL）；
- 數字：中性點在參考點後面約 0.41 個參考弦長，升力斜率 5.24／rad（2026-11-02 修正前的 AVL 是約 0.41 個參考弦長、4.62，修正後是約 0.30、約 5.0）；範圍 α −10～15°、β −10、0、10°；另加的阻力修正 `CD_fix_VSP` 0.065（`CD_fix_AVL` 現在是 0.030）。

舊表的幾何一直沒找到；新表和 AVL 的比較在 [aircraft/vsp](../vsp/README.md)。要拿掉這份屬於模型改動（`model/` 有變動就要重新產碼）。
