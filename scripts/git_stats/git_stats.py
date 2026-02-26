#!/usr/bin/env python3
"""
Git 仓库统计脚本
生成 commit 数量和代码行数折线图
"""

import argparse
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path


def run_git_command(repo_path: str | Path, cmd: list) -> str:
    """执行 git 命令并返回输出"""
    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    return result.stdout


def get_commit_counts(repo_path: str | Path, author: str, since: str, until: str, granularity: str) -> dict:
    """获取 commit 数量统计"""
    cmd = [
        "git", "log",
        f"--author={author}" if author else "--all",
        f"--since={since}",
        f"--until={until}",
        "--format=%ad",
        "--date=short"
    ]
    
    output = run_git_command(repo_path, cmd)
    commits = output.strip().split('\n') if output.strip() else []
    
    counts = defaultdict(int)
    for date in commits:
        if not date:
            continue
        key = normalize_date(date, granularity)
        counts[key] += 1
    
    return dict(counts)


def get_code_lines(repo_path: str | Path, author: str, since: str, until: str, granularity: str) -> dict:
    """获取代码行数统计"""
    cmd = [
        "git", "log",
        f"--author={author}" if author else "--all",
        f"--since={since}",
        f"--until={until}",
        "--pretty=format:%ad%n",
        "--date=short",
        "--numstat"
    ]
    
    output = run_git_command(repo_path, cmd)
    lines = output.strip().split('\n') if output.strip() else []
    
    added = defaultdict(int)
    deleted = defaultdict(int)
    
    current_date = None
    for line in lines:
        if not line:
            continue
        
        parts = line.split('\t')
        
        # 如果第一个部分是日期（不是纯数字），则是日期行
        if len(parts) == 1 or not parts[0][0].isdigit():
            # 这是日期行
            date_str = parts[0][:10] if len(parts[0]) >= 10 else parts[0]
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                current_date = date_str
            except ValueError:
                continue
        elif len(parts) >= 2 and current_date:
            # 这是 numstat 行
            add = parts[0]
            delete = parts[1] if len(parts) > 1 else '0'
            
            if add == '-' or delete == '-':
                continue
            if not add.isdigit():
                continue
            
            key = normalize_date(current_date, granularity)
            added[key] += int(add) if add.isdigit() else 0
            deleted[key] += int(delete) if delete.isdigit() else 0
    
    return {'added': dict(added), 'deleted': dict(deleted)}


def get_total_lines(repo_path: str | Path, author: str, since: str, until: str, granularity: str) -> dict:
    """获取累计代码行数统计"""
    cmd = [
        "git", "log",
        f"--author={author}" if author else "--all",
        f"--since={since}",
        f"--until={until}",
        "--pretty=format:%ad%n",
        "--date=short",
        "--numstat"
    ]
    
    output = run_git_command(repo_path, cmd)
    lines = output.strip().split('\n') if output.strip() else []
    
    daily_added = defaultdict(int)
    daily_deleted = defaultdict(int)
    
    current_date = None
    for line in lines:
        if not line:
            continue
        
        parts = line.split('\t')
        
        if len(parts) == 1 or not parts[0][0].isdigit():
            date_str = parts[0][:10] if len(parts[0]) >= 10 else parts[0]
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                current_date = date_str
            except ValueError:
                continue
        elif len(parts) >= 2 and current_date:
            add = parts[0]
            delete = parts[1] if len(parts) > 1 else '0'
            
            if add == '-' or delete == '-':
                continue
            if not add.isdigit():
                continue
            
            key = normalize_date(current_date, granularity)
            daily_added[key] += int(add) if add.isdigit() else 0
            daily_deleted[key] += int(delete) if delete.isdigit() else 0
    
    sorted_dates = sorted(daily_added.keys())
    cumulative = 0
    cumulative_data = {}
    for date in sorted_dates:
        net = daily_added.get(date, 0) - daily_deleted.get(date, 0)
        cumulative += net
        cumulative_data[date] = cumulative
    
    return cumulative_data


def plot_total_lines(total_lines: dict, output_path: str, granularity: str):
    """绘制累计代码行数折线图"""
    if not total_lines:
        print("No total line data found")
        return
    
    sorted_dates = sorted(total_lines.keys())
    values = [total_lines[d] for d in sorted_dates]
    
    date_format = "%Y-%m-%d" if granularity == "daily" else "%Y-%m"
    date_objs = []
    for d in sorted_dates:
        try:
            date_objs.append(datetime.strptime(d, date_format))
        except ValueError:
            continue
    
    if not date_objs:
        print("No valid date data found")
        return
    
    x_dates = mdates.date2num(date_objs)
    
    plt.figure(figsize=(12, 6))
    plt.plot(x_dates, values, marker='o', linewidth=2, markersize=4, color='#9C27B0')
    plt.fill_between(x_dates, values, alpha=0.3, color='#9C27B0')
    
    plt.title('Total Code Lines Over Time', fontsize=14, fontweight='bold')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Total Lines', fontsize=12)
    plt.grid(True, alpha=0.3)
    
    if granularity == "daily":
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
    elif granularity == "monthly":
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Total lines chart saved to: {output_path}")


def get_code_breakdown(repo_path: str | Path, author: str) -> dict:
    """获取代码行数按目录分布"""
    cmd = [
        "git", "log",
        f"--author={author}" if author else "--all",
        "--pretty=tformat:",
        "--numstat"
    ]
    
    output = run_git_command(repo_path, cmd)
    lines = output.strip().split('\n') if output.strip() else []
    
    dir_stats = defaultdict(int)
    
    for line in lines:
        if not line:
            continue
        
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        
        add = parts[0]
        if add == '-' or not add.isdigit():
            continue
        
        file_path = parts[2] if len(parts) > 2 else ''
        if not file_path:
            continue
        
        parts_path = file_path.split('/')
        if len(parts_path) > 1:
            dir_name = parts_path[0]
        else:
            dir_name = 'root'
        
        dir_stats[dir_name] += int(add)
    
    return dict(dir_stats)


def plot_code_breakdown(dir_stats: dict, output_path: str):
    """绘制代码行数目录占比饼图"""
    if not dir_stats:
        print("No breakdown data found")
        return
    
    sorted_dirs = dict(sorted(dir_stats.items(), key=lambda x: x[1], reverse=True))
    
    total = sum(sorted_dirs.values())
    if total == 0:
        print("No code lines to display")
        return
    
    labels = list(sorted_dirs.keys())
    sizes = list(sorted_dirs.values())
    
    colors = ['#4CAF50', '#2196F3', '#FF9800', '#E91E63', '#9C27B0', 
              '#00BCD4', '#FF5722', '#795548', '#607D8B', '#8BC34A']
    colors = colors * (len(labels) // len(colors) + 1)
    colors = colors[:len(labels)]
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    result = ax.pie(
        sizes, 
        labels=labels, 
        autopct=lambda pct: f'{pct:.1f}%\n({int(pct / 100 * total)} lines)',
        colors=colors,
        startangle=90,
        pctdistance=0.75
    )
    
    if len(result) == 3:
        wedges, texts, autotexts = result
    else:
        wedges, texts = result
        autotexts = []
    
    for text in texts:
        text.set_fontsize(9)
    for at in autotexts:
        at.set_fontsize(8)
    
    ax.set_title('Code Lines by Directory', fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Code breakdown chart saved to: {output_path}")


def normalize_date(date_str: str, granularity: str) -> str:
    """根据时间粒度标准化日期"""
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    
    if granularity == "weekly":
        monday = date - timedelta(days=date.weekday())
        return monday.strftime("%Y-%m-%d")
    elif granularity == "monthly":
        return date.strftime("%Y-%m")
    else:
        return date.strftime("%Y-%m-%d")


def fill_missing_dates(data: dict, since: str, until: str, granularity: str) -> dict:
    """填充缺失的日期"""
    since_dt = datetime.strptime(since, "%Y-%m-%d")
    until_dt = datetime.strptime(until, "%Y-%m-%d")
    
    result = {}
    current = since_dt
    while current <= until_dt:
        if granularity == "weekly":
            key = (current - timedelta(days=current.weekday())).strftime("%Y-%m-%d")
            current += timedelta(weeks=1)
        elif granularity == "monthly":
            key = current.strftime("%Y-%m")
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        else:
            key = current.strftime("%Y-%m-%d")
            current += timedelta(days=1)
        
        result[key] = data.get(key, 0)
    
    return result


def plot_commit_counts(counts: dict, output_path: str, granularity: str):
    """绘制 commit 数量折线图"""
    if not counts:
        print("No commit data found")
        return
    
    sorted_dates = sorted(counts.keys())
    values = [counts[d] for d in sorted_dates]
    date_objs = [datetime.strptime(d, "%Y-%m-%d" if granularity == "daily" else "%Y-%m") for d in sorted_dates]
    x_dates = mdates.date2num(date_objs)
    
    plt.figure(figsize=(12, 6))
    plt.plot(x_dates, values, marker='o', linewidth=2, markersize=4, color='#4CAF50')
    plt.fill_between(x_dates, values, alpha=0.3, color='#4CAF50')
    
    plt.title('Commit Count Over Time', fontsize=14, fontweight='bold')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Commits', fontsize=12)
    plt.grid(True, alpha=0.3)
    
    if granularity == "daily":
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
    elif granularity == "monthly":
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Commit chart saved to: {output_path}")


def plot_code_lines(added: dict, deleted: dict, output_path: str, granularity: str):
    """绘制代码行数折线图"""
    if not added:
        print("No code line data found")
        return
    
    all_keys = set(added.keys()) | set(deleted.keys())
    sorted_dates = sorted([d for d in all_keys if d and len(d) >= 7])
    
    if not sorted_dates:
        print("No valid code line data found")
        return
    
    add_values = [added.get(d, 0) for d in sorted_dates]
    del_values = [deleted.get(d, 0) for d in sorted_dates]
    
    date_format = "%Y-%m-%d" if granularity == "daily" else "%Y-%m"
    date_objs = []
    for d in sorted_dates:
        try:
            date_objs.append(datetime.strptime(d, date_format))
        except ValueError:
            continue
    
    if not date_objs:
        print("No valid date data found")
        return
    
    x_dates = mdates.date2num(date_objs)
    
    plt.figure(figsize=(12, 6))
    plt.plot(x_dates, add_values, marker='o', linewidth=2, markersize=4, color='#2196F3', label='Added')
    plt.plot(x_dates, del_values, marker='s', linewidth=2, markersize=4, color='#F44336', label='Deleted')
    plt.fill_between(x_dates, add_values, alpha=0.2, color='#2196F3')
    plt.fill_between(x_dates, [-v for v in del_values], alpha=0.2, color='#F44336')
    
    plt.title('Code Lines Over Time', fontsize=14, fontweight='bold')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Lines', fontsize=12)
    plt.legend(loc='upper left')
    plt.grid(True, alpha=0.3)
    
    if granularity == "daily":
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
    elif granularity == "monthly":
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Code lines chart saved to: {output_path}")


def get_repo_date_range(repo_path: str | Path, author: str) -> tuple[str, str]:
    """获取仓库的第一个和最后一个 commit 日期"""
    # 获取第一个 commit 日期（最旧的）
    cmd_first = [
        "git", "log",
        f"--author={author}" if author else "--all",
        "--format=%ad",
        "--date=short"
    ]
    output_first = run_git_command(repo_path, cmd_first).strip()
    first_date = output_first.strip().split('\n')[-1] if output_first.strip() else ""
    
    # 获取最后一个 commit 日期（最新的）
    cmd_last = [
        "git", "log",
        f"--author={author}" if author else "--all",
        "--format=%ad",
        "--date=short",
        "-1"
    ]
    last_date = run_git_command(repo_path, cmd_last).strip()
    
    return first_date, last_date


def main():
    parser = argparse.ArgumentParser(description="Generate git commit and code lines charts")
    parser.add_argument("--repo", default=".", help="Repository path")
    parser.add_argument("--author", help="Author name")
    parser.add_argument("--since", default="auto", help="Start date (YYYY-MM-DD), or 'auto' for first commit")
    parser.add_argument("--until", default="auto", help="End date (YYYY-MM-DD), or 'auto' for last commit")
    parser.add_argument("--granularity", choices=["daily", "weekly", "monthly"], default="monthly", help="Time granularity")
    parser.add_argument("--output-dir", default=".", help="Output directory for charts")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        print(f"Error: Repository path does not exist: {repo_path}")
        return
    
    # 自动检测时间范围
    if args.since == "auto" or args.until == "auto":
        first_date, last_date = get_repo_date_range(repo_path, args.author)
        if args.since == "auto":
            args.since = first_date
        if args.until == "auto":
            args.until = last_date
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Generating stats for: {repo_path}")
    print(f"Period: {args.since} to {args.until}")
    print(f"Granularity: {args.granularity}")
    if args.author:
        print(f"Author: {args.author}")
    print()
    
    print("Fetching commit counts...")
    commit_counts = get_commit_counts(
        repo_path, args.author, args.since, args.until, args.granularity
    )
    commit_counts = fill_missing_dates(commit_counts, args.since, args.until, args.granularity)
    
    print("Fetching code lines...")
    code_lines = get_code_lines(
        repo_path, args.author, args.since, args.until, args.granularity
    )
    
    print("Generating charts...")
    plot_commit_counts(
        commit_counts,
        str(output_dir / "commit_counts.png"),
        args.granularity
    )
    plot_code_lines(
        code_lines['added'],
        code_lines['deleted'],
        str(output_dir / "code_lines.png"),
        args.granularity
    )
    
    print("Fetching total lines...")
    total_lines = get_total_lines(
        repo_path, args.author, args.since, args.until, args.granularity
    )
    plot_total_lines(
        total_lines,
        str(output_dir / "total_lines.png"),
        args.granularity
    )
    
    print("Fetching code breakdown...")
    code_breakdown = get_code_breakdown(repo_path, args.author)
    plot_code_breakdown(
        code_breakdown,
        str(output_dir / "code_breakdown.png")
    )
    
    print("\nDone!")


if __name__ == "__main__":
    main()
