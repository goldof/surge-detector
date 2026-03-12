"""
Short-Term Surge Detector - 测试用例
测试短线暴涨探测器的核心功能
"""

import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta

from SurgeDetector import (
    ShortTermSurgeDetector,
    FailureMode,
    FailureCheck,
    RiskGuardrails
)


class TestRiskGuardrails(unittest.TestCase):
    """测试风控护栏参数"""

    def test_default_values(self):
        """测试默认参数值"""
        risk = RiskGuardrails()
        self.assertEqual(risk.max_loss_per_trade, 0.08)
        self.assertEqual(risk.time_stop_days, 5)
        self.assertEqual(risk.profit_protect_ratio, 0.6)
        self.assertEqual(risk.volume_collapse_ratio, 0.5)


class TestFailureMode(unittest.TestCase):
    """测试失效模式枚举"""

    def test_failure_modes(self):
        """测试三种失效模式"""
        self.assertEqual(FailureMode.CATALYST_INVALID.value, "催化剂失效")
        self.assertEqual(FailureMode.CAPITAL_WITHDRAWAL.value, "资金撤离")
        self.assertEqual(FailureMode.TECHNICAL_BREAKDOWN.value, "技术破位")


class TestFailureCheck(unittest.TestCase):
    """测试失效检查结果"""

    def test_failure_check_creation(self):
        """测试 FailureCheck 数据类创建"""
        check = FailureCheck(
            mode=FailureMode.CATALYST_INVALID,
            triggered=True,
            severity="CRITICAL",
            evidence=["测试证据"],
            action="立即清仓"
        )
        self.assertEqual(check.mode, FailureMode.CATALYST_INVALID)
        self.assertTrue(check.triggered)
        self.assertEqual(check.severity, "CRITICAL")
        self.assertEqual(check.evidence, ["测试证据"])
        self.assertEqual(check.action, "立即清仓")


class TestShortTermSurgeDetector(unittest.TestCase):
    """测试短线暴涨探测器主类"""

    def setUp(self):
        """测试前准备"""
        self.detector = ShortTermSurgeDetector()

    def test_initialization(self):
        """测试初始化"""
        self.assertIsNone(self.detector.stock_code)
        self.assertIsNone(self.detector.stock_name)
        self.assertEqual(self.detector.weights['catalyst'], 0.30)
        self.assertEqual(self.detector.weights['capital'], 0.25)
        self.assertEqual(self.detector.weights['sector'], 0.20)
        self.assertEqual(self.detector.weights['technical'], 0.15)
        self.assertEqual(self.detector.weights['fundamental'], 0.10)

    def test_weight_sum(self):
        """测试权重总和为 1"""
        total_weight = sum(self.detector.weights.values())
        self.assertAlmostEqual(total_weight, 1.0, places=2)

    @patch('SurgeDetector.ak.stock_zh_a_hist')
    @patch('SurgeDetector.ak.stock_zh_a_spot_em')
    @patch('SurgeDetector.ak.stock_individual_fund_flow')
    @patch('SurgeDetector.ak.stock_lhb_detail_daily_sina')
    @patch('SurgeDetector.ak.stock_notice_report')
    def test_fetch_data(self, mock_notice, mock_lhb, mock_flow, mock_spot, mock_hist):
        """测试数据获取（模拟）"""
        # 设置 mock 返回值
        mock_hist.return_value = pd.DataFrame({
            '收盘': [10.0, 10.5, 11.0, 10.8, 11.2],
            '最高': [10.2, 10.8, 11.5, 11.0, 11.5],
            '最低': [9.8, 10.2, 10.8, 10.5, 11.0],
            '成交量': [1000, 1200, 1500, 1300, 1400],
            '涨跌幅': [0, 5, 4.76, -1.82, 3.7]
        })
        mock_spot.return_value = pd.DataFrame({
            '代码': ['002637'],
            '名称': ['赞宇科技'],
            '所属概念': ['化工', '涨价概念']
        })
        mock_flow.return_value = pd.DataFrame({
            '主力净流入': [1000, -500, 2000, 1500, -300]
        })
        mock_lhb.return_value = pd.DataFrame()
        mock_notice.return_value = pd.DataFrame()

        data = self.detector.fetch_data('002637')

        self.assertIn('price', data)
        self.assertIn('realtime', data)
        self.assertIn('money_flow', data)
        self.assertEqual(self.detector.stock_code, '002637')

    def test_analyze_catalyst_no_data(self):
        """测试催化剂分析 - 无数据情况"""
        self.detector.data_cache = {}
        result = self.detector.analyze_catalyst()
        self.assertEqual(result['score'], 50)
        self.assertEqual(result['evidence'], ["暂无明确催化剂"])

    def test_analyze_capital_no_data(self):
        """测试资金分析 - 无数据情况"""
        self.detector.data_cache = {}
        result = self.detector.analyze_capital()
        self.assertEqual(result['score'], 50)
        self.assertEqual(result['evidence'], ['数据缺失'])

    def test_analyze_technical_no_data(self):
        """测试技术分析 - 无数据情况"""
        self.detector.data_cache = {}
        result = self.detector.analyze_technical()
        self.assertEqual(result['score'], 50)

    def test_detect_failure_modes_no_position(self):
        """测试失效检测 - 无持仓情况"""
        self.detector.data_cache = {'news': pd.DataFrame()}
        self.detector.position = None
        failures = self.detector.detect_failure_modes()
        self.assertEqual(len(failures), 3)
        # 技术破位应该是"未持仓"
        self.assertEqual(failures[2].mode, FailureMode.TECHNICAL_BREAKDOWN)
        self.assertFalse(failures[2].triggered)

    def test_integrate_decision_strong_buy(self):
        """测试整合决策 - 强烈买入"""
        scores = {
            'catalyst': {'score': 85},
            'capital': {'score': 80},
            'sector': {'score': 75},
            'technical': {'score': 80},
            'fundamental': {'score': 70}
        }
        failures = [
            FailureCheck(FailureMode.CATALYST_INVALID, False, "LOW", [], "持有"),
            FailureCheck(FailureMode.CAPITAL_WITHDRAWAL, False, "LOW", [], "持有"),
            FailureCheck(FailureMode.TECHNICAL_BREAKDOWN, False, "LOW", [], "持有")
        ]

        plan = self.detector.integrate_decision(scores, failures)
        self.assertEqual(plan['signal'], "STRONG_BUY")
        self.assertGreater(plan['original_score'], 75)

    def test_integrate_decision_emergency_exit(self):
        """测试整合决策 - 紧急清仓"""
        scores = {
            'catalyst': {'score': 85},
            'capital': {'score': 80},
            'sector': {'score': 75},
            'technical': {'score': 80},
            'fundamental': {'score': 70}
        }
        failures = [
            FailureCheck(FailureMode.CATALYST_INVALID, True, "CRITICAL", ["公告澄清"], "立即清仓"),
            FailureCheck(FailureMode.CAPITAL_WITHDRAWAL, False, "LOW", [], "持有"),
            FailureCheck(FailureMode.TECHNICAL_BREAKDOWN, False, "LOW", [], "持有")
        ]

        plan = self.detector.integrate_decision(scores, failures)
        self.assertEqual(plan['signal'], "EMERGENCY_EXIT")
        self.assertEqual(plan['critical_failures'], 1)

    def test_integrate_decision_reduce_position(self):
        """测试整合决策 - 减半持仓"""
        scores = {
            'catalyst': {'score': 85},
            'capital': {'score': 80},
            'sector': {'score': 75},
            'technical': {'score': 80},
            'fundamental': {'score': 70}
        }
        failures = [
            FailureCheck(FailureMode.CATALYST_INVALID, False, "LOW", [], "持有"),
            FailureCheck(FailureMode.CAPITAL_WITHDRAWAL, True, "HIGH", ["资金流出"], "减半持仓"),
            FailureCheck(FailureMode.TECHNICAL_BREAKDOWN, False, "LOW", [], "持有")
        ]

        plan = self.detector.integrate_decision(scores, failures)
        self.assertEqual(plan['signal'], "REDUCE_POSITION")
        self.assertEqual(plan['high_failures'], 1)

    def test_format_report(self):
        """测试格式化报告输出"""
        result = {
            'stock_code': '002637',
            'stock_name': '赞宇科技',
            'scores': {
                'catalyst': {'score': 65, 'evidence': ['回购进行中']},
                'capital': {'score': 55, 'evidence': ['资金正常']},
                'sector': {'score': 60, 'evidence': ['板块中性']},
                'technical': {'score': 58, 'evidence': ['震荡整理'], 'levels': {'current': 14.43, 'support': 13.5, 'resistance': 15.0}},
                'fundamental': {'score': 72, 'evidence': ['产能龙头']}
            },
            'failure_modes': [
                {'mode': '催化剂失效', 'triggered': False, 'severity': 'LOW', 'action': '持有观察'},
                {'mode': '资金撤离', 'triggered': False, 'severity': 'LOW', 'action': '持有观察'},
                {'mode': '技术破位', 'triggered': False, 'severity': 'LOW', 'action': 'N/A'}
            ],
            'trade_plan': {
                'original_score': 62.0,
                'adjusted_score': 62.0,
                'score_delta': 0.0,
                'signal': 'WATCH',
                'action': '👀 跟踪观察',
                'entry_price': 14.43,
                'target_price': 18.04,
                'stop_loss': 13.28,
                'position_size': 'QUARTER',
                'holding_period': 15
            },
            'risk_guardrails': {
                'max_loss': '8%',
                'time_stop': '5 日',
                'profit_protect': '回撤 60%'
            }
        }

        report = self.detector.format_report(result)
        self.assertIn('002637', report)
        self.assertIn('赞宇科技', report)
        self.assertIn('【综合评分】', report)
        self.assertIn('【交易计划】', report)


class TestCatalystDenialKeywords(unittest.TestCase):
    """测试催化剂否认关键词"""

    def setUp(self):
        self.detector = ShortTermSurgeDetector()

    def test_keywords_pattern(self):
        """测试关键词正则匹配"""
        import re
        test_cases = [
            ("澄清公告", True),
            ("否认传闻", True),
            ("业绩预增 50%", False),
            ("合同终止", True),
            ("收到监管函", True),
            ("正常经营", False)
        ]

        for text, should_match in test_cases:
            matched = bool(re.search(self.detector.catalyst_denial_keywords, text))
            self.assertEqual(matched, should_match, f"测试失败：{text}")


if __name__ == '__main__':
    unittest.main()
