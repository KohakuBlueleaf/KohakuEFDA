---
title: KohakuEFDA 文档
summary: 工厂模型、流程、使用指南、参考资料与开发说明的首页。
tags:
  - overview
  - docs
---

# KohakuEFDA 文档

KohakuEFDA（End Field Design Automation）为《明日方舟：终末地》的集成工业系统（AIC）规划并生成工厂布局。它只读取静态游戏数据，不碰游戏本身；输出是一份经过验证、由你亲手在游戏中重现的建造指南。

你只需给它四样东西：原料到达的速率、想要的产品与速率、建造所在的核心区域（区域、哪一个核心集成工业区、等级、仓库等级），以及一个决定面积或设施数何者优先的模式。其余全由工具决定：跑哪些配方、各要几台设施、每条流需要几条传送带或管道、设施如何成行、每一行放在哪里、每条传送带与管道怎么走，以及结果是否符合游戏的规则。

流程分为数个阶段，每个阶段写出一个供下一阶段读取的 JSON 产物：**规划**（配方、设施数、物品收支、网络）、**网表**（带有引脚的设施行，以及引脚之间的网络）、**布局**（格子上的每台设施、物流单元、传送带与管道）、**评估**（每段与每台设施的稳态速率）与**报告**（每项规则结果）。网页查看器可显示全部内容。

英文以外的页面若尚未翻译，会自动显示英文内容。

## 选择你的路径

| 你现在是... | 从这里开始 |
|---|---|
| **想拿自己的工厂试试** | [Getting started](guides/getting-started.md) · [First plan](tutorials/first-plan.md) · [Scenarios](guides/scenarios.md) |
| **想检查自己建的或导入的布局** | [Checking layouts](guides/checking-layouts.md) · [Importing blueprints](guides/importing-blueprints.md) · [Geometry rules](concepts/verification/geometry-rules.md) |
| **想读懂结果** | [The pipeline](concepts/foundations/the-pipeline.md) · [Artifacts](reference/artifacts.md) · [Studio](guides/viewer.md) |
| **想理解模型** | [The factory model](concepts/foundations/the-factory-model.md) · [Planning](concepts/planning/README.md) · [Cells](concepts/cells/README.md) · [Layout](concepts/layout/README.md) |
| **想参与开发** | [Development](dev/README.md) · [Internals](dev/internals.md) · [Testing](dev/testing.md) · [Assumptions](dev/assumptions.md) |

## 文档结构

- **教程**（[tutorials/](tutorials/README.md)）：从场景文件到查看器中已验证布局的逐步引导。
- **使用指南**（[guides/](guides/README.md)）：任务导向的"我要如何完成 X"。
- **核心概念**（[concepts/](concepts/README.md)）：工具为何如此设计；含[术语表](concepts/glossary.md)，列出设施与物流单元在三种语言中的官方名称。
- **参考**（[reference/](reference/README.md)）：每个命令、字段、产物与规则。
- **开发**（[dev/](dev/README.md)）：包地图、导入顺序、测试、查看器与尚待验证的假设。
