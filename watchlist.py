# -*- coding: utf-8 -*-
"""
Watchlist Manager - Manage your focused stock pool
Add, remove, list, and analyze watched stocks
"""

import os
import sys
import json
from datetime import datetime

WATCHLIST_FILE = 'watchlist.json'

def load_watchlist():
    """Load watchlist from file"""
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_watchlist(watchlist):
    """Save watchlist to file"""
    with open(WATCHLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)

def add_stock(stock_code, stock_name=None, notes=''):
    """Add a stock to watchlist"""
    watchlist = load_watchlist()
    
    # Check if already exists
    for stock in watchlist:
        if stock['code'] == stock_code:
            print(f'[WARN] {stock_code} already in watchlist')
            return False
    
    # Add new stock
    watchlist.append({
        'code': stock_code,
        'name': stock_name or '',
        'notes': notes,
        'added_date': datetime.now().strftime('%Y-%m-%d %H:%M')
    })
    
    save_watchlist(watchlist)
    print(f'[OK] Added {stock_code} - {stock_name or "Unknown"} to watchlist')
    return True

def remove_stock(stock_code):
    """Remove a stock from watchlist"""
    watchlist = load_watchlist()
    
    for i, stock in enumerate(watchlist):
        if stock['code'] == stock_code:
            removed = watchlist.pop(i)
            save_watchlist(watchlist)
            print(f'[OK] Removed {stock_code} - {removed["name"]} from watchlist')
            return True
    
    print(f'[ERROR] {stock_code} not found in watchlist')
    return False

def list_stocks():
    """List all stocks in watchlist"""
    watchlist = load_watchlist()
    
    if not watchlist:
        print('Watchlist is empty')
        print()
        print('Usage:')
        print('  python watchlist.py add 600135 乐凯胶片 "5 日+23.8%"')
        return []
    
    print('=' * 70)
    print('WATCHLIST')
    print(f'Total: {len(watchlist)} stocks')
    print('=' * 70)
    print(f'| #  | Code   | Name                  | Notes                    | Added      |')
    print(f'|:--:|:-------|:----------------------|:-------------------------|:-----------|')
    
    for i, stock in enumerate(watchlist, 1):
        code = stock['code']
        name = (stock['name'] or 'Unknown')[:20].ljust(20)
        notes = (stock['notes'] or '-')[:24].ljust(24)
        added = stock['added_date'][:10]
        print(f'| {i:>2} | {code} | {name} | {notes} | {added} |')
    
    print('=' * 70)
    return watchlist

def analyze_all():
    """Analyze all stocks in watchlist"""
    watchlist = load_watchlist()
    
    if not watchlist:
        print('Watchlist is empty')
        return
    
    print(f'Analyzing {len(watchlist)} stocks...')
    print()
    
    # Import analyzer
    from surge_analyzer import analyze_stock
    
    results = []
    for stock in watchlist:
        print(f'\n{"="*70}')
        print(f'Analyzing {stock["code"]} ({stock["name"]})...')
        print(f'{"="*70}\n')
        
        result = analyze_stock(stock['code'], stock['name'])
        if result:
            results.append(result)
    
    # Summary
    print('\n')
    print('=' * 70)
    print('WATCHLIST SUMMARY')
    print('=' * 70)
    
    # Sort by score
    results.sort(key=lambda x: x['total_score'], reverse=True)
    
    print(f'| Rank | Code   | Score | Signal      | Price    | Name            |')
    print(f'|:----:|:-------|:-----:|:------------|:---------|:----------------|')
    
    for i, r in enumerate(results, 1):
        name = (r['stock_code'] + (' ' * 12))[:14]
        if r['stock_code'] in [s['code'] for s in watchlist]:
            for s in watchlist:
                if s['code'] == r['stock_code']:
                    name = (s['name'] or r['stock_code'])[:14]
                    break
        
        print(f'| {i:>4} | {r["stock_code"]} | {r["total_score"]:>5.1f} | {r["signal"]:<11} | {r["current_price"]:>8.2f} | {name:<14} |')
    
    print()
    
    # Filter by signal
    strong_buy = [r for r in results if r['signal'] == 'STRONG_BUY']
    watch = [r for r in results if r['signal'] == 'WATCH']
    avoid = [r for r in results if r['signal'] == 'AVOID']
    
    print(f'STRONG_BUY (>=75): {len(strong_buy)} stocks')
    print(f'WATCH (60-75):     {len(watch)} stocks')
    print(f'AVOID (<60):       {len(avoid)} stocks')
    print()
    
    if strong_buy:
        print('🚀 TOP PICKS:')
        for r in strong_buy:
            print(f'  - {r["stock_code"]}: {r["total_score"]:.1f} @ RMB {r["current_price"]:.2f}')
    
    if watch:
        print('\n👀 WATCH LIST:')
        for r in watch:
            print(f'  - {r["stock_code"]}: {r["total_score"]:.1f} @ RMB {r["current_price"]:.2f}')
    
    print('=' * 70)

def main():
    if len(sys.argv) < 2:
        print('Watchlist Manager')
        print()
        print('Usage:')
        print('  python watchlist.py list                  # List all stocks')
        print('  python watchlist.py add 600135 乐凯胶片 "5 日+23.8%"  # Add stock')
        print('  python watchlist.py remove 600135         # Remove stock')
        print('  python watchlist.py analyze               # Analyze all')
        print()
        return
    
    action = sys.argv[1].lower()
    
    if action == 'list':
        list_stocks()
    
    elif action == 'add':
        if len(sys.argv) < 3:
            print('[ERROR] Please provide stock code')
            return
        stock_code = sys.argv[2]
        stock_name = sys.argv[3] if len(sys.argv) > 3 else None
        notes = sys.argv[4] if len(sys.argv) > 4 else ''
        add_stock(stock_code, stock_name, notes)
    
    elif action == 'remove':
        if len(sys.argv) < 3:
            print('[ERROR] Please provide stock code')
            return
        remove_stock(sys.argv[2])
    
    elif action == 'analyze':
        analyze_all()
    
    else:
        print(f'[ERROR] Unknown action: {action}')

if __name__ == '__main__':
    main()
