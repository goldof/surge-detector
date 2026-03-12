# -*- coding: utf-8 -*-
"""
Batch Stock Analyzer - Analyze multiple stocks at once
Usage: python batch_analyze.py stock1 stock2 stock3 ...
"""

import sys
import os
from datetime import datetime

# Import the analyzer
from surge_analyzer import analyze_stock

# Stock pool to analyze
DEFAULT_STOCKS = [
    ('603527', 'Zhongyuan New Materials'),
    ('300502', 'Xin Yi Sheng'),
    ('600410', 'Hua Sheng Tian Cheng'),
    ('688256', 'Han Wu Ji'),
    ('688008', 'Lan Qi Ke Ji'),
    ('002085', 'Wan Feng Ao Wei'),
]

def main():
    # Get stocks from command line or use default pool
    if len(sys.argv) > 1:
        stocks = [(sys.argv[i], sys.argv[i+1] if i+1 < len(sys.argv) and not sys.argv[i+1].startswith('0') else None) 
                  for i in range(1, len(sys.argv), 2)]
    else:
        stocks = DEFAULT_STOCKS
    
    print('=' * 70)
    print('BATCH STOCK ANALYZER')
    print(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'Total Stocks: {len(stocks)}')
    print('=' * 70)
    print()
    
    results = []
    
    for i, (stock_code, stock_name) in enumerate(stocks, 1):
        print(f'\n{"="*70}')
        print(f'[{i}/{len(stocks)}] Analyzing {stock_code}...')
        print(f'{"="*70}\n')
        
        result = analyze_stock(stock_code, stock_name)
        
        if result:
            results.append(result)
    
    # Summary
    print('\n')
    print('=' * 70)
    print('SUMMARY')
    print('=' * 70)
    print(f'| Code   | Name                  | Score | Signal      | Price    |')
    print(f'|:-------|:----------------------|:-----:|:------------|:---------|')
    
    for r in results:
        name = (r['stock_code'] + (' ' * 20))[:20]
        print(f'| {r["stock_code"]} | {name} | {r["total_score"]:>5.1f} | {r["signal"]:<11} | {r["current_price"]:>8.2f} |')
    
    print()
    
    # Filter by signal
    strong_buy = [r for r in results if r['signal'] == 'STRONG_BUY']
    watch = [r for r in results if r['signal'] == 'WATCH']
    avoid = [r for r in results if r['signal'] == 'AVOID']
    
    print(f'STRONG_BUY: {len(strong_buy)} stocks')
    print(f'WATCH: {len(watch)} stocks')
    print(f'AVOID: {len(avoid)} stocks')
    print()
    
    if strong_buy:
        print('Top Picks (Score >= 75):')
        for r in sorted(strong_buy, key=lambda x: x['total_score'], reverse=True):
            print(f'  - {r["stock_code"]}: {r["total_score"]:.1f} @ RMB {r["current_price"]:.2f}')
    
    if watch:
        print('\nWatch List (60 <= Score < 75):')
        for r in sorted(watch, key=lambda x: x['total_score'], reverse=True):
            print(f'  - {r["stock_code"]}: {r["total_score"]:.1f} @ RMB {r["current_price"]:.2f}')
    
    print('=' * 70)
    
    # Save to CSV
    csv_file = f'analysis_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    import pandas as pd
    df = pd.DataFrame(results)
    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f'\nResults saved to: {csv_file}')
    print('=' * 70)


if __name__ == '__main__':
    main()
