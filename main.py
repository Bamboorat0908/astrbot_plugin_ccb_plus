# -- coding: utf-8 --
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp
from collections import deque
from astrbot.api import AstrBotConfig

import time
import json
import random
import os

# DATA_FILE = os.path.join(
#     os.getcwd(),
#     "data", "plugins", "astrbot_plugin_ccb_plus", "ccb.json"
# )

DATA_FILE = "data/ccb.json"

LOG_FILE = "data/ccb_log.json"

a1 = "id"       # qq号
a2 = "num"      # 北朝次数
a3 = "vol"      # 被注入量
a4 = "ccb_by"   # 被谁朝了
a5 = "max"      # 最大值
a6 = "climax"   # 绝顶次数

def get_avatar(user_id: str) -> bytes:
    return f"https://q4.qlogo.cn/headimg_dl?dst_uin={user_id}&spec=640"

def makeit(group_data, target_user_id):
    return 1 if any(item.get(a1) == target_user_id for item in group_data) else 2

@register("ccb", "Koikokokokoro", "和群友赛博sex的插件PLUS", "1.1.4")
class ccb(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.ban_duration = config.get("yw_ban_duration")      # 禁用时长（秒）
        self.yw_reset_timeout = config.get("yw_reset_timeout")  # 连续ccb计数重置时间（秒）
        self.ban_list = {}
        self.ccb_counts = {}  # actor_id -> 连续ccb次数（用于逐级递进概率）
        self.ccb_last_time = {}  # actor_id -> 上次ccb时间戳
        self.white_list  = config.get("white_list")
        self.selfdo = self.config.get("self_ccb", False)         # 0721 默认为否
        self.crit_prob  =   self.config.get("crit_prob")
        self.is_log =   self.config.get("is_log")           # 完整日志，默认为false
        self.struggle_fails = {}  # "actor_id:target_id" -> True，记录挣脱事件
        self.special_struggle_count = {}  # "actor_id:target_id" -> 针对特殊用户的ccb次数
        self.climax_cooldown = {}  # target_user_id -> 冷却结束时间戳（30min绝顶冷却）
        self.combo_data = {}  # "actor:target" -> {"count": N, "time": timestamp}
        self.cooldown_attempts = {}  # "actor_id:target_id" -> 冷却期间尝试ccb的次数
        self.actor_daily = {}  # "actor_id:YYYY-MM-DD" -> ccb_count (每日统计)
        # 群ccb开关，默认全开，存储被禁用的群号
        self._disabled_groups = set()
        # 成就定义
        self.achievement_defs = [
            {"id": "first_ccb", "name": "初体验", "icon": "🐣", "desc": "第一次ccb成功"},
            {"id": "combo_master", "name": "连击大师", "icon": "🔥", "desc": "连击数达到7"},
            {"id": "climax_master", "name": "绝顶高手", "icon": "💀", "desc": "累计让别人绝顶20次"},
            {"id": "climax_fish", "name": "绝顶杂鱼", "icon": "🧹", "desc": "累计被绝顶10次"},
            {"id": "conqueror", "name": "征服者", "icon": "💪", "desc": "累计ccb成功50次"},
            {"id": "perpetual", "name": "永动机", "icon": "♾️", "desc": "连击≥3时触发再战"},
            {"id": "all_achievements", "name": "全成就", "icon": "🌟", "desc": "解锁以上全部成就"},
        ]

    def _calc_yw_prob(self, count):
        """计算逐级递进养胃概率：min(0.02 × count², 1.0)"""
        return min(0.02 * (count ** 2), 1.0)

    def read_data(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"读取数据错误: {e}")
        return {}

    def write_data(self, data):
        try:
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入数据错误: {e}")

    # 记录日志
    def append_log(self, group_id: str, executor_id: str, target_id: str, duration: float, vol: float):
        """
        记录日志
        """
        try:
            # 读取日志
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'r', encoding='utf-8') as lf:
                    try:
                        logs = json.load(lf)
                        if not isinstance(logs, list):
                            logs = []
                    except Exception:
                        logs = []
            else:
                logs = []

            # 追加日志内容（修复：记录真实时间戳）
            entry = {
                "group": group_id,
                "executor": executor_id,
                "target": target_id,
                "duration": duration,
                "vol": str(round(float(vol), 2)),
                "timestamp": time.time()
            }
            logs.append(entry)

            # 写回
            with open(LOG_FILE, 'w', encoding='utf-8') as lf:
                json.dump(logs, lf, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"append_log 失败: {e}")

    @filter.command("ccb")
    async def ccb(self, event: AstrMessageEvent):
        """
        ccb，顾名思义，用来ccb
        用法： ccb [@]
        """
        import time, random

        group_id = str(event.get_group_id())
        send_id = str(event.get_sender_id())
        self_id = str(event.get_self_id())
        actor_id = send_id
        now = time.time()

        # 检查群ccb开关
        if group_id in self._disabled_groups:
            yield event.plain_result("本群已禁用ccb喵～")
            return

        # 检查是否在禁用期内
        ban_end = self.ban_list.get(actor_id, 0)
        if now < ban_end:
            remain = int(ban_end - now)
            m, s = divmod(remain, 60)
            yield event.plain_result(f"嘻嘻，你已经一滴不剩了，养胃还剩 {m}分{s}秒")
            return

        # ====== 逐级递进养胃概率 ======
        # 检查是否需要重置计数
        last_time = self.ccb_last_time.get(actor_id, 0)
        if now - last_time > self.yw_reset_timeout:
            self.ccb_counts[actor_id] = 0  # 超时重置

        # 获取当前连续次数并计算概率
        current_count = self.ccb_counts.get(actor_id, 0)
        yw_prob = self._calc_yw_prob(current_count)

        # 掷骰子判定养胃
        import random as _rand
        if _rand.random() < yw_prob:
            self.ban_list[actor_id] = now + self.ban_duration
            self.ccb_counts[actor_id] = 0  # 养胃后重置
            yield event.plain_result(f"💥 你的牛牛在第{current_count + 1}次ccb后炸膛了！养胃{self.ban_duration // 60}分钟（概率{yw_prob:.0%}）")
            return

        # 找到 @ 的目标，否则默认自己
        target_user_id = next(
            (str(seg.qq) for seg in event.get_messages()
             if isinstance(seg, Comp.At) and str(seg.qq) != self_id),
            send_id
        )

        if target_user_id in self.white_list:
            stranger_info = await event.bot.api.call_action(
                'get_stranger_info', user_id=target_user_id
            )
            nickname = stranger_info.get("nick", target_user_id)
            yield event.plain_result(f"{nickname} 是受保护的用户，不能 ccb")
            return

        if target_user_id == actor_id and not self.selfdo:
            yield event.plain_result("兄啊金箔怎么还能捅到自己的啊（恼）")
            return

        # ====== 绝顶冷却拦截 ======
        forced_ccb = False
        climax_end = self.climax_cooldown.get(target_user_id, 0)
        if now < climax_end:
            remain = int(climax_end - now)
            m, s = divmod(remain, 60)
            climax_msgs = [
                f"ta刚刚才绝顶过……♡ 身体还在轻轻颤抖，脸颊泛着红晕……稍微再等{m}分{s}秒，等余韵过去再碰她好不好～（/qzccb @xxx 可强制 ccb）",
                f"呜……绝顶的余韵还没散呢……♡ 整个人都还软软的、热热的，现在就碰的话会受不了的……再{m}分{s}秒就好喵～（/qzccb @xxx 可强制 ccb）",
                f"♡ 人家刚被送到顶峰……现在脑子里还一片空白，身体酥酥麻麻的……♡ 等{m}分{s}秒，让人家缓一缓再继续好不好～（/qzccb @xxx 可强制 ccb）",
                f"还、还在绝顶后的余韵里呢……♡ 感觉身体深处还在微微痉挛……♡ 再给{m}分{s}秒恢复一下嘛！（/qzccb @xxx 可强制 ccb）",
                f"♡ 刚被ccb到意识都要飞走了……现在还浑身软绵绵的……♡ 再{m}分{s}秒……等我能站稳了再……（/qzccb @xxx 可强制 ccb）",
                f"唔～ta刚被ccb到说不出话了喵……♡ 再{m}分{s}秒冷却，现在碰的话肯定会坏掉的～（/qzccb @xxx 可强制 ccb）",
                f"♡ ta还在绝顶的余韵里飘着呢……被ccb到脑子都融化了……再等{m}分{s}秒再继续喵～（/qzccb @xxx 可强制 ccb）",
                f"不行不行～ta刚刚才去了……♡ 现在连腰都是软的，碰一下就会漏出来……再{m}分{s}秒缓一缓！（/qzccb @xxx 可强制 ccb）",
                f"♡ 绝顶后的身体太敏感了……现在还一碰就发抖……让ta缓{m}分{s}秒再继续玩好不好喵～（/qzccb @xxx 可强制 ccb）",
                f"ta说再来的话会受不了的喵……♡ 冷却还剩{m}分{s}秒，让人家缓口气再来嘛！（/qzccb @xxx 可强制 ccb）",
            ]
            yield event.plain_result(random.choice(climax_msgs))
            return

        # 调用核心ccb逻辑
        async for result in self._ccb_core(event, group_id, send_id, self_id, actor_id, target_user_id, now, forced_ccb):
            yield result

    @filter.command("ccbswitch")
    async def ccb_switch(self, event: AstrMessageEvent):
        """
        开关某个群的ccb权限，需要管理员权限
        用法： ccbswitch on/off
        """
        group_id = str(event.get_group_id())
        args = event.get_message_str().strip().split()
        if len(args) < 2:
            yield event.plain_result(f"用法：ccbswitch on/off  |  当前状态：{'已禁用' if group_id in self._disabled_groups else '已开启'}喵～")
            return
        
        action = args[1].lower()
        if action == "off":
            if group_id in self._disabled_groups:
                yield event.plain_result("本群已经禁用ccb了喵……")
            else:
                self._disabled_groups.add(group_id)
                yield event.plain_result("本群ccb已关闭喵，想开了再叫我～ &&sigh&&")
        elif action == "on":
            if group_id not in self._disabled_groups:
                yield event.plain_result("本群ccb本来就是开启的喵～")
            else:
                self._disabled_groups.discard(group_id)
                yield event.plain_result("本群ccb已重新开启喵，尽情玩耍吧 &&happy&&")
        else:
            yield event.plain_result("参数错误喵，用 on 或 off 啦～")

    @filter.command("qzccb")
    async def qzccb(self, event: AstrMessageEvent):
        """
        强制ccb，100%触发绝顶+长文案
        用法： qzccb [@]
        """
        import time, random

        group_id = str(event.get_group_id())
        send_id = str(event.get_sender_id())
        self_id = str(event.get_self_id())
        actor_id = send_id
        now = time.time()

        # 检查群ccb开关
        if group_id in self._disabled_groups:
            yield event.plain_result("本群已禁用ccb喵～")
            return

        # 检查是否在禁用期内
        ban_end = self.ban_list.get(actor_id, 0)
        if now < ban_end:
            remain = int(ban_end - now)
            m, s = divmod(remain, 60)
            yield event.plain_result(f"嘻嘻，你已经一滴不剩了，养胃还剩 {m}分{s}秒")
            return

        # ====== 逐级递进养胃概率 ======
        # 检查是否需要重置计数
        last_time = self.ccb_last_time.get(actor_id, 0)
        if now - last_time > self.yw_reset_timeout:
            self.ccb_counts[actor_id] = 0  # 超时重置

        # 获取当前连续次数并计算概率
        current_count = self.ccb_counts.get(actor_id, 0)
        yw_prob = self._calc_yw_prob(current_count)

        # 掷骰子判定养胃
        import random as _rand
        if _rand.random() < yw_prob:
            self.ban_list[actor_id] = now + self.ban_duration
            self.ccb_counts[actor_id] = 0  # 养胃后重置
            yield event.plain_result(f"💥 强制ccb在第{current_count + 1}次后炸膛了！养胃{self.ban_duration // 60}分钟（概率{yw_prob:.0%}）")
            return

        # 找到 @ 的目标
        target_user_id = next(
            (str(seg.qq) for seg in event.get_messages()
             if isinstance(seg, Comp.At) and str(seg.qq) != self_id),
            send_id
        )

        if target_user_id in self.white_list:
            stranger_info = await event.bot.api.call_action(
                'get_stranger_info', user_id=target_user_id
            )
            nickname = stranger_info.get("nick", target_user_id)
            yield event.plain_result(f"{nickname} 是受保护的用户，不能 ccb")
            return

        if target_user_id == actor_id and not self.selfdo:
            yield event.plain_result("兄啊金箔怎么还能捅到自己的啊（恼）")
            return

        # ====== 发送强制ccb前缀 ======
        yield event.chain_result([
            Comp.At(qq=actor_id),
            Comp.Plain(random.choice([
                " ♡ 强制指令已受理……♡ 用这个指令的话，可就要做好觉悟了……♡ 不管对方是谁，都会彻底招待到底哦……",
                " ♡ 强制模式启动……♡ 让你见识一下，被送到顶点的人会露出什么样的表情吧……",
                " ♡ 既然你选择了「强制」……♡ 那就不留情面了——♡ 准备好沉沦了吗？",
                " ♡ 用/qzccb的话……♡ 就要负责到底哦……♡ 对方的一切反应，都是你的责任了……",
                " ♡ 强制指令已确认……♡ 100% 会把你送到那个地方去……♡ 逃不掉的……♡ 好好感受吧……",
                " ♡ 强制ccb启动——♡ 冷却什么的都无所谓了……♡ 既然你发出了这个指令，就让你看到ta最不堪的样子……",
                " ♡ qzccb已受理……♡ 这是强制性的——♡ ta会彻底坏掉，而你将被那份反应填满……♡ 准备好了吗？",
                " ♡ 强制模式on……♡ 对方会100%被送到绝顶的顶峰……♡ 那颤抖的声音和身体，都是你的所有物……♡ 尽情享用吧……",
                " ♡ 哼……♡ 你发出了强制指令呢……♡ 那就不客气了——♡ 让ta体验一下真正无法抵抗的顶峰吧……",
                " ♡ 强制指令执行——♡ 这可是有代价的……♡ 你准备好承担对方绝顶后潮红的脸和呜咽声了吗？♡ 那就开始吧……",
            ]))
        ])

        # 调用核心ccb逻辑（强制模式）
        async for result in self._ccb_core(event, group_id, send_id, self_id, actor_id, target_user_id, now, forced_ccb=True):
            yield result

    async def _ccb_core(self, event, group_id, send_id, self_id, actor_id, target_user_id, now, forced_ccb):
        """ccb核心逻辑：挣脱→连击→概率→ccb→绝顶→保存"""
        import time, random

        # ====== 挣脱事件判定 ======
        struggle_key = f"{actor_id}:{target_user_id}"
        struggle_revenge = False

        # 特殊用户 743901524 的专属挣脱机制
        SPECIAL_USER = "743901524"
        if target_user_id == SPECIAL_USER:
            sc = self.special_struggle_count.get(struggle_key, 0) + 1
            self.special_struggle_count[struggle_key] = sc

            if sc == 1:
                struggle_prob = 1.0    # 第1次：100%挣脱
            elif sc == 2:
                struggle_prob = 0.5    # 第2次：50%挣脱
            elif sc == 3:
                struggle_prob = 0.3    # 第3次：30%挣脱
            else:
                struggle_prob = 0.0    # 第4次及以后：必中

            struggle_fail = random.random() < struggle_prob
        else:
            # 普通用户：5%概率挣脱
            struggle_fail = random.random() < 0.05
            if struggle_key in self.struggle_fails:
                del self.struggle_fails[struggle_key]
                struggle_revenge = True

        if struggle_fail and not struggle_revenge:
            # 挣脱成功，ccb失败
            self.struggle_fails[struggle_key] = True
            yield event.chain_result([
                Comp.At(qq=actor_id),
                Comp.Plain("，没能顺利得手呢……"),
                Comp.At(qq=target_user_id),
                Comp.Plain(" 轻轻躲开了"),
                Comp.At(qq=actor_id),
                Comp.Plain(" 的攻势，微微侧过头，嘴角带着一丝狡黠的笑意——「还差得远呢」")
            ])
            return

        if struggle_revenge:
            # 上次挣脱失败，这次先放嘲讽再正常ccb
            yield event.chain_result([
                Comp.Plain("「上次让你逃掉了……这次可不会了哦」——♡ 带着略带报复的笑容，温柔却不容抗拒地贴近……")
            ])

        # ====== 连击判定 ======
        combo_key = f"{actor_id}:{target_user_id}"
        last_entry = self.combo_data.get(combo_key)
        if last_entry and (now - last_entry["time"]) < 1800:
            combo_count = last_entry["count"] + 1
        else:
            combo_count = 1
        self.combo_data[combo_key] = {"count": combo_count, "time": now}

        # 根据连击调整绝顶概率
        # 特殊用户：竹鼠HoYo(743901524) 初始概率更高
        if target_user_id == "743901524":
            if combo_count >= 7:
                climax_prob = 1.0
            elif combo_count >= 5:
                climax_prob = 0.55
            elif combo_count >= 3:
                climax_prob = 0.40
            else:
                climax_prob = 0.50
        else:
            if combo_count >= 7:
                climax_prob = 1.0  # 必触发
            elif combo_count >= 5:
                climax_prob = 0.35
            elif combo_count >= 3:
                climax_prob = 0.25
            else:
                climax_prob = 0.20

        # 强制ccb时必绝顶，且用长文案
        if forced_ccb:
            climax_prob = 1.0
            climax_long = True
        else:
            climax_long = False

        # CCB 逻辑
        duration = round(random.uniform(1, 60), 2)
        V = round(random.uniform(1, 100), 2)
        prob = self.crit_prob
        crit = False
        is_log = self.is_log
        if random.random() < prob:
            V = round(V * 2, 2)
            crit = True
        pic = get_avatar(target_user_id)

        all_data = self.read_data()
        group_data = all_data.get(group_id, [])

        mode = makeit(group_data, target_user_id)
        if mode == 1:
            # 已有记录，更新
            try:
                for item in group_data:
                    if item.get(a1) == target_user_id:
                        # 获取昵称
                        nickname = target_user_id
                        if event.get_platform_name() == "aiocqhttp":
                            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import                                 AiocqhttpMessageEvent
                            assert isinstance(event, AiocqhttpMessageEvent)
                            stranger_info = await event.bot.api.call_action(
                                'get_stranger_info', user_id=target_user_id
                            )
                            nickname = stranger_info.get("nick", nickname)

                        # 更新 num / vol / ccb_by
                        item[a2] = int(item.get(a2, 0)) + 1
                        item[a3] = round(float(item.get(a3, 0)) + V, 2)

                        # 添加逻辑：记录max值的产生者
                        ccb_by = item.get(a4, {}) or {}
                        if send_id in ccb_by:
                            ccb_by[send_id]["count"] = ccb_by[send_id].get("count", 0) + 1
                            ccb_by[send_id]["first"] = ccb_by[send_id].get("first", False)
                        else:
                            ccb_by[send_id] = {"count": 1, "first": False, "max": False}

                        # 添加逻辑：记录max值

                        # 计算max
                        raw_prev = item.get(a5, None)
                        prev_max = 0.0
                        if raw_prev is not None:
                            try:
                                prev_max = float(raw_prev)
                            except (TypeError, ValueError):
                                prev_max = 0.0
                        # 如果不存在合法的 max，使用平均值
                        if prev_max == 0.0:
                            try:
                                total_vol = float(item.get(a3, 0))
                                total_num = int(item.get(a2, 0))
                                if total_num > 0:
                                    prev_max = round(total_vol / total_num, 2)
                                else:
                                    prev_max = 0.0
                            except Exception:
                                prev_max = 0.0

                        if float(V) > prev_max:
                            item[a5] = round(float(V), 2)
                            for k in ccb_by:
                                ccb_by[k]["max"] = False
                            ccb_by[send_id]["max"] = True
                        else:
                            for k in ccb_by:
                                if "max" not in ccb_by[k]:
                                    ccb_by[k]["max"] = False

                        item[a4] = ccb_by

                        if crit:
                            # 连击文案
                            combo_msg = ""
                            if combo_count >= 7:
                                combo_msg = random.choice([
                                    f"♡ ♡ ♡ 第{combo_count}连……分不清现实与梦境的边界了……♡ 整个人都被你的温度填满……意识在甘美的漩涡中融化……已经……回不去了……♡ ♡ ♡",
                                    f"♡ ♡ ♡ 第{combo_count}连……♡ 灵魂都被你抽走了……身体不再属于自己……每一次冲击都让脚尖绷直、眼前发白……♡ ♡ ♡ 已经……彻底是你的形状了……",
                                    f"♡ ♡ ♡ 第{combo_count}连了……♡ 全身的每一寸都记住了你的节奏……♡ 感觉快要坏掉了……但是停不下来……♡ ♡ ♡ 继续……把我弄坏也可以的……请继续……♡",
                                    f"♡ ♡ ♡ 第{combo_count}连……♡ 视野在破碎重组……♡ 每一次都被贯穿得更深……身体变得好奇怪……♡ ♡ ♡ 我已经……分不清哪里是界限了……好舒服……♡",
                                    f"♡ ♡ ♡ 第{combo_count}次了……♡ 脑子里全是白色的泡泡……♡ 被反复送上去又拉回来……♡ ♡ ♡ 我已经……不再是原来的我了……是你的人偶……是你的东西……♡",
                                ])
                            elif combo_count >= 5:
                                combo_msg = random.choice([
                                    f"♡ ♡ 第{combo_count}连……脑海里只剩下你的触感……♡ 身体擅自记住了节奏……明明应该抗拒的……却不由自主地迎合上去……♡ ♡",
                                    f"♡ ♡ 第{combo_count}连了……♡ 身体深处有什么东西在悄悄改变……♡ 每一下都带起一阵酥麻……我已经……开始期待下一次了……♡ ♡",
                                    f"♡ ♡ 第{combo_count}连……♡ 耳朵好热……心跳好吵……♡ 明明应该累了的……身体却越发敏感……♡ 再这样下去真的会坏掉的……但是……不想停下……♡ ♡",
                                    f"♡ ♡ 第{combo_count}连持续中……♡ 腰在发抖……呼吸变得好浅……♡ 每一次冲击都让视线模糊一点……♡ 好舒服……脑袋变得轻飘飘的……♡ ♡",
                                    f"♡ ♡ 第{combo_count}了……♡ 连思考都变得困难……♡ 只知道你的温度和你的存在……♡ 身体已经自作主张地开始回应了……真丢人……但是又很幸福……♡ ♡",
                                ])
                            elif combo_count >= 3:
                                combo_msg = random.choice([
                                    f"♡ 第{combo_count}次了……身体微微颤抖着……♡ 被反复送到边缘又拉回来……好舒服……脑袋变得好奇怪……♡",
                                    f"♡ 第{combo_count}次……♡ 热度在身体里堆积……♡ 每一次都让呼吸变得更急促一点……♡ 意识开始变得朦朦胧胧……好舒服……",
                                    f"♡ 第{combo_count}次了喵……♡ 身体开始记住你的节奏了……♡ 连膝盖都在轻轻打颤……♡ 但是……还想要更多……♡",
                                    f"♡ 第{combo_count}次……♡ 被连续ccb到意识开始模糊……♡ 身体酥酥麻麻的……好像泡在温暖的水里一样……♡ 好安心……好舒服……",
                                    f"♡ 第{combo_count}次了……♡ 尾椎骨传来一阵阵酥麻……♡ 明明才刚结束……身体深处又开始期待了……♡ 好奇怪……但是不想停下来……♡",
                                ])
                            chain = [
                                Comp.Plain(combo_msg),
                                Comp.At(qq=send_id),
                                Comp.Plain(" 和 "),
                                Comp.At(qq=target_user_id),
                                Comp.Plain(f"发生了{duration}min长的ccb行为，"),
                                Comp.At(qq=send_id),
                                Comp.Plain("向"),
                                Comp.At(qq=target_user_id),
                                Comp.Plain(f"注入了 💥 暴击！{V:.2f}ml的生命因子"),
                                Comp.Image.fromURL(pic),
                                Comp.Plain(f"这是"),
                                Comp.At(qq=target_user_id),
                                Comp.Plain(f"的第{item[a2]}次，请好好爱惜 ta 喵")
                            ]
                        else:
                            # 发送结果
                            # 连击文案
                            combo_msg = ""
                            if combo_count >= 7:
                                combo_msg = random.choice([
                                    f"♡ ♡ ♡ 第{combo_count}连……分不清现实与梦境的边界了……♡ 整个人都被你的温度填满……意识在甘美的漩涡中融化……已经……回不去了……♡ ♡ ♡",
                                    f"♡ ♡ ♡ 第{combo_count}连……♡ 灵魂都被你抽走了……身体不再属于自己……每一次冲击都让脚尖绷直、眼前发白……♡ ♡ ♡ 已经……彻底是你的形状了……",
                                    f"♡ ♡ ♡ 第{combo_count}连了……♡ 全身的每一寸都记住了你的节奏……♡ 感觉快要坏掉了……但是停不下来……♡ ♡ ♡ 继续……把我弄坏也可以的……请继续……♡",
                                    f"♡ ♡ ♡ 第{combo_count}连……♡ 视野在破碎重组……♡ 每一次都被贯穿得更深……身体变得好奇怪……♡ ♡ ♡ 我已经……分不清哪里是界限了……好舒服……♡",
                                    f"♡ ♡ ♡ 第{combo_count}次了……♡ 脑子里全是白色的泡泡……♡ 被反复送上去又拉回来……♡ ♡ ♡ 我已经……不再是原来的我了……是你的人偶……是你的东西……♡",
                                ])
                            elif combo_count >= 5:
                                combo_msg = random.choice([
                                    f"♡ ♡ 第{combo_count}连……脑海里只剩下你的触感……♡ 身体擅自记住了节奏……明明应该抗拒的……却不由自主地迎合上去……♡ ♡",
                                    f"♡ ♡ 第{combo_count}连了……♡ 身体深处有什么东西在悄悄改变……♡ 每一下都带起一阵酥麻……我已经……开始期待下一次了……♡ ♡",
                                    f"♡ ♡ 第{combo_count}连……♡ 耳朵好热……心跳好吵……♡ 明明应该累了的……身体却越发敏感……♡ 再这样下去真的会坏掉的……但是……不想停下……♡ ♡",
                                    f"♡ ♡ 第{combo_count}连持续中……♡ 腰在发抖……呼吸变得好浅……♡ 每一次冲击都让视线模糊一点……♡ 好舒服……脑袋变得轻飘飘的……♡ ♡",
                                    f"♡ ♡ 第{combo_count}了……♡ 连思考都变得困难……♡ 只知道你的温度和你的存在……♡ 身体已经自作主张地开始回应了……真丢人……但是又很幸福……♡ ♡",
                                ])
                            elif combo_count >= 3:
                                combo_msg = random.choice([
                                    f"♡ 第{combo_count}次了……身体微微颤抖着……♡ 被反复送到边缘又拉回来……好舒服……脑袋变得好奇怪……♡",
                                    f"♡ 第{combo_count}次……♡ 热度在身体里堆积……♡ 每一次都让呼吸变得更急促一点……♡ 意识开始变得朦朦胧胧……好舒服……",
                                    f"♡ 第{combo_count}次了喵……♡ 身体开始记住你的节奏了……♡ 连膝盖都在轻轻打颤……♡ 但是……还想要更多……♡",
                                    f"♡ 第{combo_count}次……♡ 被连续ccb到意识开始模糊……♡ 身体酥酥麻麻的……好像泡在温暖的水里一样……♡ 好安心……好舒服……",
                                    f"♡ 第{combo_count}次了……♡ 尾椎骨传来一阵阵酥麻……♡ 明明才刚结束……身体深处又开始期待了……♡ 好奇怪……但是不想停下来……♡",
                                ])
                            chain = [
                                Comp.Plain(combo_msg),
                                Comp.At(qq=send_id),
                                Comp.Plain(" 和 "),
                                Comp.At(qq=target_user_id),
                                Comp.Plain(f"发生了{duration}min长的ccb行为，"),
                                Comp.At(qq=send_id),
                                Comp.Plain("向"),
                                Comp.At(qq=target_user_id),
                                Comp.Plain(f"注入了{V:.2f}ml的生命因子"),
                                Comp.Image.fromURL(pic),
                                Comp.Plain(f"这是"),
                                Comp.At(qq=target_user_id),
                                Comp.Plain(f"的第{item[a2]}次，请好好爱惜 ta 喵")
                            ]
                        yield event.chain_result(chain)

                        # ====== 绝顶判定 ======
                        if random.random() < climax_prob:
                            if climax_long:
                                climax_msgs = [
                                    f"♡ 哈啊……♡ 到、到头了喵……被强制ccb到灵魂都要飞出去了……♡ 浑身都在发抖……已经分不清是痛苦还是快乐了……♡ 全部……全部都被填满了……♡ 谢谢款待喵……♡",
                                    f"♡ 呜……♡ 太、太深了喵……♡ 被强制玩坏掉了……脑袋一片空白……腰完全使不上力气了……♡ 但是……好舒服……♡ 再多来一点也可以喵……♡",
                                    f"♡ 嗯啊啊……♡ 强制ccb什么的太超过了……♡ 身体和心里都变得乱七八糟的……♡ 已经……回不去了喵……♡ 但是……如果是你的话……我愿意……♡",
                                    f"♡ 停、停不下来……♡ 强制到什么羞耻的念头都被ccb出来了……♡ 人家已经……完全变成你的形状了喵……♡ 还要……还要更多……♡ 请继续ccb我喵……♡",
                                    f"♡ 唔唔……♡ 被强制ccb到意识都要融化了……♡ 全身都好热……好奇怪……♡ 已经……什么都想不起来了……♡ 只想被你继续注入……♡ 我是你的了喵……♡",
                                    f"♡ 又、又去了……♡ 被强制ccb到彻底坏掉了……♡ 身体像坏掉的水龙头一样关不上……♡ 意识已经飞到天花板上面了……♡ 全部……都是你给的感觉……好幸福……♡",
                                    f"♡ 啊啊啊……♡ 到这里了……♡ 强制绝顶的感觉太过分了……♡ 脑袋里炸开了好多好多星星……♡ 身体不听话地在发抖……♡ 但是……好喜欢……♡ 被你这样对待最喜欢了……♡",
                                    f"♡ 不行了喵……♡ 真的不行了……♡ 强制ccb到连尾巴尖都在发麻……♡ 从脊椎一直酥到头顶……♡ 感觉整个人都变成了一滩水……♡ 但是……你还没有结束对吧……♡ 那就继续……♡ 我受得了……♡",
                                    f"♡ ♡ 绝顶了……♡ 被强制送到顶端的时候，世界都安静了一秒……♡ 剩下的只有你的温度和你的味道……♡ 身体深处的某个东西被打开了……♡ 已经——完全无法离开你了喵……♡",
                                    f"♡ 到、到了……♡ 被强制ccb到坏掉了……♡ 视野里一片白花花……♡ 耳朵里全是自己心跳的声音……♡ 好大声……好丢人……♡ 但是……请你再多看看我这个样子……♡ 我想被你记住……♡",
                                ]
                            else:
                                climax_msgs = [
                                    f"……♡ 嗯啊～到、到了……绝顶了喵……♡ 被ccb到整个人都软绵绵的，完全使不上力气了……",
                                    f"♡ 被ccb到浑身发抖……去了……♡ 脑袋一片空白，身体酥酥麻麻的，好舒服……",
                                    f"……呜♡ 太深了……已经……绝顶了喵……♡ 被灌得满满的，腰都直不起来了……",
                                    f"♡ 哈啊～♡ 到头了……去了去了……♡ 完全被ccb征服了，一点反抗的力气都没有了喵……",
                                    f"……唔♡ 不行了……被ccb到绝顶了……♡ 整个人都变得好奇怪，快要融化掉了……",
                                    f"♡ 已经……站不住了喵……♡ 被ccb到腿都软了……♡ 脑袋热乎乎的，好舒服……",
                                    f"♡ 绝顶了……♡ 脑子里全是你的形状……♡ 身体酥酥麻麻的，还在里面颤抖……",
                                    f"……♡ 去、去了喵……♡ 被ccb到整个人都坏掉了……♡ 好幸福……好舒服……不想醒来……",
                                    f"♡ 到了……♡ 完全到了……♡ 被灌得满满的，肚子里面好热……♡ 谢谢你……♡",
                                    f"♡ 呜……♡ 绝顶了……♡ 身体变得好奇怪……♡ 明明想忍住但还是被你弄到去了……♡ 太舒服了喵……",
                                ]
                            item[a6] = int(item.get(a6, 0)) + 1
                            cooldown = 900 if target_user_id == "743901524" else 1800
                            self.climax_cooldown[target_user_id] = now + cooldown
                            yield event.chain_result([
                                Comp.At(qq=target_user_id),
                                Comp.Plain(f" {random.choice(climax_msgs)}")
                            ])

                        # 是否保留完整日志
                        if is_log:
                            try:
                                self.append_log(group_id, send_id, target_user_id, duration, V)
                            except Exception as e:
                                logger.warning(f"记录日志失败: {e}")

                        # 写回数据
                        all_data[group_id] = group_data
                        self.write_data(all_data)

                        # ====== 成就检测 ======
                        new_achs = self._check_achievements(all_data, send_id, combo_count, struggle_revenge, group_id)
                        for a in new_achs:
                            yield event.chain_result([
                                Comp.At(qq=send_id),
                                Comp.Plain(f" 🎉 解锁成就【{a['icon']} {a['name']}】！{a['desc']}")
                            ])
                        if new_achs:
                            self.write_data(all_data)

                        # 更新连续ccb计数（成功后+1）
                        self.ccb_counts[actor_id] = self.ccb_counts.get(actor_id, 0) + 1
                        self.ccb_last_time[actor_id] = now


                        return
            except Exception as e:
                logger.error(f"报错: {e}")
                yield event.plain_result("对方拒绝了和你ccb")
                return

        else:
            # 新记录
            try:
                nickname = target_user_id
                if event.get_platform_name() == "aiocqhttp":
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    assert isinstance(event, AiocqhttpMessageEvent)
                    stranger_info = await event.bot.api.call_action(
                        'get_stranger_info', user_id=target_user_id
                    )
                    nickname = stranger_info.get("nick", nickname)

                # 连击文案
                combo_msg = ""
                if combo_count >= 7:
                    combo_msg = random.choice([
                        f"♡ ♡ ♡ 第{combo_count}连……分不清现实与梦境的边界了……♡ 整个人都被你的温度填满……意识在甘美的漩涡中融化……已经……回不去了……♡ ♡ ♡",
                        f"♡ ♡ ♡ 第{combo_count}连……♡ 灵魂都被你抽走了……身体不再属于自己……每一次冲击都让脚尖绷直、眼前发白……♡ ♡ ♡ 已经……彻底是你的形状了……",
                        f"♡ ♡ ♡ 第{combo_count}连了……♡ 全身的每一寸都记住了你的节奏……♡ 感觉快要坏掉了……但是停不下来……♡ ♡ ♡ 继续……把我弄坏也可以的……请继续……♡",
                        f"♡ ♡ ♡ 第{combo_count}连……♡ 视野在破碎重组……♡ 每一次都被贯穿得更深……身体变得好奇怪……♡ ♡ ♡ 我已经……分不清哪里是界限了……好舒服……♡",
                        f"♡ ♡ ♡ 第{combo_count}次了……♡ 脑子里全是白色的泡泡……♡ 被反复送上去又拉回来……♡ ♡ ♡ 我已经……不再是原来的我了……是你的人偶……是你的东西……♡",
                    ])
                elif combo_count >= 5:
                    combo_msg = random.choice([
                        f"♡ ♡ 第{combo_count}连……脑海里只剩下你的触感……♡ 身体擅自记住了节奏……明明应该抗拒的……却不由自主地迎合上去……♡ ♡",
                        f"♡ ♡ 第{combo_count}连了……♡ 身体深处有什么东西在悄悄改变……♡ 每一下都带起一阵酥麻……我已经……开始期待下一次了……♡ ♡",
                        f"♡ ♡ 第{combo_count}连……♡ 耳朵好热……心跳好吵……♡ 明明应该累了的……身体却越发敏感……♡ 再这样下去真的会坏掉的……但是……不想停下……♡ ♡",
                        f"♡ ♡ 第{combo_count}连持续中……♡ 腰在发抖……呼吸变得好浅……♡ 每一次冲击都让视线模糊一点……♡ 好舒服……脑袋变得轻飘飘的……♡ ♡",
                        f"♡ ♡ 第{combo_count}了……♡ 连思考都变得困难……♡ 只知道你的温度和你的存在……♡ 身体已经自作主张地开始回应了……真丢人……但是又很幸福……♡ ♡",
                    ])
                elif combo_count >= 3:
                    combo_msg = random.choice([
                        f"♡ 第{combo_count}次了……身体微微颤抖着……♡ 被反复送到边缘又拉回来……好舒服……脑袋变得好奇怪……♡",
                        f"♡ 第{combo_count}次……♡ 热度在身体里堆积……♡ 每一次都让呼吸变得更急促一点……♡ 意识开始变得朦朦胧胧……好舒服……",
                        f"♡ 第{combo_count}次了喵……♡ 身体开始记住你的节奏了……♡ 连膝盖都在轻轻打颤……♡ 但是……还想要更多……♡",
                        f"♡ 第{combo_count}次……♡ 被连续ccb到意识开始模糊……♡ 身体酥酥麻麻的……好像泡在温暖的水里一样……♡ 好安心……好舒服……",
                        f"♡ 第{combo_count}次了……♡ 尾椎骨传来一阵阵酥麻……♡ 明明才刚结束……身体深处又开始期待了……♡ 好奇怪……但是不想停下来……♡",
                    ])
                chain = [
                    Comp.Plain(combo_msg),
                    Comp.At(qq=send_id),
                    Comp.Plain(" 和 "),
                    Comp.At(qq=target_user_id),
                    Comp.Plain(f"发生了{duration}min长的ccb行为，"),
                    Comp.At(qq=send_id),
                    Comp.Plain("向"),
                    Comp.At(qq=target_user_id),
                    Comp.Plain(f"注入了{V:.2f}ml的生命因子"),
                    Comp.Image.fromURL(pic),
                    Comp.Plain(f"这是"),
                    Comp.At(qq=target_user_id),
                    Comp.Plain("的初体验，请好好爱惜 ta 喵")
                ]
                yield event.chain_result(chain)

                # ====== 绝顶判定 ======
                climax_hit = False
                if random.random() < climax_prob:
                    if climax_long:
                        climax_msgs = [
                            f"♡ 啊啊……到、到了……♡ 被强制送到顶峰的感觉……像是整个人都被贯穿了一样……♡ 视野渐渐模糊，只剩下你的温度在身体里蔓延……♡ 我……好像在融化……♡ 好温暖……好舒服……已经……不想停下来了……♡",
                            f"♡ 不行了……真的不行了……♡ 身体深处有什么东西碎掉了……♡ 酥麻感从脊椎一直窜到头顶……♡ 明明应该很羞耻的……♡ 可是……可是……好舒服……♡ 眼泪都要出来了……♡ 全都是你的形状了……♡",
                            f"♡ 呜……♡ 被强制ccb到连思考都停止了……♡ 世界在旋转……♡ 只有被你触碰的地方在发烫……♡ 从身体深处涌上来的感觉……♡ 好可怕……又好幸福……♡ 我……好像变得不是自己了……♡ 可是……是你让我变成这样的……所以我……愿意……♡",
                            f"♡ 请、请等一下……♡ 啊……到了……♡ 强制绝顶什么的……太超过了……♡ 意识都要飞到天边去了……♡ 全身的每一寸皮肤都在感受着你……♡ 好热……♡ 好满……♡ 已经分不清哪里是我的边界了……♡ 我……正在成为你的一部分……♡",
                            f"♡ ♡ ♡ 到头了……♡ 被强制送上顶峰的那一刻……♡ 脑子里炸开了无数烟花……♡ 身体在痉挛……♡ 明明应该逃开的……却反而抱得更紧了……♡ 不要停……♡ 继续……♡ 把我彻底变成你的东西……♡ 拜托了……♡ 只有你可以……♡",
                            f"♡ 到、到了……♡ 强制ccb让第一次就这么激烈……♡ 视野在发白……♡ 全身都在痉挛……♡ 明明应该害怕的……可是你的温度让我好安心……♡ 第一次……就记住了你的味道……♡ 我已经……是你的东西了……♡",
                            f"♡ 啊啊……♡ 这就是……绝顶的感觉吗……♡ 被强制送上来的……但是好舒服……♡ 身体在发抖，心里却热热的……♡ 原来被人这样对待是这样的感觉……♡ 好可怕……又好幸福……♡ 再、再来一次也可以的……♡",
                            f"♡ 呜……♡ 太超过了……♡ 第一次就被强制ccb到这种地步……♡ 脑子里全是你的气息……♡ 身体深处还在轻轻抽搐……♡ 好丢人……但是……♡ 这是你给我的感觉……我会好好记住的……♡ 一辈子都忘不掉了……♡",
                            f"♡ ♡ 绝顶了……♡ 初体验就被强制送到了顶点……♡ 连一丝抵抗的余地都没有……♡ 就这么彻底被你占有了……♡ 身体里满满的都是你……♡ 好温暖……好安心……♡ 我……好幸福……第一次就给了你……太好了……♡",
                            f"♡ 哈啊……♡ 哈啊……♡ 到、到了那里了……♡ 被强制ccb到第一次就这么剧烈……♡ 眼角都湿了……♡ 但是并不是因为难过……♡ 而是因为被你这样珍视地对待……♡ 心里酸酸胀胀的……♡ 谢谢你让我体验到这种感觉……♡",
                        ]
                    else:
                        climax_msgs = [
                            f"♡ ……嗯啊♡ 到、到了……♡ 被温柔的浪潮推上顶峰……♡ 身体轻轻颤抖着，连指尖都酥麻了……♡ 好舒服……♡ 像是泡在热水中一样……♡",
                            f"♡ 哈啊……♡ 去了……♡ 脑袋里一片空白，只剩下暖暖的感觉在扩散……♡ 被ccb到整个人都软绵绵的……♡ 一点力气都使不上了……♡",
                            f"♡ ……呜♡ 太深了……♡ 感觉有什么东西满溢出来了……♡ 腰在发抖……♡ 但是……好幸福……♡ 又被你送到了顶点……♡ 谢谢你……♡",
                            f"♡ 啊……♡ 到头了……♡ 身子像羽毛一样轻飘飘的……♡ 完全被你征服了……♡ 一点反抗的念头都没有了……♡ 只想沉浸在这片余韵里……♡",
                            f"♡ ……不行了♡ 被ccb到好奇怪……♡ 身体变得好敏感……♡ 连呼吸都能触碰到快感……♡ 整个人都要融化在你的怀抱里了……♡ 好温暖……♡",
                            f"♡ 绝、绝顶了喵……♡ 初体验就被ccb到去了……♡ 好害羞但是又好舒服……♡ 身体还在轻轻地抽动……♡ 这就是……被你拥有的感觉吗……♡",
                            f"♡ 哈啊……♡ 到了……♡ 第一次就这么舒服……♡ 身体的深处好热……♡ 我还想……再多感受一点你的温度……♡",
                            f"♡ ……呜♡ 去了喵……♡ 初体验就绝顶了……♡ 好丢人但是……好幸福……♡ 脑子里全是你的味道……♡ 挥之不去了……♡",
                            f"♡ 到、到了……♡ 第一次就被ccb到浑身酥麻……♡ 眼角湿湿的但是心里好暖……♡ 谢谢你……♡ 把第一次给你真是太好了……♡",
                            f"♡ 嗯啊……♡ 绝顶了……♡ 初体验的感觉……这辈子都会记得的……♡ 你的温度……你的气息……♡ 全部都刻进身体里了……♡",
                        ]
                    climax_hit = True
                    cooldown = 900 if target_user_id == "743901524" else 1800
                    self.climax_cooldown[target_user_id] = now + cooldown
                    yield event.chain_result([
                        Comp.At(qq=target_user_id),
                        Comp.Plain(f" {random.choice(climax_msgs)}")
                    ])

                # 构造并保存新记录
                new_record = {
                    a1: target_user_id,
                    a2: 1,
                    a3: round(V, 2),
                    a4: {send_id: {"count": 1, "first": True, "max": True}},
                    a5: round(V, 2),
                    a6: 1 if climax_hit else 0
                }
                group_data.append(new_record)
                all_data[group_id] = group_data
                self.write_data(all_data)

                # ====== 成就检测 ======
                new_achs = self._check_achievements(all_data, send_id, combo_count, struggle_revenge, group_id)
                for a in new_achs:
                    yield event.chain_result([
                        Comp.At(qq=send_id),
                        Comp.Plain(f" 🎉 解锁成就【{a['icon']} {a['name']}】！{a['desc']}")
                    ])
                if new_achs:
                    self.write_data(all_data)

                # 是否保留完整日志
                if is_log:
                    try:
                        self.append_log(group_id, send_id, target_user_id, duration, V)
                    except Exception as e:
                        logger.warning(f"记录日志失败: {e}")

                # 更新连续ccb计数（成功后+1）
                self.ccb_counts[actor_id] = self.ccb_counts.get(actor_id, 0) + 1
                self.ccb_last_time[actor_id] = now


                return
            except Exception as e:
                logger.error(f"报错: {e}")
                yield event.plain_result("对方拒绝了和你ccb")
                return

    @filter.command("ccbtop")
    async def ccbtop(self, event: AstrMessageEvent):
        """
        按次数排行
        """
        group_id = str(event.get_group_id())
        group_data = self.read_data().get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        top5 = sorted(group_data, key=lambda x: int(x.get(a2, 0)), reverse=True)[:5]
        msg = "被ccb排行榜 TOP5：\n"
        for i, r in enumerate(top5, 1):
            uid = r[a1]
            nick = uid
            if event.get_platform_name() == "aiocqhttp":
                try:
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    stranger_info = await event.bot.api.call_action('get_stranger_info', user_id=uid)
                    nick = stranger_info.get("nick", nick)
                except:
                    pass
            msg += f"{i}. {nick} - 次数：{r[a2]}\n"
        yield event.plain_result(msg)

    @filter.command("ccbreport")
    async def ccb_report(self, event: AstrMessageEvent):
        """
        生成ccb全服统计报告图片
        用法：ccbreport
        """
        from PIL import Image, ImageDraw, ImageFont
        import os, json
        
        group_id = str(event.get_group_id())
        all_data = self.read_data()
        group_data = all_data.get(group_id, [])
        
        if not group_data:
            yield event.plain_result("本群暂无ccb记录喵～")
            return
        
        # 昵称映射
        nick_map = {}
        if event.get_platform_name() == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            for r in group_data:
                uid = r.get(a1, "")
                if uid not in nick_map:
                    try:
                        info = await event.bot.api.call_action('get_stranger_info', user_id=uid)
                        nick_map[uid] = info.get("nick", uid)
                    except:
                        nick_map[uid] = uid
        else:
            for r in group_data:
                nick_map[r.get(a1, "")] = r.get(a1, "")
        
        def get_name(uid):
            return nick_map.get(uid, uid)
        
        # 统计
        active = {}
        first_cnt = {}
        for r in group_data:
            for aid, info in r.get(a4, {}).items():
                active[aid] = active.get(aid, 0) + info.get("count", 0)
                if info.get("first"):
                    first_cnt[aid] = first_cnt.get(aid, 0) + 1
        
        total_users = len(group_data)
        total_ccb = sum(r.get(a2, 0) for r in group_data)
        total_vol = sum(r.get(a3, 0) for r in group_data)
        total_climax = sum(int(r.get(a6, 0)) for r in group_data)
        
        # 图片
        W, H = 1000, 1800
        img = Image.new("RGB", (W, H), (245, 245, 250))
        draw = ImageDraw.Draw(img)
        fp = "/tmp/wqy-microhei.ttc"
        
        F_TITLE = ImageFont.truetype(fp, 30)
        F_SEC = ImageFont.truetype(fp, 20)
        F_NUM = ImageFont.truetype(fp, 22)
        F_NAME = ImageFont.truetype(fp, 17)
        F_VAL = ImageFont.truetype(fp, 18)
        F_SM = ImageFont.truetype(fp, 14)
        F_XS = ImageFont.truetype(fp, 12)
        
        # Header
        draw.rounded_rectangle([(20,20),(W-20,110)], radius=16, fill=(40,60,120))
        draw.text((50, 38), "ccb+ 全服统计报告", fill=(255,215,80), font=F_TITLE)
        draw.text((50, 78), "VRChat 综合数据  |  ccb+ v1.1.4", fill=(180,200,230), font=F_SM)
        import datetime
        draw.text((W-220, 80), datetime.datetime.now().strftime("%Y/%m/%d %H:%M"), fill=(150,170,210), font=F_XS)
        
        # 总览卡片
        labels = [
            ("总人数", f"{total_users}", "人", (60,120,220)),
            ("总次数", f"{total_ccb}", "次", (50,170,110)),
            ("总注入", f"{total_vol:.0f}", "ml", (220,130,80)),
            ("绝顶", f"{total_climax}", "次", (200,100,170)),
        ]
        x0, y0, w0, h0, g0 = 40, 135, 220, 85, 13
        for i, (lab, val, unit, col) in enumerate(labels):
            x = x0 + i*(w0+g0)
            draw.rounded_rectangle([(x,y0),(x+w0,y0+h0)], radius=12, fill=(255,255,255), outline=col, width=2)
            draw.rounded_rectangle([(x+8,y0+8),(x+10,y0+h0-8)], radius=4, fill=col)
            draw.text((x+22, y0+10), lab, fill=(100,100,130), font=F_SM)
            draw.text((x+22, y0+42), val, fill=(30,30,50), font=F_NUM)
            draw.text((x+22+draw.textlength(val, font=F_NUM)+4, y0+52), unit, fill=(140,140,170), font=F_SM)
        
        # 排行数据
        top_ccb = sorted(group_data, key=lambda r: r.get(a2, 0), reverse=True)[:5]
        top_vol = sorted(group_data, key=lambda r: r.get(a3, 0), reverse=True)[:5]
        top_max = sorted(group_data, key=lambda r: r.get(a5, 0), reverse=True)[:5]
        top_climax = sorted(group_data, key=lambda r: int(r.get(a6, 0)), reverse=True)[:5]
        top_active = sorted(active.items(), key=lambda x: x[1], reverse=True)[:5]
        hail = {a: first_cnt.get(a,0)*2 + active[a] for a in active}
        hail_top = sorted(hail.items(), key=lambda x: x[1], reverse=True)[:5]
        xnn_list = [(r.get(a1,""), round(r.get(a2,0)*1+r.get(a3,0)*0.1-active.get(r.get(a1,""),0)*0.5,2)) for r in group_data]
        xnn_top = sorted(xnn_list, key=lambda x: x[1], reverse=True)[:5]
        
        def draw_rank(x, y, w, title, items, color):
            max_v = items[0][0] if items else 1
            draw.rounded_rectangle([(x,y),(x+w,y+38)], radius=10, fill=color)
            draw.text((x+14, y+8), title, fill=(255,255,255), font=F_SEC)
            y += 48
            for i, (val, name, txt) in enumerate(items):
                row_h = 42
                bg = (255,255,255) if i%2==0 else (250,250,253)
                draw.rounded_rectangle([(x,y),(x+w,y+row_h)], radius=8, fill=bg)
                if i == 0: draw.text((x+14, y+9), "#1", fill=(200,140,40), font=F_VAL)
                elif i == 1: draw.text((x+14, y+9), "#2", fill=(140,140,160), font=F_VAL)
                elif i == 2: draw.text((x+14, y+9), "#3", fill=(180,120,60), font=F_VAL)
                else: draw.text((x+20, y+10), f"#{i+1}", fill=(160,160,180), font=F_SM)
                nx = x + 60 if i < 3 else x + 52
                draw.text((nx, y+9), name, fill=(40,40,60), font=F_NAME)
                tw = draw.textlength(txt, font=F_VAL)
                draw.text((x+w-14-tw, y+9), txt, fill=(30,30,50), font=F_VAL)
                bar_s = x + 195
                bar_e = x + w - tw - 22
                bw = bar_e - bar_s
                if bw > 30:
                    ratio = val / max_v
                    filled = max(4, int(bw * ratio))
                    draw.rounded_rectangle([(bar_s,y+14),(bar_e,y+28)], radius=6, fill=(220,220,230))
                    draw.rounded_rectangle([(bar_s,y+14),(bar_s+filled,y+28)], radius=6, fill=color)
                y += row_h + 3
            return y + 10
        
        ccb_items = [(r.get(a2,0), get_name(r.get(a1,"")), f"{r.get(a2,0)}次") for r in top_ccb]
        vol_items = [(r.get(a3,0), get_name(r.get(a1,"")), f"{r.get(a3,0):.0f}ml") for r in top_vol]
        max_items = [(r.get(a5,0), get_name(r.get(a1,"")), f"{r.get(a5,0):.1f}ml") for r in top_max]
        climax_items = [(int(r.get(a6,0)), get_name(r.get(a1,"")), f"{int(r.get(a6,0))}次") for r in top_climax]
        act_items = [(c, get_name(a), f"{c}次") for a,c in top_active]
        hail_items = [(hail[a], get_name(a), f"海王值{hail[a]}") for a,_ in hail_top]
        xnn_items = [(x, get_name(u), f"XNN{x}") for u,x in xnn_top]
        
        cw = 440
        ly = 245
        ly = draw_rank(40, ly, cw, "被ccb次数 TOP5", ccb_items, (220,140,60))
        ly = draw_rank(40, ly, cw, "被注入量 TOP5", vol_items, (70,160,230))
        ly = draw_rank(40, ly, cw, "单次最大注入 TOP5", max_items, (160,110,230))
        ly = draw_rank(40, ly, cw, "绝顶次数 TOP5", climax_items, (200,100,170))
        ry = 245
        ry = draw_rank(40+cw+40, ry, cw, "主动出击 TOP5", act_items, (220,100,100))
        ry = draw_rank(40+cw+40, ry, cw, "海王值 TOP5", hail_items, (220,180,50))
        ry = draw_rank(40+cw+40, ry, cw, "小南梁XNN TOP5", xnn_items, (70,190,140))
        
        fy = max(ly, ry) + 15
        draw.line([(40,fy),(W-40,fy)], fill=(200,200,215), width=1)
        # 指令提示框
        box_y = fy + 8
        draw.rounded_rectangle([(40,box_y),(W-40,box_y+50)], radius=10, fill=(40,60,120), outline=(40,60,120), width=2)
        draw.text((60, box_y+10), "📋 指令提示", fill=(255,255,255), font=F_SM)
        draw.text((60, box_y+28), "ccbreport(本群统计)   |   ccbglobal(全局统计)(跨群统计)   |   hail   |   xnn   |   ccbchieve   |   ccbtoday", fill=(200,210,240), font=F_XS)
        fy = box_y + 50
        
        import tempfile
        save_path = os.path.join(tempfile.gettempdir(), "ccb_report.png")
        img.save(save_path)
        
        yield event.chain_result([
            Comp.Image(file=save_path)
        ])

    @filter.command("ccbglobal")
    async def ccb_global(self, event: AstrMessageEvent):
        """
        生成跨群全局ccb统计报告
        用法：ccbglobal
        """
        from PIL import Image, ImageDraw, ImageFont
        import os, json, datetime
        
        all_data = self.read_data()
        
        # 合并所有群的数据
        merged = {}
        for gid, records in all_data.items():
            if gid.startswith("_") or not isinstance(records, list):
                continue
            for r in records:
                uid = r.get(a1, "")
                if uid not in merged:
                    merged[uid] = {
                        a1: uid,
                        a2: 0,
                        a3: 0.0,
                        a4: {},
                        a5: 0.0,
                        a6: 0,
                        "groups": set(),
                    }
                merged[uid][a2] = merged[uid].get(a2, 0) + r.get(a2, 0)
                merged[uid][a3] = merged[uid].get(a3, 0.0) + r.get(a3, 0.0)
                merged[uid][a5] = max(merged[uid].get(a5, 0.0), r.get(a5, 0.0))
                merged[uid][a6] = merged[uid].get(a6, 0) + int(r.get(a6, 0))
                merged[uid]["groups"].add(gid)
                for aid, info in r.get(a4, {}).items():
                    if aid not in merged[uid][a4]:
                        merged[uid][a4][aid] = {"count": 0, "first": False}
                    merged[uid][a4][aid]["count"] += info.get("count", 0)
                    if info.get("first"):
                        merged[uid][a4][aid]["first"] = True
        
        group_data = list(merged.values())
        
        if not group_data:
            yield event.plain_result("暂无全局ccb记录喵～")
            return
        
        # 昵称映射
        nick_map = {}
        if event.get_platform_name() == "aiocqhttp":
            for r in group_data:
                uid = r.get(a1, "")
                if uid not in nick_map:
                    try:
                        info = await event.bot.api.call_action('get_stranger_info', user_id=uid)
                        nick_map[uid] = info.get("nick", uid)
                    except:
                        nick_map[uid] = uid
        else:
            for r in group_data:
                nick_map[r.get(a1, "")] = r.get(a1, "")
        
        def get_name(uid):
            return nick_map.get(uid, uid)
        
        # 统计
        active = {}
        first_cnt = {}
        for r in group_data:
            for aid, info in r.get(a4, {}).items():
                active[aid] = active.get(aid, 0) + info.get("count", 0)
                if info.get("first"):
                    first_cnt[aid] = first_cnt.get(aid, 0) + 1
        
        total_users = len(group_data)
        total_ccb = sum(r.get(a2, 0) for r in group_data)
        total_vol = sum(r.get(a3, 0) for r in group_data)
        total_climax = sum(int(r.get(a6, 0)) for r in group_data)
        total_groups = len([g for g in all_data if not g.startswith("_") and isinstance(all_data[g], list)])
        
        # 图片
        W, H = 1000, 1800
        img = Image.new("RGB", (W, H), (245, 245, 250))
        draw = ImageDraw.Draw(img)
        fp = "/tmp/wqy-microhei.ttc"
        
        F_TITLE = ImageFont.truetype(fp, 30)
        F_SEC = ImageFont.truetype(fp, 20)
        F_NUM = ImageFont.truetype(fp, 22)
        F_NAME = ImageFont.truetype(fp, 17)
        F_VAL = ImageFont.truetype(fp, 18)
        F_SM = ImageFont.truetype(fp, 14)
        F_XS = ImageFont.truetype(fp, 12)
        
        # Header
        draw.rounded_rectangle([(20,20),(W-20,110)], radius=16, fill=(180,50,80))
        draw.text((50, 38), "ccb+ 全局统计报告", fill=(255,215,80), font=F_TITLE)
        draw.text((50, 78), f"覆盖 {total_groups} 个群  |  ccb+ global", fill=(220,180,190), font=F_SM)
        draw.text((W-220, 80), datetime.datetime.now().strftime("%Y/%m/%d %H:%M"), fill=(200,160,170), font=F_XS)
        
        # 总览卡片
        labels = [
            ("总人数", f"{total_users}", "人", (180,50,80)),
            ("总次数", f"{total_ccb}", "次", (50,170,110)),
            ("总注入", f"{total_vol:.0f}", "ml", (220,130,80)),
            ("绝顶", f"{total_climax}", "次", (200,100,170)),
        ]
        x0, y0, w0, h0, g0 = 40, 135, 220, 85, 13
        for i, (lab, val, unit, col) in enumerate(labels):
            x = x0 + i*(w0+g0)
            draw.rounded_rectangle([(x,y0),(x+w0,y0+h0)], radius=12, fill=(255,255,255), outline=col, width=2)
            draw.rounded_rectangle([(x+8,y0+8),(x+10,y0+h0-8)], radius=4, fill=col)
            draw.text((x+22, y0+10), lab, fill=(100,100,130), font=F_SM)
            draw.text((x+22, y0+42), val, fill=(30,30,50), font=F_NUM)
            draw.text((x+22+draw.textlength(val, font=F_NUM)+4, y0+52), unit, fill=(140,140,170), font=F_SM)
        
        # 排行数据
        top_ccb = sorted(group_data, key=lambda r: r.get(a2, 0), reverse=True)[:5]
        top_vol = sorted(group_data, key=lambda r: r.get(a3, 0), reverse=True)[:5]
        top_max = sorted(group_data, key=lambda r: r.get(a5, 0), reverse=True)[:5]
        top_climax = sorted(group_data, key=lambda r: int(r.get(a6, 0)), reverse=True)[:5]
        top_active = sorted(active.items(), key=lambda x: x[1], reverse=True)[:5]
        hail = {a: first_cnt.get(a,0)*2 + active[a] for a in active}
        hail_top = sorted(hail.items(), key=lambda x: x[1], reverse=True)[:5]
        xnn_list = [(r.get(a1,""), round(r.get(a2,0)*1+r.get(a3,0)*0.1-active.get(r.get(a1,""),0)*0.5,2)) for r in group_data]
        xnn_top = sorted(xnn_list, key=lambda x: x[1], reverse=True)[:5]
        
        def draw_rank(x, y, w, title, items, color):
            if not items:
                return y
            max_v = items[0][0] if items else 1
            draw.rounded_rectangle([(x,y),(x+w,y+38)], radius=10, fill=color)
            draw.text((x+14, y+8), title, fill=(255,255,255), font=F_SEC)
            y += 48
            for i, (val, name, txt) in enumerate(items):
                row_h = 42
                bg = (255,255,255) if i%2==0 else (250,250,253)
                draw.rounded_rectangle([(x,y),(x+w,y+row_h)], radius=8, fill=bg)
                if i == 0: draw.text((x+14, y+9), "#1", fill=(200,140,40), font=F_VAL)
                elif i == 1: draw.text((x+14, y+9), "#2", fill=(140,140,160), font=F_VAL)
                elif i == 2: draw.text((x+14, y+9), "#3", fill=(180,120,60), font=F_VAL)
                else: draw.text((x+20, y+10), f"#{i+1}", fill=(160,160,180), font=F_SM)
                nx = x + 60 if i < 3 else x + 52
                draw.text((nx, y+9), name, fill=(40,40,60), font=F_NAME)
                tw = draw.textlength(txt, font=F_VAL)
                draw.text((x+w-14-tw, y+9), txt, fill=(30,30,50), font=F_VAL)
                bar_s = x + 195
                bar_e = x + w - tw - 22
                bw = bar_e - bar_s
                if bw > 30:
                    ratio = val / max_v
                    filled = max(4, int(bw * ratio))
                    draw.rounded_rectangle([(bar_s,y+14),(bar_e,y+28)], radius=6, fill=(220,220,230))
                    draw.rounded_rectangle([(bar_s,y+14),(bar_s+filled,y+28)], radius=6, fill=color)
                y += row_h + 3
            return y + 10
        
        ccb_items = [(r.get(a2,0), get_name(r.get(a1,"")), f"{r.get(a2,0)}次") for r in top_ccb]
        vol_items = [(r.get(a3,0), get_name(r.get(a1,"")), f"{r.get(a3,0):.0f}ml") for r in top_vol]
        max_items = [(r.get(a5,0), get_name(r.get(a1,"")), f"{r.get(a5,0):.1f}ml") for r in top_max]
        climax_items = [(int(r.get(a6,0)), get_name(r.get(a1,"")), f"{int(r.get(a6,0))}次") for r in top_climax]
        act_items = [(c, get_name(a), f"{c}次") for a,c in top_active]
        hail_items = [(hail[a], get_name(a), f"海王值{hail[a]}") for a,_ in hail_top]
        xnn_items = [(x, get_name(u), f"XNN{x}") for u,x in xnn_top]
        
        cw = 440
        ly = 245
        ly = draw_rank(40, ly, cw, "被ccb次数 TOP5", ccb_items, (220,140,60))
        ly = draw_rank(40, ly, cw, "被注入量 TOP5", vol_items, (70,160,230))
        ly = draw_rank(40, ly, cw, "单次最大注入 TOP5", max_items, (160,110,230))
        ly = draw_rank(40, ly, cw, "绝顶次数 TOP5", climax_items, (200,100,170))
        ry = 245
        ry = draw_rank(40+cw+40, ry, cw, "主动出击 TOP5", act_items, (220,100,100))
        ry = draw_rank(40+cw+40, ry, cw, "海王值 TOP5", hail_items, (220,180,50))
        ry = draw_rank(40+cw+40, ry, cw, "小南梁XNN TOP5", xnn_items, (70,190,140))
        
        fy = max(ly, ry) + 15
        draw.line([(40,fy),(W-40,fy)], fill=(200,200,215), width=1)
        # 指令提示框
        box_y = fy + 8
        draw.rounded_rectangle([(40,box_y),(W-40,box_y+50)], radius=10, fill=(180,50,80), outline=(180,50,80), width=2)
        draw.text((60, box_y+10), "📋 指令提示", fill=(180,50,80), font=F_SM)
        draw.text((60, box_y+28), "ccbreport(本群统计)   |   ccbglobal(全局统计)(跨群统计)   |   hail   |   xnn   |   ccbchieve   |   ccbtoday", fill=(255,200,210), font=F_XS)
        fy = box_y + 50
        
        import tempfile
        save_path = os.path.join(tempfile.gettempdir(), "ccb_global.png")
        img.save(save_path)
        
        yield event.chain_result([
            Comp.Image(file=save_path)
        ])

    # ==================== 成就系统 ====================

    def _check_achievements(self, all_data, actor_id, combo_count, struggle_revenge_flag, group_id):
        """检查并解锁新成就，返回新解锁的成就列表"""
        from datetime import datetime
        achievements = all_data.setdefault("_achievements", {})
        user_achs = achievements.setdefault(actor_id, [])
        new_achs = []

        # 获取actor的统计数据
        group_data = all_data.get(group_id, [])
        total_ccb = 0  # actor累计ccb成功次数
        total_climax_caused = 0  # actor导致的绝顶次数
        for record in group_data:
            ccb_by = record.get(a4, {}) or {}
            info = ccb_by.get(actor_id)
            if info:
                total_ccb += info.get("count", 0)
            # 该记录的绝顶次数
            climax_c = int(record.get(a6, 0))
            # 粗略估算：actor导致的绝顶按比例分配
            if ccb_by and climax_c > 0:
                total_actions = sum(v.get("count", 0) for v in ccb_by.values())
                if total_actions > 0:
                    actor_actions = ccb_by.get(actor_id, {}).get("count", 0)
                    total_climax_caused += int(climax_c * actor_actions / total_actions)

        # 被绝顶次数（actor作为target）
        actor_record = next((r for r in group_data if r.get(a1) == actor_id), None)
        self_climax = int(actor_record.get(a6, 0)) if actor_record else 0

        # 逐项检查
        for adef in self.achievement_defs:
            if adef["id"] in user_achs:
                continue
            unlock = False
            if adef["id"] == "first_ccb":
                unlock = total_ccb >= 1
            elif adef["id"] == "combo_master":
                unlock = combo_count >= 7
            elif adef["id"] == "climax_master":
                unlock = total_climax_caused >= 20
            elif adef["id"] == "climax_fish":
                unlock = self_climax >= 10
            elif adef["id"] == "conqueror":
                unlock = total_ccb >= 50
            elif adef["id"] == "perpetual":
                unlock = combo_count >= 3 and struggle_revenge_flag
            elif adef["id"] == "all_achievements":
                unlock = len(user_achs) >= 6  # 除自己外的6个
            if unlock:
                user_achs.append(adef["id"])
                new_achs.append(adef)
        achievements[actor_id] = user_achs
        all_data["_achievements"] = achievements
        return new_achs

    @filter.command("ccbachieve")
    async def ccbachieve(self, event: AstrMessageEvent):
        """
        查看ccb成就
        用法：ccbachieve [@目标]
        """
        group_id = str(event.get_group_id())
        self_id = str(event.get_self_id())
        target_user_id = next(
            (str(seg.qq) for seg in event.get_messages()
             if isinstance(seg, Comp.At) and str(seg.qq) != self_id),
            str(event.get_sender_id())
        )

        all_data = self.read_data()
        achievements = all_data.setdefault("_achievements", {})
        user_achs = achievements.get(target_user_id, [])

        nick = target_user_id
        if event.get_platform_name() == "aiocqhttp":
            try:
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                assert isinstance(event, AiocqhttpMessageEvent)
                stranger_info = await event.bot.api.call_action('get_stranger_info', user_id=target_user_id)
                nick = stranger_info.get("nick", nick)
            except:
                pass

        lines = [f"🏆 {nick} 的ccb成就 🏆"]
        lines.append("━━━━━━━━━━━━━━━")
        unlocked_count = 0
        for adef in self.achievement_defs:
            unlocked = adef["id"] in user_achs
            icon = "✅" if unlocked else "⬜"
            if unlocked:
                unlocked_count += 1
            lines.append(f"{icon} {adef['icon']} {adef['name']} — {adef['desc']}")
        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"已解锁: {unlocked_count}/{len(self.achievement_defs)}")
        yield event.plain_result("".join(lines))

    @filter.command("ccbvol")
    async def ccbvol(self, event: AstrMessageEvent):
        """
        按注入量排行
        """
        group_id = str(event.get_group_id())
        group_data = self.read_data().get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        top5 = sorted(group_data, key=lambda x: float(x.get(a3, 0)), reverse=True)[:5]
        msg = "被注入量排行榜 TOP5：\n"
        for i, r in enumerate(top5, 1):
            uid = r[a1]
            nick = uid
            if event.get_platform_name() == "aiocqhttp":
                try:
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    stranger_info = await event.bot.api.call_action('get_stranger_info', user_id=uid)
                    nick = stranger_info.get("nick", nick)
                except:
                    pass
            msg += f"{i}. {nick} - 累计注入：{float(r[a3]):.2f}ml\n"
        yield event.plain_result(msg)

    @filter.command("ccbinfo")
    async def ccbinfo(self, event: AstrMessageEvent):
        """
        查询某人ccb信息：第一次对他ccb的人，被ccb的总次数，注入总量
        用法：ccbinfo [@目标]
        """
        group_id = str(event.get_group_id())
        # 解析 @ 目标，否则默认查询自己
        self_id = str(event.get_self_id())
        target_user_id = next(
            (str(seg.qq) for seg in event.get_messages()
             if isinstance(seg, Comp.At) and str(seg.qq) != self_id),
            str(event.get_sender_id())
        )

        # 读取群数据
        all_data = self.read_data()
        group_data = all_data.get(group_id, [])

        # 查找目标记录
        record = next((r for r in group_data if r.get(a1) == target_user_id), None)
        if not record:
            yield event.plain_result("该用户暂无ccb记录。")
            return

        # 总次数 & 总注入量
        total_num = int(record.get(a2, 0))
        total_vol = float(record.get(a3, 0))

        raw_max = record.get(a5, None)
        max_val = 0.0
        try:
            if raw_max is not None:
                max_val = float(raw_max)
            else:
                if total_num > 0:
                    max_val = round(total_vol / total_num, 2)
        except Exception:
            max_val = 0.0

        # 计算ccb次数
        cb_total = 0
        try:
            for rec in group_data:
                by = rec.get(a4, {}) or {}
                info = by.get(target_user_id)
                if info:
                    cb_total += int(info.get("count", 0))
        except Exception:
            cb_total = 0

        # 找出第一次的操作者
        ccb_by = record.get(a4, {})
        first_actor = None
        for actor_id, info in ccb_by.items():
            if info.get("first"):
                first_actor = actor_id
                break

        # 如果没标记 first，就选 count 最大的作为“首位”
        if not first_actor and ccb_by:
            first_actor = max(ccb_by.items(), key=lambda x: x[1].get("count", 0))[0]

        # 获取昵称
        first_nick = first_actor or "未知"
        if first_actor and event.get_platform_name() == "aiocqhttp":
            try:
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                assert isinstance(event, AiocqhttpMessageEvent)
                stranger_info = await event.bot.api.call_action(
                    'get_stranger_info', user_id=first_actor
                )
                first_nick = stranger_info.get("nick", first_actor)
            except:
                pass

        # 绝顶次数
        climax_count = int(record.get(a6, 0))
        # 输出结果
        msg = (
            f"【{record.get(a1)} 】\n"
            f"• 第一次ccbta的人：{first_nick}\n"
            f"• 被ccb次数：{total_num}\n"
            f"• ccb别人的次数：{cb_total}\n"
            f"• 被注入总量：{total_vol:.2f}ml\n"
            f"• 单次最大注入量：{max_val:.2f}ml"
            f"• 绝顶次数：{climax_count}"
        )
        yield event.plain_result(msg)

    # 每日总结
    @filter.command("ccbtoday")
    async def ccbtoday(self, event: AstrMessageEvent):
        """
        查看今日详细ccb日报（含海王/小南梁）
        用法：ccbtoday
        """
        group_id = str(event.get_group_id())
        today_start = time.time() - 86400  # 过去24小时

        # 读取日志
        logs = []
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, 'r', encoding='utf-8') as lf:
                    logs = json.load(lf)
                    if not isinstance(logs, list):
                        logs = []
            except Exception:
                logs = []

        # 过滤当前群 + 今日的日志
        today_logs = [
            entry for entry in logs
            if str(entry.get("group", "")) == group_id
            and entry.get("timestamp", 0) >= today_start
        ]

        if not today_logs:
            yield event.plain_result("今日群内暂无ccb记录喵～")
            return

        # ====== 统计 ======
        total_count = len(today_logs)
        total_vol = sum(float(entry.get("vol", 0)) for entry in today_logs)
        total_dur = sum(float(entry.get("duration", 0)) for entry in today_logs)
        avg_vol = total_vol / total_count if total_count > 0 else 0
        max_vol_today = max(float(entry.get("vol", 0)) for entry in today_logs)
        max_dur_today = max(float(entry.get("duration", 0)) for entry in today_logs)

        # 读取全服累计数据（绝顶等）
        all_data = self.read_data()
        group_data_all = all_data.get(group_id, [])
        total_ccb_all = sum(r.get("num", 0) for r in group_data_all)
        total_vol_all = sum(r.get("vol", 0) for r in group_data_all)
        total_climax_all = sum(int(r.get(a6, 0)) for r in group_data_all)

        # 操作者排行（谁ccb别人最多）
        executor_stats = {}
        for entry in today_logs:
            eid = entry.get("executor", "?")
            executor_stats[eid] = executor_stats.get(eid, 0) + 1
        executor_rank = sorted(executor_stats.items(), key=lambda x: x[1], reverse=True)

        # 被ccb排行（谁被ccb最多）
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

        # 单次最大注入排行（今日）
        max_stats = {}
        for entry in today_logs:
            tid = entry.get("target", "?")
            v = float(entry.get("vol", 0))
            if tid not in max_stats or v > max_stats[tid]:
                max_stats[tid] = v
        max_rank = sorted(max_stats.items(), key=lambda x: x[1], reverse=True)

        # 净差值排行（主动-被动）
        all_uids_today = set(list(executor_stats.keys()) + list(target_stats.keys()))
        haiwang_list = []
        xnn_list = []
        for uid in all_uids_today:
            act = executor_stats.get(uid, 0)
            pas = target_stats.get(uid, 0)
            diff = act - pas
            if diff > 0:
                haiwang_list.append((uid, diff, act, pas))
            elif diff < 0:
                xnn_list.append((uid, diff, act, pas))
        haiwang_rank = sorted(haiwang_list, key=lambda x: x[1], reverse=True)
        xnn_rank = sorted(xnn_list, key=lambda x: x[1])

        # 小南梁XNN值（累计）
        xnn_val_list = []
        for r in group_data_all:
            uid = r.get(a1, "")
            if uid in all_uids_today:
                n = r.get("num", 0)
                v = r.get("vol", 0)
                a_today = executor_stats.get(uid, 0)
                xnn = n * 1.0 + v * 0.1 - a_today * 0.5
                xnn_val_list.append((uid, round(xnn, 2), n, v, a_today))
        xnn_val_rank = sorted(xnn_val_list, key=lambda x: x[1], reverse=True)[:5]

        # 获取昵称（批量缓存）
        nick_cache = {}
        async def get_nick(uid):
            if uid in nick_cache:
                return nick_cache[uid]
            nick = uid
            if event.get_platform_name() == "aiocqhttp":
                try:
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    assert isinstance(event, AiocqhttpMessageEvent)
                    info = await event.bot.api.call_action('get_stranger_info', user_id=uid)
                    nick = info.get("nick", uid)
                except:
                    pass
            nick_cache[uid] = nick
            return nick

        # 预加载前10个uid的昵称
        preload_uids = set()
        for uid, _ in executor_rank[:5]: preload_uids.add(uid)
        for uid, _ in target_rank[:5]: preload_uids.add(uid)
        for uid, _, _, _ in haiwang_rank[:3]: preload_uids.add(uid)
        for uid, _, _, _ in xnn_rank[:3]: preload_uids.add(uid)
        for uid, _, _, _, _ in xnn_val_rank: preload_uids.add(uid)
        for uid in preload_uids:
            await get_nick(uid)

        # ====== 构造消息 ======
        msg_lines = [
            f"📊 ccb+ 今日日报 (过去24h)",
            f"━━━━━━━━━━━━━━━",
            f"📌【今日数据】",
            f"  🔞 总次数：{total_count} 次",
            f"  💦 总注入：{total_vol:.2f}ml",
            f"  ⏱️ 总时长：{total_dur:.1f}min",
            f"  📊 平均每次：{avg_vol:.2f}ml / {total_dur/total_count:.1f}min",
            f"  🔥 单次最大：{max_vol_today:.2f}ml | 最长单次：{max_dur_today:.1f}min",
            f"━━━━━━━━━━━━━━━",
            f"📌【累计数据（本群）】",
            f"  总ccb次数：{total_ccb_all} 次",
            f"  总注入量：{total_vol_all:.2f}ml",
            f"  💫 总绝顶次数：{total_climax_all} 次",
            f"━━━━━━━━━━━━━━━",
        ]

        # ccb之王（Top 5）
        if executor_rank:
            msg_lines.append(f"🏆 今日ccb之王（主动出击）")
            medals = ["🥇","🥈","🥉","4.","5."]
            for i, (uid, cnt) in enumerate(executor_rank[:5], 0):
                nick = nick_cache.get(uid, uid)
                msg_lines.append(f"  {medals[i]} {nick} — {cnt}次")
            msg_lines.append("")

        # 被ccb排行（Top 5）
        if target_rank:
            msg_lines.append(f"🎯 今日艾草榜（被ccb）")
            medals = ["🥇","🥈","🥉","4.","5."]
            for i, (uid, cnt) in enumerate(target_rank[:5], 0):
                nick = nick_cache.get(uid, uid)
                msg_lines.append(f"  {medals[i]} {nick} — {cnt}次")
            msg_lines.append("")

        # 注入量排行（Top 5）
        if vol_rank:
            msg_lines.append(f"💧 今日被注入量排行")
            medals = ["🥇","🥈","🥉","4.","5."]
            for i, (uid, v) in enumerate(vol_rank[:5], 0):
                nick = nick_cache.get(uid, uid)
                msg_lines.append(f"  {medals[i]} {nick} — {v:.2f}ml")
            msg_lines.append("")

        # 单次最大注入（Top 5）
        if max_rank:
            msg_lines.append(f"⚡ 今日单次最大注入")
            medals = ["🥇","🥈","🥉","4.","5."]
            for i, (uid, v) in enumerate(max_rank[:5], 0):
                nick = nick_cache.get(uid, uid)
                msg_lines.append(f"  {medals[i]} {nick} — {v:.2f}ml")
            msg_lines.append("")

        # 今日海王榜
        if haiwang_rank:
            msg_lines.append(f"👑 今日海王榜（主动-被动）")
            for i, (uid, diff, act, pas) in enumerate(haiwang_rank[:3], 0):
                nick = nick_cache.get(uid, uid)
                trophy = ["🥇","🥈","🥉"][i]
                msg_lines.append(f"  {trophy} {nick} +{diff}  (出击{act}·被{pas})")
            msg_lines.append("")

        # 今日小南梁榜
        if xnn_rank:
            msg_lines.append(f"💎 今日小南梁榜（被动-主动）")
            for i, (uid, diff, act, pas) in enumerate(xnn_rank[:3], 0):
                nick = nick_cache.get(uid, uid)
                trophy = ["🥇","🥈","🥉"][i]
                msg_lines.append(f"  {trophy} {nick} {diff}  (出击{act}·被{pas})")
            msg_lines.append("")

        # 小南梁XNN值（累计）
        if xnn_val_rank:
            msg_lines.append(f"📊 小南梁XNN值（累计）")
            for i, (uid, xnn, n, v, a) in enumerate(xnn_val_rank, 0):
                nick = nick_cache.get(uid, uid)
                msg_lines.append(f"  {['🥇','🥈','🥉','4.','5.'][i]} {nick} — XNN {xnn}  (被{n}次·{v:.0f}ml·主动{a})")

        msg_lines = [l for l in msg_lines if l]
        yield event.plain_result("\n".join(msg_lines))

    # 绝顶排行榜
    @filter.command("ccbclimax")
    async def ccbclimax(self, event: AstrMessageEvent):
        """
        按绝顶次数排行
        用法：ccbclimax
        """
        group_id = str(event.get_group_id())
        group_data = self.read_data().get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        top5 = sorted(group_data, key=lambda x: int(x.get(a6, 0)), reverse=True)[:5]
        msg = "绝顶排行榜 TOP5：\n"
        for i, r in enumerate(top5, 1):
            uid = r[a1]
            nick = uid
            if event.get_platform_name() == "aiocqhttp":
                try:
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    stranger_info = await event.bot.api.call_action("get_stranger_info", user_id=uid)
                    nick = stranger_info.get("nick", nick)
                except:
                    pass
            msg += f"{i}. {nick} - 绝顶{int(r.get(a6, 0))}次\n"
        yield event.plain_result(msg)

    # 单次注入排行榜
    @filter.command("ccbmax")
    async def ccbmax(self, event: AstrMessageEvent):
        """
        按max值排行并输出产生者
        """
        group_id = str(event.get_group_id())
        group_data = self.read_data().get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        # 计算max
        entries = []
        for r in group_data:
            raw_max = r.get(a5, None)
            max_val = 0.0
            try:
                if raw_max is not None:
                    max_val = float(raw_max)
                else:
                    total_vol = float(r.get(a3, 0))
                    total_num = int(r.get(a2, 0))
                    if total_num > 0:
                        max_val = round(total_vol / total_num, 2)
            except Exception:
                max_val = 0.0
            entries.append((r, float(max_val)))

        # 排序
        entries.sort(key=lambda x: x[1], reverse=True)
        top5 = entries[:5]

        msg = "单次最大注入排行榜 TOP5：\n"
        for i, (r, max_val) in enumerate(top5, 1):
            uid = r.get(a1)
            # 解析产生者
            producer_id = None
            ccb_by = r.get(a4, {}) or {}
            for actor_id, info in ccb_by.items():
                if info.get("max"):
                    producer_id = actor_id
                    break
            # 若没有显式标记，则回退选取count最大者
            if not producer_id and ccb_by:
                try:
                    producer_id = max(ccb_by.items(), key=lambda x: x[1].get("count", 0))[0]
                except Exception:
                    producer_id = None

            # 获取昵称
            nick = uid
            producer_nick = producer_id or "未知"
            if event.get_platform_name() == "aiocqhttp":
                try:
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    assert isinstance(event, AiocqhttpMessageEvent)
                    # 获取被ccb者昵称
                    try:
                        stranger_info = await event.bot.api.call_action('get_stranger_info', user_id=uid)
                        nick = stranger_info.get("nick", nick)
                    except Exception:
                        pass
                    # 获取产生者昵称
                    if producer_id:
                        try:
                            p_info = await event.bot.api.call_action('get_stranger_info', user_id=producer_id)
                            producer_nick = p_info.get("nick", producer_nick)
                        except Exception:
                            pass
                except Exception:
                    pass

            msg += f"{i}. {nick} - 单次最大：{max_val:.2f}ml（{producer_nick}）\n"

        yield event.plain_result(msg)

    '''
    @filter.command("haiwang")
    async def haiwang(self, event: AstrMessageEvent):
        """
        海王榜
        计算群中最后宫特质的群友
        """
        group_id = str(event.get_group_id())
        all_data = self.read_data()
        group_data = all_data.get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        # 聚合
        stats = {}  # actor_id -> {"first": x, "actions": y}
        for record in group_data:
            ccb_by = record.get(a4, {})
            for actor_id, info in ccb_by.items():
                st = stats.setdefault(actor_id, {"first": 0, "actions": 0})
                st["actions"] += info.get("count", 0)
                if info.get("first"):
                    st["first"] += 1

        # 计算权重并排序
        ranking = []
        for actor_id, st in stats.items():
            weight = st["first"] * 2 + st["actions"]
            ranking.append((actor_id, st["first"], st["actions"], weight))
        ranking.sort(key=lambda x: x[3], reverse=True)
        top5 = ranking[:5]

        # 构造输出
        msg = "🏆 海王榜 TOP5 🏆\n"
        for idx, (actor_id, first_cnt, actions_cnt, weight) in enumerate(top5, 1):
            nick = actor_id
            if event.get_platform_name() == "aiocqhttp":
                try:
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    assert isinstance(event, AiocqhttpMessageEvent)
                    info = await event.bot.api.call_action("get_stranger_info", user_id=actor_id)
                    nick = info.get("nick", nick)
                except:
                    pass
            msg += (
                f"{idx}. {nick} - 海王值：{weight}\n"
                # f"(首位：{first_cnt}次，ccb：{actions_cnt}次)\n"
            )
        yield event.plain_result(msg)
    '''

    @filter.command("xnn")
    async def xnn(self, event: AstrMessageEvent):
        """
        XNN榜
        计算群中最xnn特质的群友
        """
        # 配置权重
        w_num = 1.0
        w_vol = 0.1
        w_action = 0.5

        group_id = str(event.get_group_id())
        all_data = self.read_data()
        group_data = all_data.get(group_id, [])
        if not group_data:
            yield event.plain_result("当前群暂无ccb记录。")
            return

        # 统计每个人对别人的操作次数
        actor_actions = {}
        for record in group_data:
            ccb_by = record.get(a4, {})
            for actor_id, info in ccb_by.items():
                actor_actions[actor_id] = actor_actions.get(actor_id, 0) + info.get("count", 0)

        # 计算xnn值
        ranking = []
        for record in group_data:
            uid = record.get(a1)
            num = int(record.get(a2, 0))
            vol = float(record.get(a3, 0))
            actions = actor_actions.get(uid, 0)
            xnn_value = num * w_num + vol * w_vol - actions * w_action
            ranking.append((uid, xnn_value))

        # 排序
        ranking.sort(key=lambda x: x[1], reverse=True)
        top5 = ranking[:5]

        # 构造输出
        msg = "💎 小南梁 TOP5 💎\n"
        for idx, (uid, xnn_val) in enumerate(ranking[:5], 1):
            nick = uid
            if event.get_platform_name() == "aiocqhttp":
                try:
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    assert isinstance(event, AiocqhttpMessageEvent)
                    info = await event.bot.api.call_action("get_stranger_info", user_id=uid)
                    nick = info.get("nick", nick)
                except:
                    pass
            msg += (
                f"{idx}. {nick} - XNN值：{xnn_val:.2f} \n"
                # f"(被ccb次数：{num}，容量：{vol:.2f}ml，对他人ccb：{actions})\n"
            )

        yield event.plain_result(msg)
