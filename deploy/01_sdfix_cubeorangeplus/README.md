# 01_sdfix_cubeorangeplus：Cube Orange+ 的原生 PX4 加記憶卡修正

- **是什麼**：PX4 v1.18.0 起（2026-11-25）就是 [00_native_cubeorangeplus](../00_native_cubeorangeplus/README.md)（`hil` 板子變體），不再另套 patch：v1.18 的 NuttX 已經內建這個修正。v1.17.0 時是 `hil` 變體再套 NuttX 的記憶卡讀取修正 [nuttx_82d12852_stm32h7_sdmmc_rx_invalidate.patch](../../px4/patches/)。Cube Orange+ 的 SD 卡和 6C 一樣走 STM32H7 的 SDMMC（SDMMC1、開 D-cache），同一個驅動，所以同樣要套（原因見 [AGENTS](../../AGENTS.md) 第 1 段）。不加模組、沒有開機檔；參數和 `00_native_cubeorangeplus` 相同。
- **用途**：Cube 上「原生＋修正」的基準，也是 Cube 自建配方的起點（`02_template_cubeorangeplus` 就是它加範例模組）。
- **重現**：`./runbridge build-firmware --release deploy/01_sdfix_cubeorangeplus` → `./runbridge deploy-test --release deploy/01_sdfix_cubeorangeplus` 先看計畫 → `--flash`。
- **怎麼知道 FC 上是它**：v1.18.0：FC 回報 board_version 4184、PX4 `51daf13fca`、NuttX `3cc0c49601597d4a`；和 `00_native_cubeorangeplus` 相同（v1.17.0 時是 `c45268d056`、`8d3ed2a2177267cb`，和 6C 的 `01_sdfix` 同一個 NuttX commit）。`02_template_cubeorangeplus` 的編號相同，要靠刷機紀錄與開機檔區分。

## 紀錄

證據在做測試那台機器的 `~/.cache/px4-llm-sim2hitl/`（不隨專案）。

| 時間（UTC） | 做了什麼 | 結果 | 證據 |
|---|---|---|---|
| 2026-10-20 09:09 | 從 `02_template_cubeorangeplus` 刷回，`deploy-test --flash`；交接時 FC 留這一版 | PASS：先刪 02 的開機檔、燒錄一次成功、寫參數 0 個；盤旋 60.16 s、2.79 圈，23,094 步 0 次晚到、最慢 0.29 ms；飛控記錄（7.0 MB）下載兩次相同、嚴格解析 PASS | `deploy_runs/run_20261020_090940Z_1b7fb4ea`、`hitl_runs/run_20261020_091034Z_01a331a4` |
