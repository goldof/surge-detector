# -*- coding: utf-8 -*-
"""
Sync analysis results to Feishu Bitable
Only save stocks with score >= 70
"""

import requests
import json
from datetime import datetime, timedelta

# Feishu Bitable config
APP_TOKEN = 'Lx7db28mYag0KUsVoSNcAdOBnld'
TABLE_ID = 'tblaxSwGmpYwWk42'

# Get token from environment or config
try:
    from config import FEISHU_TOKEN
except ImportError:
    FEISHU_TOKEN = ''  # Set your Feishu API token here

def sync_to_bitable(result, stock_name=''):
    """
    Sync analysis result to Feishu Bitable
    
    Args:
        result: dict from surge_analyzer.py
        stock_name: string
    """
    if result['total_score'] < 70:
        print(f'[SKIP] Score {result["total_score"]:.1f} < 70, not syncing')
        return False
    
    if not FEISHU_TOKEN:
        print('[ERROR] FEISHU_TOKEN not set')
        return False
    
    # Calculate review date (20 days later)
    review_date = datetime.now() + timedelta(days=20)
    
    # Prepare record
    record = {
        'fields': {
            '股票名称': stock_name,
            '股票代码': result['stock_code'],
            '入选日期': int(datetime.now().timestamp() * 1000),
            '综合评分': result['total_score'],
            '分析时价格': result['current_price'],
            '目标价': result['target_price'],
            '止损价': result['stop_loss'],
            '分析报告': f"5D:{result.get('ret_5d', 'N/A')}% VolRatio:{result.get('vol_ratio', 'N/A')}x",
            '20 天后复盘': f'待复盘（{review_date.strftime("%Y-%m-%d")}）',
            '复盘日期': int(review_date.timestamp() * 1000)
        }
    }
    
    # API endpoint
    url = f'https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records'
    
    headers = {
        'Authorization': f'Bearer {FEISHU_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # Send request
    response = requests.post(url, headers=headers, json={'records': [record]})
    
    if response.status_code == 200:
        print(f'[OK] Synced {result["stock_code"]} to Feishu Bitable')
        return True
    else:
        print(f'[ERROR] Failed to sync: {response.text}')
        return False

if __name__ == '__main__':
    # Test
    test_result = {
        'stock_code': '600135',
        'total_score': 72.2,
        'current_price': 11.22,
        'target_price': 14.03,
        'stop_loss': 10.32,
        'ret_5d': 23.8,
        'vol_ratio': 2.24
    }
    
    sync_to_bitable(test_result, '乐凯胶片')
