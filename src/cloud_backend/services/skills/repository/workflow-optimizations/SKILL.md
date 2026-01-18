---
name: workflow-optimizations
description: Optimize generated workflow by reviewing patterns.
---

# Workflow Optimizations

## 核心原则

你的目标是**简化 workflow，提高执行效率和成功率**。

在理解 workflow 操作语义和浏览器工作原理的基础上，判断哪些步骤可以简化或删除。

## 关键知识

1. **scraper_agent 获取完整 DOM** - 不需要元素在视口内，可以提取页面上任何数据
2. **导航的本质** - 点击链接的目的是到达目标 URL，如果能直接到达就不需要点击
3. **用户意图 > 操作形式** - 理解用户想要什么，而不是机械复制操作

## 导航优化

**原则**: 点击导航不可靠，优先使用 scraper 提取 URL + browser 导航

点击导航（`interaction_steps` 点击链接）可能因为页面结构变化而失败。更可靠的方式是：
1. 用 `scraper_agent` 提取目标 URL
2. 用 `browser_agent` 的 `target_url` 直接导航

**什么时候可以简化为直接导航**:

| URL 特征 | 处理方式 |
|----------|----------|
| 固定路径 `/about`, `/products` | ✅ 直接用 `target_url` 导航 |
| 固定组合 `baseUrl + /makers` | ✅ 可以拼接后直接导航 |
| 含日期 `/news/2026/01/18` | ❌ 必须 scraper 提取 |
| 含 ID `/product/12345` | ❌ 必须 scraper 提取 |

**注意**: 用户创建的 workflow 可能会长期使用。含日期的 URL 必须动态获取，否则下次运行时会访问过期的页面。

## 优化执行

**逐个检查每个 step**，判断是否可以应用优化：
1. 这个 step 是点击导航吗？→ 能否改成 scraper + target_url？
2. URL 是固定的还是动态的？→ 固定的可以直接写死
3. 用户的真实意图是什么？→ 右键/hover 可能只是想获取数据

根据上述原则自行推演其他场景。

## 底线规则

**永远使用 intent 中的原始 URL/href，不要简化或猜测。**
