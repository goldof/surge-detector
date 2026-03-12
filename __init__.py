"""
Short-Term Surge Detector v2.0
短线暴涨探测器 - OpenClaw Skill

含三大失效模式检测，目标 10-20 天 25%+ 涨幅
"""

from .SurgeDetector import (
    ShortTermSurgeDetector,
    FailureMode,
    FailureCheck,
    RiskGuardrails,
    OPENCLAW_PROMPT
)

__version__ = "2.0.0"
__author__ = "OpenClaw Community"
__all__ = [
    "ShortTermSurgeDetector",
    "FailureMode",
    "FailureCheck",
    "RiskGuardrails",
    "OPENCLAW_PROMPT"
]
