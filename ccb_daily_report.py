#!/usr/bin/env python3
"""ccb每日日报生成脚本 - 读取ccb_log.json并输出到文件（带昵称）"""
import json, time, os, re

LOG_FILE = '/root/AstrBot/data/ccb_log.json'
OUTPUT_FILE = '/root/AstrBot/data/plugins/astrbot_plugin_ccb_plus/ccb_daily_summary.txt'
NICK_CACHE = '/root/AstrBot/data/plugins/astrbot_plugin_ccb_plus/nick_cache.json'
GROUP_ID = '1077203318'
TARGET_GROUP = '1077203318'

def load_nick_cache():
    """加载昵称缓存"""
    try:
        if os.path.exists(NICK_CACHE):
            with open(NICK_CACHE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return {}

def get_nick(uid, cache):
    """优先从缓存获取昵称"""
    uid_str = str(uid)
    if uid_str in cache and cache[uid_str]:
        return cache[uid_str]
    return uid_str

def main():
    # 加载昵称缓存
    nick_cache = load_nick_cache()

    logs = []
    if not os.path.exists(LOG_FILE):
        print(f"日志文件不存在: {LOG_FILE}")
        return

    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            if not isinstance(logs, list):
                logs = []
    except Exception as e:
        print(f"读取日志失败: {e}")
        return

    today_start = time.time() - 86400
    today_logs = [
        entry for entry in logs
        if str(entry.get("group", "")) == GROUP_ID
        and entry.get("timestamp", 0) >= today_start
    ]

    if not today_logs:
        msg = "今日群内暂无ccb记录喵～"
        print(msg)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(msg)
        return

    total_count = len(today_logs)
    total_vol = sum(float(entry.get("vol", 0)) for entry in today_logs)
    total_dur = sum(float(entry.get("duration", 0)) for entry in today_logs)

    # 执行者排行
    executor_stats = {}
    for entry in today_logs:
        eid = entry.get("executor", "?")
        executor_stats[eid] = executor_stats.get(eid, 0) + 1
    executor_rank = sorted(executor_stats.items(), key=lambda x: x[1], reverse=True)

    # 被ccb排行
    target_stats = {}
    for entry in today_logs:
        tid = entry.get("target", "?")
        target_stats[tid] = target_stats.get(tid, 0) + 1
    target_rank = sorted(target_stats.items(), key=lambda x: x[1], reverse=True)

    # 注入量排行
    vol_stats = {}
    for entry in today_logs:
        tid = entry.get("target", "?")
        v = float(entry.get("vol", 0))
        vol_stats[tid] = vol_stats.get(tid, 0) + v
    vol_rank = sorted(vol_stats.items(), key=lambda x: x[1], reverse=True)

    msg_lines = [
        f"📊 今日ccb日报 (过去24h) 📊",
        f"━━━━━━━━━━━━━━━",
        f"🔞 今日共发生 {total_count} 次ccb",
        f"💦 累计注入 {total_vol:.2f}ml",
        f"⏱️ 总时长 {total_dur:.1f}min",
        f"━━━━━━━━━━━━━━━",
    ]

    emojis = ["🥇", "🥈", "🥉"]
    if executor_rank:
        msg_lines.append("🏆 今日ccb之王")
        for i, (uid, cnt) in enumerate(executor_rank[:3], 1):
            nick = get_nick(uid, nick_cache)
            emoji = emojis[i-1] if i <= 3 else f"  {i}."
            msg_lines.append(f"  {emoji} {nick} — {cnt}次")
        msg_lines.append("")

    if target_rank:
        msg_lines.append("🎯 今日艾草榜")
        for i, (uid, cnt) in enumerate(target_rank[:3], 1):
            nick = get_nick(uid, nick_cache)
            emoji = emojis[i-1] if i <= 3 else f"  {i}."
            msg_lines.append(f"  {emoji} {nick} — {cnt}次")
        msg_lines.append("")

    if vol_rank:
        msg_lines.append("💧 今日被注入量排行")
        for i, (uid, v) in enumerate(vol_rank[:3], 1):
            nick = get_nick(uid, nick_cache)
            emoji = emojis[i-1] if i <= 3 else f"  {i}."
            msg_lines.append(f"  {emoji} {nick} — {v:.2f}ml")

    output = "\n".join(msg_lines)
    print(output)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"\n✅ 日报已保存至 {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
