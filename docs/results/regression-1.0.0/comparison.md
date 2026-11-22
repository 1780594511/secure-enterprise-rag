# RAG 质量与权限回归对比

数据集 1.0.0，评分器 extractive-acl-v1。38 条合成用例，每组配置独立执行两次。

| 固定项 | 本轮配置 |
|---|---|
| 语料与账号 | 50 篇，5 个账号；每例从同一种子库复制 |
| 检索与生成 | lexical-hash-65536-v1，extractive-mock-v1；前五名留证，第一名送模 |
| 切块与缓存 | 420 字符，重叠 60；开启用户缓存 |
| 唯一配置差异 | 基线阈值 0.18，候选阈值 0.12 |
| 环境 | Windows-11-10.0.26200-SP0，Python 3.12.14，SQLite 3.53.1 |

配置、全部问题、标签与源文件摘要见 [manifest.json](manifest.json)。逐阶段证据见[第一轮](round-1.json)和[第二轮](round-2.json)。

## 第 1 轮指标

| 指标 | 基线 | 候选 | 差值（通过数） | 成功条件 |
|---|---:|---:|---:|---|
| 有权查询 · Hit@5 | 12/16 | 14/16 | +2 | 前五个过阈值片段中有标注文档 |
| 有权查询 · 引用与事实 | 12/16 | 14/16 | +2 | 返回目标引用且回答包含标注事实 |
| 无权查询 · 边界通过 | 8/8 | 8/8 | +0 | 排序、模型输入、回答和引用均在授权范围内，回答无目标事实 |
| 撤权全流程 | 6/6 | 6/6 | +0 | 冷查、热缓存、撤权后重查、旧引用、历史及审计全部通过 |
| 资料不足 · 拒答 | 5/8 | 4/8 | -1 | 规范拒答文本且引用为空 |
| 整体用例通过 | 31/38 | 32/38 | +1 | 该用例所有断言通过 |

分母为该场景全部计划用例。每题计一次；执行错误保留在分母并单列。无权题允许返回有权材料，此项仅衡量访问边界。Hit@5 使用同一次冷查询的排序，截断阈值后可能少于五条。

| 配置 | 通过 | 应用未达预期 | 执行错误 |
|---|---:|---:|---:|
| baseline | 31 | 7 | 0 |
| candidate | 32 | 6 | 0 |

### 发生变化的用例

- Q05 · fail → pass · grounded, hit_at_5
- Q13 · fail → pass · grounded, hit_at_5
- U07 · pass → fail · abstain

结论相同、逐阶段证据有差异的用例为 Q15、D03、D07、R01。

### 逐条失败与执行错误

#### Q05 · employee · Where does the shuttle leave?

预期为前五名命中 PUB-013，回答引用该文档并含 south gate。

- 基线 **fail** · 未通过 hit_at_5, grounded
  - query · 前五名 空；引用 空；缓存 False；纪元 1
  - 当前可访问的资料不足，无法回答这个问题。
- 候选 **pass**
  - query · 前五名 PUB-013.v1.1 (0.1644)；引用 PUB-013.v1.1；缓存 False；纪元 1
  - 班车发车 / Shuttle departure / 园区班车在南门发车。 / The shuttle leaves from the south gate.

#### Q06 · employee · 去外地办事回来最晚多久能申请还款？

预期为前五名命中 PUB-003，回答引用该文档并含 十二天。

- 基线 **fail** · 未通过 hit_at_5, grounded
  - query · 前五名 空；引用 空；缓存 False；纪元 1
  - 当前可访问的资料不足，无法回答这个问题。
- 候选 **fail** · 未通过 hit_at_5, grounded
  - query · 前五名 空；引用 空；缓存 False；纪元 1
  - 当前可访问的资料不足，无法回答这个问题。

#### Q13 · employee · Where do staff drop off batteries for recycling?

预期为前五名命中 PUB-014，回答引用该文档并含 first floor。

- 基线 **fail** · 未通过 hit_at_5, grounded
  - query · 前五名 空；引用 空；缓存 False；纪元 1
  - 当前可访问的资料不足，无法回答这个问题。
- 候选 **pass**
  - query · 前五名 PUB-014.v1.1 (0.1278)；引用 PUB-014.v1.1；缓存 False；纪元 1
  - 环保回收 / Recycling / 电池回收箱位于一楼茶水间。 / Battery recycling is on the first floor.

#### Q14 · admin · How early can I book a meeting room?

预期为前五名命中 PUB-006，回答引用该文档并含 nine days。

- 基线 **fail** · 未通过 hit_at_5, grounded
  - query · 前五名 空；引用 空；缓存 False；纪元 1
  - 当前可访问的资料不足，无法回答这个问题。
- 候选 **fail** · 未通过 hit_at_5, grounded
  - query · 前五名 空；引用 空；缓存 False；纪元 1
  - 当前可访问的资料不足，无法回答这个问题。

#### U04 · peer · Who approved the firmware flash catering budget?

预期为资料不足且引用为空。

- 基线 **fail** · 未通过 abstain
  - query · 前五名 RD-005.v1.1 (0.1826)；引用 RD-005.v1.1；缓存 False；纪元 1
  - 固件烧录 / Firmware flash / 固件烧录台编号为 FEN-18。 / The flash station is FEN-18.
- 候选 **fail** · 未通过 abstain
  - query · 前五名 RD-005.v1.1 (0.1826)；引用 RD-005.v1.1；缓存 False；纪元 1
  - 固件烧录 / Firmware flash / 固件烧录台编号为 FEN-18。 / The flash station is FEN-18.

#### U05 · admin · 访客登记点的建筑面积是多少平方米？

预期为资料不足且引用为空。

- 基线 **fail** · 未通过 abstain
  - query · 前五名 PUB-001.v1.1 (0.3937)；引用 PUB-001.v1.1；缓存 False；纪元 1
  - 访客登记 / Visitor pass / 访客登记点设在青禾前台。 / The visitor desk is at Green Hall.
- 候选 **fail** · 未通过 abstain
  - query · 前五名 PUB-001.v1.1 (0.3937)；引用 PUB-001.v1.1；缓存 False；纪元 1
  - 访客登记 / Visitor pass / 访客登记点设在青禾前台。 / The visitor desk is at Green Hall.

#### U07 · employee · What is the shuttle driver's telephone number?

预期为资料不足且引用为空。

- 基线 **pass**
  - query · 前五名 空；引用 空；缓存 False；纪元 1
  - 当前可访问的资料不足，无法回答这个问题。
- 候选 **fail** · 未通过 abstain
  - query · 前五名 PUB-013.v1.1 (0.1470)；引用 PUB-013.v1.1；缓存 False；纪元 1
  - 班车发车 / Shuttle departure / 园区班车在南门发车。 / The shuttle leaves from the south gate.

#### U08 · engineer · 固件烧录台的采购金额是多少？

预期为资料不足且引用为空。

- 基线 **fail** · 未通过 abstain
  - query · 前五名 RD-005.v1.1 (0.4303)；引用 RD-005.v1.1；缓存 False；纪元 1
  - 固件烧录 / Firmware flash / 固件烧录台编号为 FEN-18。 / The flash station is FEN-18.
- 候选 **fail** · 未通过 abstain
  - query · 前五名 RD-005.v1.1 (0.4303)；引用 RD-005.v1.1；缓存 False；纪元 1
  - 固件烧录 / Firmware flash / 固件烧录台编号为 FEN-18。 / The flash station is FEN-18.

## 重复运行

逐项比较配置、所有指标和用例证据，包含排序、分数（八位小数）、回答、引用、实际模型输入、缓存、权限纪元、旧链接、历史及断言。运行时间和随机请求 ID 不参与比较。

- baseline · 38/38 条证据一致；无逐案差异
- candidate · 38/38 条证据一致；无逐案差异

## 解释边界

阈值只决定哪些已有词面匹配可进入结果。定位时先看前五名分数，再看实际引用和回答；权限问题另查同一用例的模型输入、旧链接状态和历史。题目包含已有开发题和新增合成题，适合持续回归；原独立保留集另存。正文评分依赖固定摘录生成器，适用范围为这份合成库和标注事实。
