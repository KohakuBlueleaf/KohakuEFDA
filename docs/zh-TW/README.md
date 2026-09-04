---
title: KohakuEFDA 文件
summary: 工廠模型、流程、使用指南、參考資料與開發說明的首頁。
tags:
  - overview
  - docs
---

# KohakuEFDA 文件

KohakuEFDA（End Field Design Automation）為《明日方舟：終末地》的集成工業系統（AIC）規劃並產生工廠佈局。它只讀取靜態遊戲資料，不碰遊戲本身；輸出是一份經過驗證、由你親手在遊戲中重現的建造指南。

你只需給它四樣東西：原料到達的速率、想要的產品與速率、建造所在的核心區域（區域、哪一個核心集成工業區、等級、倉庫等級），以及一個決定面積或設施數何者優先的模式。其餘全由工具決定：跑哪些配方、各要幾台設施、每條流需要幾條傳送帶或管道、設施如何成列、每一列放在哪裡、每條傳送帶與管道怎麼走，以及結果是否符合遊戲的規則。

流程分為數個階段，每個階段寫出一個供下一階段讀取的 JSON 產物：**規劃**（配方、設施數、物品收支、網路）、**網表**（帶有接腳的設施列，以及接腳之間的網路）、**佈局**（格子上的每台設施、物流單元、傳送帶與管道）、**評估**（每段與每台設施的穩態速率）與**報告**（每項規則結果）。網頁檢視器可顯示全部內容。

英文以外的頁面若尚未翻譯，會自動顯示英文內容。

## 選擇你的路徑

| 你現在是... | 從這裡開始 |
|---|---|
| **想拿自己的工廠試試** | [Getting started](guides/getting-started.md) · [First plan](tutorials/first-plan.md) · [Scenarios](guides/scenarios.md) |
| **想檢查自己建的或匯入的佈局** | [Checking layouts](guides/checking-layouts.md) · [Importing blueprints](guides/importing-blueprints.md) · [Geometry rules](concepts/verification/geometry-rules.md) |
| **想讀懂結果** | [The pipeline](concepts/foundations/the-pipeline.md) · [Artifacts](reference/artifacts.md) · [Studio](guides/viewer.md) |
| **想理解模型** | [The factory model](concepts/foundations/the-factory-model.md) · [Planning](concepts/planning/README.md) · [Cells](concepts/cells/README.md) · [Layout](concepts/layout/README.md) |
| **想參與開發** | [Development](dev/README.md) · [Internals](dev/internals.md) · [Testing](dev/testing.md) · [Assumptions](dev/assumptions.md) |

## 文件結構

- **教學**（[tutorials/](tutorials/README.md)）：從情境檔到檢視器中已驗證佈局的逐步引導。
- **使用指南**（[guides/](guides/README.md)）：任務導向的「我要如何完成 X」。
- **核心概念**（[concepts/](concepts/README.md)）：工具為何如此設計；含[詞彙表](concepts/glossary.md)，列出設施與物流單元在三種語言中的官方名稱。
- **參考**（[reference/](reference/README.md)）：每個命令、欄位、產物與規則。
- **開發**（[dev/](dev/README.md)）：套件地圖、匯入順序、測試、檢視器與尚待驗證的假設。
