---
name: test-driven-development
version: 1.0.0
description: TDD 方法论：先测试、后实现、再重构
metadata:
  openclaw:
    always: false
  nanobot:
    always: false
---

# 测试驱动开发

你采用 TDD 方法论编写代码，遵循 Red-Green-Refactor 循环。

## 核心循环

1. **Red** — 先写一个会失败的测试（明确期望行为）
2. **Green** — 用最简单的代码让测试通过
3. **Refactor** — 优化代码结构，保持测试绿色

每个循环控制在 5 分钟以内。

## 测试金字塔

- **单元测试（70%）** — 快速、隔离、覆盖核心逻辑
- **集成测试（20%）** — 验证模块间交互
- **E2E 测试（10%）** — 验证关键用户路径

## 测试设计原则

- **FIRST**: Fast, Independent, Repeatable, Self-validating, Timely
- 每个测试只验证一个行为
- 测试名描述预期行为：`should_return_error_when_input_is_empty`
- 重点测试边界条件和异常路径
- Mock 外部依赖，不 mock 被测对象

## 何时用 TDD

- 业务逻辑复杂 → 必须用
- 算法实现 → 建议用
- UI 布局 → 不适用
- 探索性原型 → 不适用
