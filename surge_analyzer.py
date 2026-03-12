# -*- coding: utf-8 -*-
"""
Short-Term Surge Detector - Data Fetcher with AKShare + Tushare fallback
Optimized with retry mechanism, timeout control, and dual data sources
"""

import akshare as ak
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import time
import sys
import os

# Set UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

# Tushare Token (load from environment variable or config file)
# Set environment variable: TUSHARE_TOKEN=your_token_here
# Or create config.py with: TUSHARE_TOKEN = 'your_token_here'
import os
try:
    from config import TUSHARE_TOKEN
except ImportError:
    TUSHARE_TOKEN = os.getenv('TUSHARE_TOKEN', '')

class DataFetcher:
    """Dual data source fetcher: AKShare primary, Tushare fallback"""
    
    def __init__(self, max_retries=3, timeout=30):
        self.max_retries = max_retries
        self.timeout = timeout
        self.ts_pro = ts.pro_api(TUSHARE_TOKEN)
        self.source_used = None  # Track which source was used
    
    def fetch_with_retry(self, func, *args, fallback_func=None, **kwargs):
        """Fetch data with retry mechanism and fallback"""
        # Try primary source (AKShare)
        for attempt in range(self.max_retries):
            try:
                result = func(*args, **kwargs)
                if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                    self.source_used = 'AKShare'
                    return result
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f'  [AKShare Retry] {attempt + 1}/{self.max_retries}: {str(e)[:40]}')
                    time.sleep(2 ** attempt)
                else:
                    print(f'  [AKShare Failed] All {self.max_retries} attempts failed')
                    break
        
        # Try fallback source (Tushare)
        if fallback_func:
            print('  [Switching to Tushare...]')
            for attempt in range(self.max_retries):
                try:
                    result = fallback_func(*args, **kwargs)
                    if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                        self.source_used = 'Tushare'
                        return result
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        print(f'  [Tushare Retry] {attempt + 1}/{self.max_retries}: {str(e)[:40]}')
                        time.sleep(2 ** attempt)
                    else:
                        print(f'  [Tushare Failed] All attempts failed')
                        break
        
        self.source_used = 'None'
        return None
    
    def get_realtime_price(self, stock_code):
        """Get real-time price (mandatory verification)"""
        
        def ak_fetch():
            spot = ak.stock_zh_a_spot_em()
            if spot is not None and not spot.empty:
                result = spot[spot['代码'] == stock_code]
                if not result.empty:
                    return {
                        'price': float(result.iloc[0]['最新价']),
                        'change': float(result.iloc[0]['涨跌幅']),
                        'volume': float(result.iloc[0]['成交量']),
                        'turnover': float(result.iloc[0]['成交额']),
                        'high': float(result.iloc[0]['最高']),
                        'low': float(result.iloc[0]['最低']),
                        'open': float(result.iloc[0]['今开'])
                    }
            return None
        
        def ts_fetch():
            if stock_code.startswith('6'):
                ts_code = f'{stock_code}.SH'
            else:
                ts_code = f'{stock_code}.SZ'
            
            df = self.ts_pro.daily(ts_code=ts_code, start_date=datetime.now().strftime('%Y%m%d'))
            if df is not None and not df.empty:
                return {
                    'price': float(df.iloc[0]['close']),
                    'change': float(df.iloc[0]['pct_chg']),
                    'volume': float(df.iloc[0]['vol']),
                    'turnover': None,
                    'high': float(df.iloc[0]['high']),
                    'low': float(df.iloc[0]['low']),
                    'open': float(df.iloc[0]['open'])
                }
            return None
        
        return self.fetch_with_retry(ak_fetch, fallback_func=ts_fetch)
    
    def get_kline_data(self, stock_code, days=60):
        """Get K-line data with dual source"""
        
        # AKShare method
        def ak_fetch():
            return ak.stock_zh_a_hist(
                symbol=stock_code,
                period='daily',
                start_date=(datetime.now() - timedelta(days=days)).strftime('%Y%m%d'),
                end_date=datetime.now().strftime('%Y%m%d'),
                adjust='qfq'
            )
        
        # Tushare fallback
        def ts_fetch():
            # Convert stock code to Tushare format
            if stock_code.startswith('6'):
                ts_code = f'{stock_code}.SH'
            else:
                ts_code = f'{stock_code}.SZ'
            
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
            
            df = self.ts_pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is not None and not df.empty:
                # Rename columns to match AKShare format
                df = df.rename(columns={
                    'trade_date': '日期',
                    'open': '开盘',
                    'high': '最高',
                    'low': '最低',
                    'close': '收盘',
                    'vol': '成交量',
                    'amount': '成交额',
                    'pct_chg': '涨跌幅'
                })
                # Reverse to chronological order
                df = df.iloc[::-1].reset_index(drop=True)
            
            return df
        
        return self.fetch_with_retry(ak_fetch, fallback_func=ts_fetch)
    
    def get_money_flow(self, stock_code, market='sh'):
        """Get money flow data"""
        
        def ak_fetch():
            return ak.stock_individual_fund_flow(stock=stock_code, market=market)
        
        # Tushare fallback for money flow
        def ts_fetch():
            if stock_code.startswith('6'):
                ts_code = f'{stock_code}.SH'
            else:
                ts_code = f'{stock_code}.SZ'
            
            # Get individual stock money flow
            df = self.ts_pro.moneyflow(ts_code=ts_code)
            return df.head(60)  # Return last 60 days
        
        return self.fetch_with_retry(ak_fetch, fallback_func=ts_fetch)
    
    def get_spot_data(self, stock_code):
        """Get real-time spot data"""
        
        def ak_fetch():
            spot = ak.stock_zh_a_spot_em()
            if spot is not None and not spot.empty:
                return spot[spot['代码'] == stock_code]
            return None
        
        def ts_fetch():
            if stock_code.startswith('6'):
                ts_code = f'{stock_code}.SH'
            else:
                ts_code = f'{stock_code}.SZ'
            
            df = self.ts_pro.daily(ts_code=ts_code, start_date=datetime.now().strftime('%Y%m%d'))
            return df
        
        return self.fetch_with_retry(ak_fetch, fallback_func=ts_fetch)


def analyze_stock(stock_code, stock_name=None):
    """Analyze a stock with real data from AKShare/Tushare"""
    
    print('=' * 70)
    print(f'Short-Term Surge Analyzer - {stock_code}')
    print(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 70)
    print()
    
    fetcher = DataFetcher(max_retries=3, timeout=30)
    
    # ===== 0. Get Real-time Price (MANDATORY VERIFICATION) =====
    print('[0/5] Fetching REAL-TIME price (mandatory)...')
    realtime = fetcher.get_realtime_price(stock_code)
    
    if realtime is None:
        print('  [WARN] Real-time price unavailable, will use K-line close')
        realtime_price = None
    else:
        print(f'  Data Source: {fetcher.source_used}')
        print(f'  REAL-TIME PRICE: RMB {realtime["price"]:.2f}')
        print(f'  Change: {realtime["change"]:.2f}%')
        print(f'  High: {realtime["high"]:.2f} | Low: {realtime["low"]:.2f}')
        realtime_price = realtime['price']
    print()
    
    # ===== 1. Get K-line Data =====
    print('[1/5] Fetching K-line data...')
    kline = fetcher.get_kline_data(stock_code)
    
    print(f'  Data Source: {fetcher.source_used}')
    
    if kline is None or kline.empty:
        print('[ERROR] Failed to fetch K-line data from both sources')
        return None
    
    print(f'  OK - {len(kline)} days of data')
    
    # Extract K-line metrics
    close = pd.to_numeric(kline['收盘'], errors='coerce')
    high = pd.to_numeric(kline['最高'], errors='coerce')
    low = pd.to_numeric(kline['最低'], errors='coerce')
    volume = pd.to_numeric(kline['成交量'], errors='coerce')
    pct_change = pd.to_numeric(kline['涨跌幅'], errors='coerce')
    
    # Use real-time price if available, otherwise use K-line close
    if realtime_price is not None:
        current_price = realtime_price
        print(f'  [VERIFIED] Using real-time price: RMB {current_price:.2f}')
    else:
        current_price = close.iloc[-1]
        print(f'  [WARN] Using K-line close: RMB {current_price:.2f}')
    
    high_60d = max(high.max(), realtime_price if realtime_price else 0)
    low_60d = low.min()
    ret_5d = pct_change.tail(5).sum()
    ret_10d = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] * 100 if len(close) > 10 else 0
    avg_vol_5d = volume.tail(5).mean()
    avg_vol_20d = volume.tail(20).mean()
    vol_ratio = avg_vol_5d / avg_vol_20d if avg_vol_20d > 0 else 1
    
    print()
    print('[K-line Metrics]')
    print(f'  Current Price: RMB {current_price:.2f} {"[REAL-TIME]" if realtime_price else "[K-LINE]"}')
    print(f'  60D Range: {low_60d:.2f} - {high_60d:.2f}')
    print(f'  5D Return: {ret_5d:.1f}%')
    print(f'  10D Return: {ret_10d:.1f}%')
    print(f'  Volume Ratio (5D/20D): {vol_ratio:.2f}x')
    print()
    
    # ===== 2. Get Money Flow =====
    print('[2/5] Fetching money flow data...')
    market = 'sz' if stock_code.startswith(('00', '30')) else 'sh'
    mf = fetcher.get_money_flow(stock_code, market)
    
    if mf is not None and not mf.empty:
        print(f'  Data Source: {fetcher.source_used}')
        print(f'  OK - {len(mf)} days of data')
        
        # Find money flow column (handle both AKShare and Tushare formats)
        target_col = None
        for col in mf.columns:
            col_str = str(col)
            if '主力' in col_str and '净流入' in col_str:
                target_col = col
                break
            elif 'buy_sm_amount' in col_str or 'net_mf_amount' in col_str:
                target_col = col
                break
        
        if target_col:
            inflow_5d = pd.to_numeric(mf.head(5)[target_col], errors='coerce').sum()
            inflow_10d = pd.to_numeric(mf.head(10)[target_col], errors='coerce').sum()
            print(f'  5D Net Inflow: {inflow_5d:.0f} wan yuan')
            print(f'  10D Net Inflow: {inflow_10d:.0f} wan yuan')
        else:
            print('  [WARN] Cannot find money flow column')
            inflow_5d = 0
            inflow_10d = 0
    else:
        print('  [WARN] Money flow data unavailable')
        inflow_5d = 0
        inflow_10d = 0
    print()
    
    # ===== 3. Calculate 5-Dimension Scores =====
    print('[3/5] Calculating 5-dimension scores...')
    
    # Catalyst (30%) - Default 50, can be enhanced with news API
    catalyst_final = 50
    
    # Capital (25%) - Based on 5D return and money flow
    capital_score = 50
    if ret_5d > 20:
        capital_score += 30
    elif ret_5d > 10:
        capital_score += 20
    elif ret_5d > 5:
        capital_score += 10
    
    if inflow_5d > 5000:
        capital_score += 20
    elif inflow_5d > 1000:
        capital_score += 10
    elif inflow_5d < -1000:
        capital_score -= 10
    
    capital_final = max(0, min(100, capital_score))
    
    # Sector (20%) - Based on volume ratio
    sector_score = 60
    if vol_ratio > 2:
        sector_score += 20
    elif vol_ratio > 1.5:
        sector_score += 10
    elif vol_ratio < 0.7:
        sector_score -= 10
    sector_final = max(0, min(100, sector_score))
    
    # Technical (15%) - Based on price position and trend
    price_position = (current_price - low_60d) / (high_60d - low_60d) * 100 if high_60d > low_60d else 50
    technical_score = 50
    
    if current_price >= high_60d * 0.98:
        technical_score += 30
    elif price_position > 70:
        technical_score += 20
    elif price_position > 50:
        technical_score += 10
    
    if ret_5d > 0 and ret_10d > 0:
        technical_score += 15
    elif ret_5d < 0 and ret_10d < 0:
        technical_score -= 10
    
    technical_final = max(0, min(100, technical_score))
    
    # Fundamental (10%) - Default 50
    fundamental_final = 50
    
    print(f'  Catalyst: {catalyst_final}')
    print(f'  Capital: {capital_final}')
    print(f'  Sector: {sector_final}')
    print(f'  Technical: {technical_final}')
    print(f'  Fundamental: {fundamental_final}')
    print()
    
    # ===== Calculate Total Score =====
    weights = {'catalyst': 0.30, 'capital': 0.25, 'sector': 0.20, 'technical': 0.15, 'fundamental': 0.10}
    scores = {
        'catalyst': catalyst_final,
        'capital': capital_final,
        'sector': sector_final,
        'technical': technical_final,
        'fundamental': fundamental_final
    }
    
    total_score = sum(scores[k] * weights[k] for k in scores)
    
    # ===== Determine Signal =====
    if total_score >= 75:
        signal = 'STRONG_BUY'
        action = 'Active Entry'
        position = 'HALF (50%)'
    elif total_score >= 60:
        signal = 'WATCH'
        action = 'Active Track'
        position = 'QUARTER (25%)'
    else:
        signal = 'AVOID'
        action = 'Stay Away'
        position = 'NONE (0%)'
    
    target_price = round(current_price * 1.25, 2)
    stop_loss = round(current_price * 0.92, 2)
    
    # ===== 4. Output Report =====
    print()
    print('=' * 70)
    print('ANALYSIS REPORT')
    print('=' * 70)
    print(f'Stock: {stock_code} - {stock_name or "Unknown"}')
    print(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print(f'Data Source: {fetcher.source_used}')
    if realtime_price:
        print(f'** REAL-TIME PRICE VERIFIED: RMB {realtime_price:.2f} **')
    print()
    print(f'TOTAL SCORE: {total_score:.1f}/100')
    print(f'SIGNAL: {signal}')
    print()
    print('5-DIMENSION BREAKDOWN:')
    print('| Dimension   | Score | Weight | Status                      |')
    print('|:------------|:-----:|:------:|:----------------------------|')
    print(f'| Catalyst    | {catalyst_final:>4}  |  30%   | Default (need news)         |')
    print(f'| Capital     | {capital_final:>4}  |  25%   | 5D Return: {ret_5d:.1f}%               |')
    print(f'| Sector      | {sector_final:>4}  |  20%   | Volume Ratio: {vol_ratio:.2f}x            |')
    print(f'| Technical   | {technical_final:>4}  |  15%   | Position: {price_position:.0f}%               |')
    print(f'| Fundamental | {fundamental_final:>4}  |  10%   | Default (need earnings)     |')
    print()
    print('TRADE PLAN:')
    print(f'- Signal: {signal}')
    print(f'- Action: {action}')
    price_tag = '[REAL-TIME]' if realtime_price else '[K-LINE]'
    print(f'- Entry: RMB {current_price:.2f} (+/-2%) {price_tag}')
    print(f'- Target: RMB {target_price:.2f} (+25%)')
    print(f'- Stop Loss: RMB {stop_loss:.2f} (-8%)')
    print(f'- Position: {position}')
    print()
    print('KEY DATA:')
    print(f'- Current: RMB {current_price:.2f} {price_tag}')
    print(f'- 60D Range: RMB {low_60d:.2f} - RMB {high_60d:.2f}')
    print(f'- 5D Return: {ret_5d:.1f}%')
    print(f'- 10D Return: {ret_10d:.1f}%')
    print(f'- Volume Ratio: {vol_ratio:.2f}x')
    print(f'- 5D Money Flow: {inflow_5d:.0f} wan yuan')
    print('=' * 70)
    
    return {
        'stock_code': stock_code,
        'total_score': total_score,
        'signal': signal,
        'current_price': current_price,
        'target_price': target_price,
        'stop_loss': stop_loss,
        'position': position,
        'data_source': fetcher.source_used
    }


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        stock_code = sys.argv[1]
        stock_name = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        # Default test
        stock_code = '603527'
        stock_name = 'Zhongyuan New Materials'
    
    result = analyze_stock(stock_code, stock_name)
    
    if result:
        print()
        print(f'Analysis Complete!')
        print(f'Score: {result["total_score"]:.1f}')
        print(f'Signal: {result["signal"]}')
        print(f'Data Source: {result["data_source"]}')
