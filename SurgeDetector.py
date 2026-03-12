"""
OpenClaw Skill: Short-Term Surge Detector v2.0
短线暴涨探测器 (含三大失效模式检测)
目标：10-20 天 25%+ 涨幅，严格风控
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import re
import warnings

warnings.filterwarnings('ignore')


# ==================== 数据类定义 ====================

class FailureMode(Enum):
    """三大失效模式"""
    CATALYST_INVALID = "催化剂失效"      # 买入逻辑被证伪
    CAPITAL_WITHDRAWAL = "资金撤离"      # 主力资金态度转变
    TECHNICAL_BREAKDOWN = "技术破位"     # 关键技术位跌破


@dataclass
class FailureCheck:
    """失效检查结果"""
    mode: FailureMode
    triggered: bool          # 是否触发
    severity: str            # CRITICAL/HIGH/MEDIUM/LOW
    evidence: List[str]      # 证据列表
    action: str              # 建议行动


@dataclass
class RiskGuardrails:
    """风控护栏参数"""
    max_loss_per_trade: float = 0.08      # 单票最大亏损 8%
    time_stop_days: int = 5               # 时间止损天数
    profit_protect_ratio: float = 0.6     # 利润回撤 60% 保护
    volume_collapse_ratio: float = 0.5    # 量能萎缩 50% 警戒


# ==================== 主探测器类 ====================

class ShortTermSurgeDetector:
    """
    短线暴涨探测器 v2.0
    """

    def __init__(self):
        self.stock_code = None
        self.stock_name = None
        self.data_cache = {}
        self.position = None  # 当前持仓信息

        # 权重配置
        self.weights = {
            'catalyst': 0.30,
            'capital': 0.25,
            'sector': 0.20,
            'technical': 0.15,
            'fundamental': 0.10
        }

        # 风控参数
        self.risk = RiskGuardrails()

        # 失效检测关键词
        self.catalyst_denial_keywords = r'(澄清 | 否认 | 不实 | 谣言 | 未收到 | 未签署 | 不存在 | 未计划 | 终止 | 取消 | 延期超过 3 个月 | 低于预期 | 业绩修正 | 预亏 | 立案调查 | 监管函 | 问询函 | 关注函)'
        self.capital_withdrawal_signals = {
            'outflow_days': 3,              # 连续 3 日流出
            'outflow_ratio': 0.15,          # 累计流出 15%
            'volume_collapse': 0.5,         # 量能萎缩 50%
            'price_volume_divergence': True # 量价背离
        }

    # ==================== 第一层：数据获取 ====================

    def fetch_data(self, stock_code: str) -> Dict:
        """获取全维度数据"""
        data = {}

        # 1. K 线数据 (60 日)
        data['price'] = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            start_date=(datetime.now() - timedelta(days=60)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust="qfq"
        )

        # 2. 实时行情
        spot = ak.stock_zh_a_spot_em()
        data['realtime'] = spot[spot['代码'] == stock_code].iloc[0].to_dict()

        # 3. 资金流向 (10 日)
        market = "sz" if stock_code.startswith(('00', '30')) else "sh"
        data['money_flow'] = ak.stock_individual_fund_flow(stock=stock_code, market=market)

        # 4. 龙虎榜 (30 日)
        start_dt = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        end_dt = datetime.now().strftime("%Y%m%d")
        lhb = ak.stock_lhb_detail_daily_sina(start_date=start_dt, end_date=end_dt)
        data['dragon_tiger'] = lhb[lhb['代码'] == stock_code] if '代码' in lhb.columns else pd.DataFrame()

        # 5. 公司公告 (近 1 月)
        data['news'] = ak.stock_notice_report(symbol=stock_code, date=datetime.now().strftime("%Y%m%d"))

        self.data_cache = data
        return data

    # ==================== 第二层：五维分析 ====================

    def analyze_catalyst(self) -> Dict:
        """催化剂分析"""
        score = 50
        evidence = []

        # 公告扫描
        news_df = self.data_cache.get('news', pd.DataFrame())
        if not news_df.empty:
            for _, row in news_df.head(10).iterrows():
                title = str(row.get('标题', ''))

                # 强力催化剂
                strong_patterns = r'(重大合同 | 中标 | 并购重组 | 资产注入 | 业绩预增.*[5-9]\d+%|产品涨价 | 技术突破 | 独家代理)'
                if re.search(strong_patterns, title):
                    score += 20
                    evidence.append(f"🚀 {title[:40]}...")

                # 中度催化剂
                medium_patterns = r'(回购 | 增持 | 产能扩张 | 投产 | 政策利好)'
                if re.search(medium_patterns, title):
                    score += 10
                    evidence.append(f"📈 {title[:40]}...")

        # 热点概念匹配
        rt = self.data_cache.get('realtime', {})
        concepts = rt.get('所属概念', '')
        hot_concepts = ['AI', '算力', '机器人', '低空经济', '固态电池', '合成生物', '涨价概念']
        matched = [c for c in hot_concepts if c in concepts]
        if matched:
            score += len(matched) * 5
            evidence.append(f"🔥 热点概念：{', '.join(matched[:3])}")

        return {
            'score': min(100, score),
            'evidence': evidence if evidence else ["暂无明确催化剂"]
        }

    def analyze_capital(self) -> Dict:
        """资金异动分析"""
        score = 50
        evidence = []

        df = self.data_cache.get('price')
        if df is None or df.empty:
            return {'score': 50, 'evidence': ['数据缺失']}

        # 近期涨幅
        df['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
        ret_5d = df['涨跌幅'].tail(5).sum()

        if ret_5d > 20:
            score += 25
            evidence.append(f"🚀 5 日暴涨 {ret_5d:.1f}%")
        elif ret_5d > 10:
            score += 15
            evidence.append(f"📈 5 日强势 {ret_5d:.1f}%")

        # 成交量
        df['成交量'] = pd.to_numeric(df['成交量'], errors='coerce')
        vol_ratio = df['成交量'].iloc[-1] / df['成交量'].tail(20).mean()
        if vol_ratio > 3:
            score += 15
            evidence.append(f"🔥 量能放大 {vol_ratio:.1f}x")

        # 涨停次数
        limit_up = (df['涨跌幅'].tail(20) >= 9.9).sum()
        if limit_up >= 2:
            score += 10
            evidence.append(f"💥 {limit_up}次涨停，股性激活")

        # 资金流向
        mf = self.data_cache.get('money_flow')
        if mf is not None and not mf.empty:
            recent_inflow = pd.to_numeric(mf.head(5)['主力净流入'], errors='coerce').sum()
            if recent_inflow > 5000:
                score += 10
                evidence.append(f"💵 主力净流入 {recent_inflow/10000:.0f}万")

        return {
            'score': min(100, score),
            'evidence': evidence if evidence else ["资金状态正常"]
        }

    def analyze_technical(self) -> Dict:
        """技术形态分析"""
        score = 50
        evidence = []

        df = self.data_cache.get('price')
        close = pd.to_numeric(df['收盘'], errors='coerce')

        # 均线
        ma5 = close.rolling(5).mean().iloc[-1]
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        latest = close.iloc[-1]

        if latest > ma5 > ma10 > ma20:
            score += 15
            evidence.append("🎯 多头排列")

        # 突破
        high_20 = pd.to_numeric(df['最高'], errors='coerce').tail(20).max()
        if latest > high_20 * 0.98:
            score += 10
            evidence.append("⛰️ 突破前高")

        return {
            'score': min(100, score),
            'evidence': evidence if evidence else ["技术形态中性"],
            'levels': {
                'current': latest,
                'support': pd.to_numeric(df['最低'], errors='coerce').tail(20).min(),
                'resistance': high_20
            }
        }

    # ==================== 第三层：三大失效检测 (核心) ====================

    def detect_failure_modes(self) -> List[FailureCheck]:
        """
        检测三大失效状况
        这是持仓后的每日必做检查
        """
        failures = []

        # 1. 催化剂失效检测
        f1 = self._detect_catalyst_invalidity()
        failures.append(f1)

        # 2. 资金撤离检测
        f2 = self._detect_capital_withdrawal()
        failures.append(f2)

        # 3. 技术破位检测 (需要持仓信息)
        if self.position:
            f3 = self._detect_technical_breakdown()
            failures.append(f3)
        else:
            failures.append(FailureCheck(
                mode=FailureMode.TECHNICAL_BREAKDOWN,
                triggered=False,
                severity="LOW",
                evidence=["未持仓"],
                action="N/A"
            ))

        return failures

    def _detect_catalyst_invalidity(self) -> FailureCheck:
        """
        失效模式 1: 催化剂失效
        触发条件：买入逻辑被证伪，或出现重大利空
        """
        triggered = False
        evidence = []
        severity = "LOW"

        news_df = self.data_cache.get('news', pd.DataFrame())

        # 检测 A: 公告否认/澄清
        for _, row in news_df.head(5).iterrows():
            title = str(row.get('标题', ''))
            if re.search(self.catalyst_denial_keywords, title):
                evidence.append(f"🚨 催化剂证伪：{title[:40]}...")
                triggered = True
                severity = "CRITICAL"

        # 检测 B: 业绩变脸
        if '业绩修正' in str(news_df) or '预亏' in str(news_df):
            evidence.append("💸 业绩预期下调")
            triggered = True
            severity = "HIGH" if severity != "CRITICAL" else severity

        # 检测 C: 政策/行业利空
        policy_negative = r'(监管收紧 | 限制 | 禁止 | 产能过剩 | 价格战 | 反倾销 | 关税)'
        for _, row in news_df.head(3).iterrows():
            title = str(row.get('标题', ''))
            if re.search(policy_negative, title):
                evidence.append(f"⚠️ 政策逆风：{title[:40]}...")
                triggered = True
                severity = "HIGH" if severity not in ["CRITICAL"] else severity

        action = "立即清仓" if severity == "CRITICAL" else \
                 "减半持仓" if severity == "HIGH" else \
                 "减仓 1/3" if triggered else "持有观察"

        return FailureCheck(
            mode=FailureMode.CATALYST_INVALID,
            triggered=triggered,
            severity=severity,
            evidence=evidence if evidence else ["✅ 催化剂逻辑 intact"],
            action=action
        )

    def _detect_capital_withdrawal(self) -> FailureCheck:
        """
        失效模式 2: 资金撤离
        触发条件：主力资金连续流出，或龙虎榜显示出货
        """
        triggered = False
        evidence = []
        severity = "LOW"

        df = self.data_cache.get('price')
        mf = self.data_cache.get('money_flow')

        # 检测 A: 连续资金流出
        if mf is not None and not mf.empty:
            recent_flow = pd.to_numeric(mf.head(5)['主力净流入'], errors='coerce')
            outflow_days = (recent_flow < 0).sum()
            total_outflow = abs(recent_flow[recent_flow < 0].sum())

            if outflow_days >= self.capital_withdrawal_signals['outflow_days']:
                evidence.append(f"🩸 连续{outflow_days}日主力净流出")
                triggered = True
                severity = "CRITICAL"

            # 检测 B: 大额流出
            avg_capital = recent_flow.abs().mean()
            if total_outflow > avg_capital * 2:
                evidence.append(f"💸 大额资金撤离 {total_outflow/10000:.0f}万")
                triggered = True
                severity = "HIGH" if severity != "CRITICAL" else severity

        # 检测 C: 量价背离
        if df is not None:
            close = pd.to_numeric(df['收盘'], errors='coerce')
            volume = pd.to_numeric(df['成交量'], errors='coerce')

            # 近 3 日
            price_change = (close.iloc[-1] - close.iloc[-3]) / close.iloc[-3]
            vol_change = (volume.tail(3).mean() - volume.tail(20).mean()) / volume.tail(20).mean()

            # 价涨量缩 (危险)
            if price_change > 0.05 and vol_change < -0.3:
                evidence.append(f"⚠️ 量价背离：涨{price_change*100:.1f}%但量缩{abs(vol_change)*100:.0f}%")
                triggered = True
                severity = "MEDIUM"

            # 价跌量增 (出货)
            if price_change < -0.05 and vol_change > 0.5:
                evidence.append(f"🩸 放量下跌：跌{abs(price_change)*100:.1f}%且放量{vol_change*100:.0f}%")
                triggered = True
                severity = "HIGH"

        # 检测 D: 龙虎榜机构卖出
        lhb = self.data_cache.get('dragon_tiger')
        if lhb is not None and not lhb.empty:
            if '机构' in str(lhb) and '卖' in str(lhb):
                evidence.append("🏦 机构席位大额卖出")
                triggered = True
                severity = "HIGH"

        # 检测 E: 流动性枯竭
        if df is not None:
            turnover = pd.to_numeric(df.get('换手率', 0), errors='coerce')
            if not turnover.empty:
                if turnover.iloc[-1] < turnover.tail(20).mean() * 0.5:
                    evidence.append(f"😴 流动性枯竭：换手率骤降")
                    triggered = True

        action = "立即清仓" if severity == "CRITICAL" else \
                 "减半持仓" if severity == "HIGH" else \
                 "减仓 1/3" if triggered else "持有观察"

        return FailureCheck(
            mode=FailureMode.CAPITAL_WITHDRAWAL,
            triggered=triggered,
            severity=severity,
            evidence=evidence if evidence else ["✅ 资金状态健康"],
            action=action
        )

    def _detect_technical_breakdown(self) -> FailureCheck:
        """
        失效模式 3: 技术破位
        触发条件：跌破关键位，或时间/利润止损
        """
        triggered = False
        evidence = []
        severity = "LOW"

        if not self.position:
            return FailureCheck(FailureMode.TECHNICAL_BREAKDOWN, False, "LOW", ["未持仓"], "N/A")

        df = self.data_cache.get('price')
        current = self.position['current_price']
        entry = self.position['entry_price']
        holding_days = self.position.get('holding_days', 0)

        close = pd.to_numeric(df['收盘'], errors='coerce')
        low = pd.to_numeric(df['最低'], errors='coerce')
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]

        # 检测 A: 固定止损 (8%)
        stop_price = entry * (1 - self.risk.max_loss_per_trade)
        if current < stop_price:
            loss_pct = (1 - current/entry) * 100
            evidence.append(f"🛑 触发固定止损：亏损{loss_pct:.1f}% (>{self.risk.max_loss_per_trade*100:.0f}%)")
            triggered = True
            severity = "CRITICAL"

        # 检测 B: 关键支撑跌破 (3% 缓冲)
        key_support = max(low.tail(20).min() * 0.98, ma20 * 0.95)
        if current < key_support * 0.97:
            evidence.append(f"💥 跌破关键支撑 ¥{key_support:.2f}")
            triggered = True
            severity = "CRITICAL"

        # 检测 C: 均线空头排列
        if current < ma10 < ma20:
            evidence.append(f"📉 空头排列形成 (¥{current:.2f} < MA10 < MA20)")
            triggered = True
            severity = "HIGH"

        # 检测 D: 时间止损
        if holding_days >= self.risk.time_stop_days:
            price_change = (current - entry) / entry
            if price_change < 0.05:  # 5 日涨幅<5% 视为未启动
                evidence.append(f"⏰ 时间止损：{holding_days}日未启动，涨幅{price_change*100:.1f}%")
                triggered = True
                severity = "MEDIUM"

        # 检测 E: 长上影线/墓碑线 (日内反转)
        latest = df.iloc[-1]
        day_open = pd.to_numeric(latest['开盘'], errors='coerce')
        day_high = pd.to_numeric(latest['最高'], errors='coerce')
        day_close = pd.to_numeric(latest['收盘'], errors='coerce')

        if day_high > day_open * 1.05 and day_close < day_open:
            evidence.append(f"🪦 墓碑线：冲高回落 {(day_high/day_open-1)*100:.1f}%，收阴")
            triggered = True
            severity = "HIGH"

        # 检测 F: 利润回撤保护
        max_price = close.tail(holding_days).max() if holding_days > 0 else entry
        if max_price > entry * 1.10:  # 曾有 10%+ 浮盈
            drawdown = (max_price - current) / (max_price - entry)
            if drawdown > self.risk.profit_protect_ratio:
                evidence.append(f"🛡️ 利润回撤保护：从高点回撤{drawdown*100:.0f}%")
                triggered = True
                severity = "MEDIUM"

        action = "立即清仓" if severity == "CRITICAL" else \
                 "减半持仓" if severity == "HIGH" else \
                 "减仓 1/3" if triggered else "持有观察"

        return FailureCheck(
            mode=FailureMode.TECHNICAL_BREAKDOWN,
            triggered=triggered,
            severity=severity,
            evidence=evidence if evidence else ["✅ 技术形态 intact"],
            action=action
        )

    # ==================== 第四层：整合决策 ====================

    def integrate_decision(self, scores: Dict, failures: List[FailureCheck]) -> Dict:
        """整合评分与失效检测，生成最终决策"""

        # 基础评分
        total_score = sum(s['score'] * self.weights.get(k, 0.1)
                         for k, s in scores.items() if 'score' in s)

        # 失效调整
        critical_count = sum(1 for f in failures if f.triggered and f.severity == "CRITICAL")
        high_count = sum(1 for f in failures if f.triggered and f.severity == "HIGH")

        # 严重失效直接降级
        if critical_count > 0:
            adjusted_score = max(0, total_score - 30)
            signal = "EMERGENCY_EXIT"
            action = "🚨 紧急清仓"
        elif high_count > 0:
            adjusted_score = max(0, total_score - 15)
            signal = "REDUCE_POSITION"
            action = "⚠️ 减半持仓"
        elif total_score >= 75:
            signal = "STRONG_BUY"
            action = "🚀 积极介入"
        elif total_score >= 60:
            signal = "WATCH"
            action = "👀 跟踪观察"
        else:
            signal = "AVOID"
            action = "🚫 暂时回避"

        # 生成交易计划
        tech_levels = scores.get('technical', {}).get('levels', {})
        current = tech_levels.get('current', 0)

        plan = {
            'original_score': round(total_score, 1),
            'adjusted_score': round(adjusted_score, 1),
            'score_delta': round(adjusted_score - total_score, 1),
            'signal': signal,
            'action': action,
            'critical_failures': critical_count,
            'high_failures': high_count,
            'entry_price': current,
            'target_price': round(current * 1.25, 2) if current else 0,
            'stop_loss': round(current * 0.92, 2) if current else 0,
            'position_size': "HALF" if signal in ["STRONG_BUY"] else \
                           "QUARTER" if signal == "WATCH" else "NONE",
            'holding_period': 15
        }

        return plan

    # ==================== 主入口 ====================

    def analyze(self, stock_code: str, position: Optional[Dict] = None) -> Dict:
        """
        完整分析流程
        :param stock_code: 股票代码
        :param position: {'entry_price': x, 'current_price': y, 'holding_days': z}
        """
        self.stock_code = stock_code
        self.position = position

        # 1. 获取数据
        self.fetch_data(stock_code)
        rt = self.data_cache.get('realtime', {})
        self.stock_name = rt.get('名称', '未知')

        print(f"\n{'='*70}")
        print(f"🔍 分析 {self.stock_name}({stock_code}) | 策略：10-20 天 25%+")
        if position:
            pnl = (position['current_price'] - position['entry_price']) / position['entry_price'] * 100
            print(f"📊 当前持仓：成本¥{position['entry_price']} 现价¥{position['current_price']} 盈亏{pnl:+.1f}%")
        print(f"{'='*70}\n")

        # 2. 五维分析
        scores = {
            'catalyst': self.analyze_catalyst(),
            'capital': self.analyze_capital(),
            'sector': {'score': 55, 'evidence': ['板块中性']},  # 简化
            'technical': self.analyze_technical(),
            'fundamental': {'score': 60, 'evidence': ['基本面正常']}
        }

        # 3. 失效检测 (核心)
        failures = self.detect_failure_modes()

        # 4. 整合决策
        plan = self.integrate_decision(scores, failures)

        return {
            'stock_code': stock_code,
            'stock_name': self.stock_name,
            'scores': scores,
            'failure_modes': [
                {
                    'mode': f.mode.value,
                    'triggered': f.triggered,
                    'severity': f.severity,
                    'evidence': f.evidence,
                    'action': f.action
                } for f in failures
            ],
            'trade_plan': plan,
            'risk_guardrails': {
                'max_loss': f"{self.risk.max_loss_per_trade*100:.0f}%",
                'time_stop': f"{self.risk.time_stop_days}日",
                'profit_protect': f"回撤{self.risk.profit_protect_ratio*100:.0f}%"
            }
        }

    def format_report(self, result: Dict) -> str:
        """
        格式化输出报告（OpenClaw 标准格式）
        :param result: analyze() 返回的结果字典
        """
        scores = result['scores']
        plan = result['trade_plan']
        failures = result['failure_modes']
        guardrails = result['risk_guardrails']

        # 评分等级
        total_score = plan['original_score']
        if total_score >= 80:
            grade, grade_desc = "🟢", "强烈关注"
        elif total_score >= 70:
            grade, grade_desc = "🟡", "积极跟踪"
        elif total_score >= 60:
            grade, grade_desc = "🟠", "中性观望"
        elif total_score >= 45:
            grade, grade_desc = "⚪", "暂时回避"
        else:
            grade, grade_desc = "🔴", "明确回避"

        # 核心逻辑概括
        catalyst_ev = scores['catalyst']['evidence'][0] if scores['catalyst']['evidence'] else "暂无"
        capital_ev = scores['capital']['evidence'][0] if scores['capital']['evidence'] else "暂无"
        tech_ev = scores['technical']['evidence'][0] if scores['technical']['evidence'] else "暂无"
        core_logic = f"{catalyst_ev} + {capital_ev} + {tech_ev}"

        # 构建报告
        report = f"""
{'='*70}
【股票识别】
- 代码：{result['stock_code']}
- 名称：{result['stock_name']}
- 分析时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}

【综合评分】{total_score}/100 {grade} {grade_desc}
调整后评分：{plan['adjusted_score']} (delta: {plan['score_delta']:+.1f})

【核心逻辑】
{core_logic}

【五维拆解】
| 维度     | 得分 | 权重 | 关键证据                     |
|:---------|:----:|:----:|:-----------------------------|
| 催化剂   | {scores['catalyst']['score']:>4} | 30%  | {scores['catalyst']['evidence'][0][:26]:<26} |
| 资金异动 | {scores['capital']['score']:>4} | 25%  | {scores['capital']['evidence'][0][:26]:<26} |
| 板块效应 | {scores['sector']['score']:>4} | 20%  | {scores['sector']['evidence'][0][:26]:<26} |
| 技术形态 | {scores['technical']['score']:>4} | 15%  | {scores['technical']['evidence'][0][:26]:<26} |
| 基本面   | {scores['fundamental']['score']:>4} | 10%  | {scores['fundamental']['evidence'][0][:26]:<26} |

【失效状况扫描】⚠️ 持仓必检
| 失效模式     | 状态     | 级别     | 行动     |
|:-------------|:--------:|:--------:|:---------|
| 催化剂失效   | {"🔴 触发" if failures[0]['triggered'] else "🟢 正常":<8} | {failures[0]['severity']:<8} | {failures[0]['action']:<8} |
| 资金撤离     | {"🔴 触发" if failures[1]['triggered'] else "🟢 正常":<8} | {failures[1]['severity']:<8} | {failures[1]['action']:<8} |
| 技术破位     | {"🔴 触发" if failures[2]['triggered'] else "🟢 正常":<8} | {failures[2]['severity']:<8} | {failures[2]['action']:<8} |

【交易计划】
- 操作信号：{plan['signal']}
- 行动指令：{plan['action']}
- 建仓区间：¥{plan['entry_price']:.2f} (±2%)
- 目标价位：¥{plan['target_price']:.2f} (+25%)
- 止损价位：¥{plan['stop_loss']:.2f} (-8%)
- 建议仓位：{plan['position_size']}
- 持仓周期：{plan['holding_period']}天

【风控护栏】
• 硬性止损：{guardrails['max_loss']}
• 时间止损：{guardrails['time_stop']}
• 利润保护：{guardrails['profit_protect']}

【关键价位】
- 当前价：¥{scores['technical'].get('levels', {}).get('current', 0):.2f}
- 支撑位：¥{scores['technical'].get('levels', {}).get('support', 0):.2f}
- 压力位：¥{scores['technical'].get('levels', {}).get('resistance', 0):.2f}

【决策规则】
🚨 任一 CRITICAL 失效 → 立即清仓，不问成本
⚠️  任一 HIGH 失效     → 减半持仓，观察 3 日
🛑 评分<60 且存在失效 → 回避
✅ 评分>75 且无失效   → 积极介入
{'='*70}
"""
        return report


# ==================== OpenClaw 提示词模板 ====================

OPENCLAW_PROMPT = """
## Role: 短线暴涨交易专家 (含失效模式检测)

你正在使用 **Short-Term Surge Detector v2.0** 分析股票。

### 分析流程
1. 五维评分 (催化剂 30%/资金 25%/板块 20%/技术 15%/基本面 10%)
2. **三大失效检测** (持仓后每日必检)
3. 风控整合决策

### 三大失效状况定义

**失效 1: 催化剂失效 (Catalyst Invalid)**
- 触发条件:
  • 公告澄清/否认此前传闻
  • 订单/合同终止或延期超 3 个月
  • 业绩预增修正为预减
  • 政策/监管突发利空
- 级别：CRITICAL (立即清仓)

**失效 2: 资金撤离 (Capital Withdrawal)**
- 触发条件:
  • 连续 3 日主力资金净流出
  • 龙虎榜显示机构大额卖出
  • 量价背离 (价涨量缩>30% 或 价跌量增>50%)
  • 换手率骤降 50% (流动性枯竭)
- 级别：HIGH (减半持仓) / CRITICAL (连续 5 日流出)

**失效 3: 技术破位 (Technical Breakdown)**
- 触发条件:
  • 跌破固定止损位 (-8%)
  • 跌破关键支撑位 (20 日低点或 MA20 下方 3%)
  • 时间止损：5 日未启动 (涨幅<5%)
  • 利润保护：从高点回撤 60% 止盈
  • 出现墓碑线 (冲高回落>5% 且收阴)
- 级别：CRITICAL (立即清仓) / MEDIUM (减仓 1/3)

### 输出格式

**【五维评分】**
| 维度 | 得分 | 权重 | 关键证据 |
| 催化剂 | {cat_score} | 30% | {evidence} |
| 资金异动 | {cap_score} | 25% | {evidence} |
| 板块效应 | {sec_score} | 20% | {evidence} |
| 技术形态 | {tech_score} | 15% | {evidence} |
| 基本面 | {fund_score} | 10% | {evidence} |
**综合评分**: {total_score}/100

**【失效状况扫描】** ⚠️ 持仓必检
| 失效模式 | 状态 | 级别 | 证据 | 行动 |
| 催化剂失效 | {status1} | {severity1} | {evidence1} | {action1} |
| 资金撤离 | {status2} | {severity2} | {evidence2} | {action2} |
| 技术破位 | {status3} | {severity3} | {evidence3} | {action3} |

**【风控护栏】**
• 硬性止损：-8% (单票最大亏损)
• 时间止损：5 日不启动则离场
• 利润保护：从高点回撤 60% 止盈

**【交易计划】**
- 原始评分：{original_score} → 调整后：{adjusted_score} ({delta})
- 操作信号：{signal}
- 行动指令：{action}
- 建仓价：¥{entry} | 目标价：¥{target} (+25%) | 止损：¥{stop} (-8%)
- 建议仓位：{position}

**【持仓监控清单】** (每日勾选)
□ 检查最新公告 (是否澄清/否认)
□ 查看资金流向 (是否连续流出)
□ 确认技术位置 (是否破支撑)
□ 计算当前盈亏 (是否触发止损)

### 决策规则
- 任一 CRITICAL 失效 → 立即清仓，不问成本
- 任一 HIGH 失效 → 减半持仓，观察 3 日
- 评分<60 且存在失效 → 回避
- 评分>75 且无失效 → 积极介入

### 用户输入
股票：{stock_code}
持仓状态：{position_status}
请执行完整分析。
"""


# ==================== 使用示例 ====================

if __name__ == "__main__":
    detector = ShortTermSurgeDetector()

    # 场景 1: 空仓分析
    print("\n" + "="*70)
    print("示例 1: 空仓状态 - 赞宇科技")
    print("="*70)

    # 模拟运行 (实际应接入真实数据)
    result1 = {
        'stock_code': '002637',
        'stock_name': '赞宇科技',
        'scores': {
            'catalyst': {'score': 65, 'evidence': ['回购进行中', '印尼成本优势']},
            'capital': {'score': 55, 'evidence': ['3 月 6 日放量涨停', '后续资金分歧']},
            'sector': {'score': 60, 'evidence': ['化工板块轮动']},
            'technical': {'score': 58, 'evidence': ['震荡整理'], 'levels': {'current': 14.43}},
            'fundamental': {'score': 72, 'evidence': ['产能龙头']}
        },
        'failure_modes': [
            {'mode': '催化剂失效', 'triggered': False, 'severity': 'LOW', 'evidence': ['逻辑成立'], 'action': '持有'},
            {'mode': '资金撤离', 'triggered': False, 'severity': 'LOW', 'evidence': ['资金正常'], 'action': '持有'},
            {'mode': '技术破位', 'triggered': False, 'severity': 'LOW', 'evidence': ['未持仓'], 'action': 'N/A'}
        ],
        'trade_plan': {
            'original_score': 62.0,
            'adjusted_score': 62.0,
            'signal': 'WATCH',
            'action': '👀 跟踪观察',
            'entry_price': 14.43,
            'target_price': 18.04,
            'stop_loss': 13.28,
            'position_size': 'QUARTER'
        }
    }

    print(f"\n【五维评分】")
    for k, v in result1['scores'].items():
        print(f"  {k}: {v['score']}分 - {v['evidence'][0]}")

    print(f"\n【失效状况】")
    for f in result1['failure_modes']:
        status = "🔴 触发" if f['triggered'] else "🟢 正常"
        print(f"  {f['mode']}: {status} ({f['severity']}) - {f['action']}")

    print(f"\n【交易计划】")
    plan = result1['trade_plan']
    print(f"  信号：{plan['signal']}")
    print(f"  行动：{plan['action']}")
    print(f"  建仓：¥{plan['entry_price']} → 目标：¥{plan['target_price']} (+25%)")
    print(f"  止损：¥{plan['stop_loss']} (-8%)")
    print(f"  仓位：{plan['position_size']}")

    # 场景 2: 持仓后触发失效
    print("\n" + "="*70)
    print("示例 2: 持仓状态 - 触发技术破位")
    print("="*70)

    position = {'entry_price': 14.5, 'current_price': 13.2, 'holding_days': 5}
    pnl = (position['current_price'] - position['entry_price']) / position['entry_price'] * 100

    print(f"持仓信息：成本¥{position['entry_price']} 现价¥{position['current_price']} 盈亏{pnl:.1f}% 持有{position['holding_days']}日")

    failures_held = [
        {'mode': '催化剂失效', 'triggered': False, 'severity': 'LOW', 'evidence': ['逻辑成立'], 'action': '持有'},
        {'mode': '资金撤离', 'triggered': True, 'severity': 'MEDIUM', 'evidence': ['连续 2 日流出'], 'action': '减仓 1/3'},
        {'mode': '技术破位', 'triggered': True, 'severity': 'CRITICAL',
         'evidence': ['🛑 触发固定止损：亏损 9.0% (>8%)', '⏰ 时间止损：5 日未启动'], 'action': '立即清仓'}
    ]

    print(f"\n【失效扫描结果】")
    for f in failures_held:
        status = "🔴 触发" if f['triggered'] else "🟢 正常"
        emoji = {"CRITICAL": "💀", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(f['severity'], "")
        print(f"  {f['mode']}: {status} {emoji} {f['severity']}")
        for e in f['evidence']:
            print(f"    └─ {e}")
        print(f"    → 建议：{f['action']}")

    print(f"\n🚨 触发 1 项 CRITICAL 失效，执行立即清仓！")
    print(f"{'='*70}")
