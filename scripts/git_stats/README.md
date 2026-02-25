# Git 统计脚本

生成 Git 仓库的 commit 数量和代码行数折线图。

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
# 基本用法（当前仓库，每月统计）
python git_stats.py

# 指定仓库路径
python git_stats.py --repo /path/to/repo

# 指定作者
python git_stats.py --author "Your Name"

# 按周统计
python git_stats.py --granularity weekly

# 按天统计
python git_stats.py --granularity daily

# 指定时间范围
python git_stats.py --since 2025-01-01 --until 2025-12-31

# 指定输出目录
python git_stats.py --output-dir ./charts

# 组合使用
python git_stats.py --repo . --author "Your Name" --monthly --output-dir ./output
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--repo` | 仓库路径 | 当前目录 |
| `--author` | 作者名称（精确匹配） | 全部作者 |
| `--since` | 开始日期 | 2024-01-01 |
| `--until` | 结束日期 | 当前日期 |
| `--granularity` | 时间粒度 | monthly |
| `--output-dir` | 输出目录 | 当前目录 |

## 输出

生成两个 PNG 图片：
- `commit_counts.png` - Commit 数量折线图
- `code_lines.png` - 代码行数折线图（新增/删除）
