# 01_sdfix：原生 PX4 加記憶卡修正

- **是什麼**：PX4 v1.18.0 起（[px4_lock.json](../../px4/px4_lock.json)，2026-11-25）是 PX4 原樣、不套 patch：v1.18 的 NuttX 已經內建下面這個修正，名字照舊。v1.17.0 時是 PX4 原樣，只套一個 NuttX 修正 [nuttx_82d12852_stm32h7_sdmmc_rx_invalidate.patch](../../px4/patches/)（NuttX 官方 82d1285：STM32H7 的 SD 卡 DMA 讀取後清快取，原因見 [AGENTS](../../AGENTS.md) 第 1 段）。不加模組、沒有開機檔；參數和 `00_native` 相同。
- **用途**：「原生＋修正」的基準，隨時可刷回；也是自建配方的起點：複製這個資料夾，在 `firmware/firmware.json` 的 `recipe.modules` 加模組（`02_template` 就是這樣做的）。
- **重現**：PX4 原始碼照版本鎖下載（README「環境準備」）→ `./runbridge build-firmware --release deploy/01_sdfix`（編好的 `.px4` 不放 git）→ `./runbridge deploy-test --release deploy/01_sdfix` 先看計畫 → `--flash`。
- **怎麼知道 FC 上是它**：v1.18.0：FC 回報 PX4 `935addf1d6`、NuttX `3cc0c49601597d4a`（v1.17.0 時是 `d6f12ad1c4`、`8d3ed2a2177267cb`）（`firmware.json` 的 `embedded` 與 `flashed`）。patch 以固定作者與日期 commit，所以重編後這兩個編號不變；`.px4` 檔頭有建置時間，檔案 SHA-256 每次重編都不同。`02_template` 的兩個編號和這裡相同（只多一個模組），要靠刷機紀錄與開機檔區分。

## 紀錄

證據在做測試那台機器的 `~/.cache/px4-llm-sim2hitl/`（不隨專案）。

| 時間（UTC） | 做了什麼 | 結果 | 證據 |
|---|---|---|---|
| 2026-10-18 02:28 | 第一次用 `deploy-test --flash` 燒錄、`--reuse` 跑 `hitl-run` | PASS：盤旋 60.13 s、2.78 圈，23,104 步 0 次晚到；飛控記錄（10.9 MB）下載兩次相同、嚴格解析 PASS | `deploy_runs/run_20261018_022809Z_88290c85`、`run_20261018_022926Z_1485847d` |
| 2026-10-18 07:22 | 從 `02_template` 刷回，交接時 FC 留這一版 | PASS：先刪 02 的開機檔、燒錄一次成功、寫參數 0 個；盤旋 60.0 s、2.79 圈，0 次晚到、最慢 0.52 ms；記錄（10.9 MB）下載兩次相同、嚴格解析 PASS | `deploy_runs/run_20261018_072113Z_0fe09c8e`、`hitl_runs/run_20261018_072205Z_17fe74af` |
