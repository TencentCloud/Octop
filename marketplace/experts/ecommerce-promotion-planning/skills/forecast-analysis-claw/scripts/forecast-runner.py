#!/usr/bin/env python3
"""
forecast-runner.py - 销量预测核心脚本
支持单SKU预测、批量预测、准确率评估、报告生成

依赖: pandas, numpy, scikit-learn
可选: prophet (pip install prophet)

用法:
  python3 forecast-runner.py single --sku SKU-001 --input sales.csv --days 30
  python3 forecast-runner.py batch --input sales.csv --output forecast_result.csv --days 30
  python3 forecast-runner.py evaluate --input sales.csv --actual actual.csv
  python3 forecast-runner.py report --forecast forecast_result.csv --inventory inventory.csv
"""

import argparse
import sys
import json
from pathlib import Path

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: pandas and numpy are required. Run: pip install pandas numpy")
    sys.exit(1)


# ─── 预测模型 ───────────────────────────────────────────────────────────────

def moving_average(series: pd.Series, window: int = 14) -> float:
    """移动平均法"""
    if len(series) < window:
        window = len(series)
    return series.tail(window).mean()


def exponential_smoothing(series: pd.Series, alpha: float = 0.3) -> float:
    """指数平滑法"""
    result = series.iloc[0]
    for val in series.iloc[1:]:
        result = alpha * val + (1 - alpha) * result
    return result


def holt_winters_forecast(series: pd.Series, forecast_days: int, season_period: int = 7):
    """Holt-Winters 季节性预测（简化版）"""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(
            series, trend='add', seasonal='add', seasonal_periods=season_period
        ).fit(optimized=True)
        forecast = model.forecast(forecast_days)
        return forecast.clip(lower=0)
    except ImportError:
        # fallback to simple moving average
        avg = moving_average(series)
        return pd.Series([avg] * forecast_days)


def prophet_forecast(series: pd.Series, forecast_days: int, holidays_df=None):
    """Prophet 预测（需要 prophet 包）"""
    try:
        from prophet import Prophet
        df = pd.DataFrame({
            'ds': series.index,
            'y': series.values
        })
        m = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
        if holidays_df is not None:
            m.add_country_holidays(country_name='CN')
        m.fit(df)
        future = m.make_future_dataframe(periods=forecast_days)
        forecast = m.predict(future)
        return forecast.tail(forecast_days)[['ds', 'yhat', 'yhat_lower', 'yhat_upper']]
    except ImportError:
        raise ImportError("Prophet not installed. Run: pip install prophet")


def auto_select_model(series: pd.Series) -> str:
    """根据数据特征自动选择预测模型"""
    n = len(series)
    if n < 30:
        return 'moving_average'

    # 检测季节性（简单方法：周内变异系数）
    if n >= 14:
        weekly_cv = series.groupby(series.index.dayofweek).mean().std() / series.mean()
        if weekly_cv > 0.2:
            return 'holt_winters'

    # 检测趋势
    x = np.arange(n)
    slope = np.polyfit(x, series.values, 1)[0]
    trend_ratio = abs(slope * n) / series.mean()
    if trend_ratio > 0.3:
        return 'exponential_smoothing'

    return 'moving_average'


# ─── 预测执行 ───────────────────────────────────────────────────────────────

def forecast_sku(sku_data: pd.Series, forecast_days: int, model: str = 'auto') -> dict:
    """对单个 SKU 执行预测，返回预测结果字典"""
    if model == 'auto':
        model = auto_select_model(sku_data)

    if model == 'moving_average':
        daily_forecast = moving_average(sku_data)
        total = daily_forecast * forecast_days
        lower = total * 0.8
        upper = total * 1.2
    elif model == 'exponential_smoothing':
        daily_forecast = exponential_smoothing(sku_data)
        total = daily_forecast * forecast_days
        lower = total * 0.75
        upper = total * 1.25
    elif model == 'holt_winters':
        forecast_series = holt_winters_forecast(sku_data, forecast_days)
        total = forecast_series.sum()
        daily_forecast = total / forecast_days
        lower = total * 0.75
        upper = total * 1.25
    else:
        daily_forecast = moving_average(sku_data)
        total = daily_forecast * forecast_days
        lower = total * 0.8
        upper = total * 1.2

    return {
        'model_used': model,
        'daily_avg_forecast': round(daily_forecast, 1),
        'total_forecast': round(total, 0),
        'lower_bound': round(lower, 0),
        'upper_bound': round(upper, 0),
        'forecast_days': forecast_days,
    }


def calculate_replenishment(forecast: dict, current_stock: float,
                             in_transit: float, lead_time_days: int,
                             safety_days: int) -> dict:
    """计算补货建议"""
    daily_avg = forecast['daily_avg_forecast']
    reorder_point = daily_avg * (lead_time_days + safety_days)
    available_stock = current_stock + in_transit
    days_of_stock = available_stock / daily_avg if daily_avg > 0 else 999

    if days_of_stock < 3:
        priority = '🔴 紧急'
    elif available_stock < reorder_point:
        priority = '🟡 正常'
    else:
        priority = '🟢 可延后'

    replenishment_qty = max(0, forecast['total_forecast'] + reorder_point - available_stock)

    return {
        'reorder_point': round(reorder_point, 0),
        'available_stock': available_stock,
        'days_of_stock': round(days_of_stock, 1),
        'replenishment_qty': round(replenishment_qty, 0),
        'priority': priority,
    }


# ─── 数据加载 ───────────────────────────────────────────────────────────────

def load_sales_data(filepath: str) -> pd.DataFrame:
    """加载销售数据 CSV/Excel，期望列：date, sku, quantity"""
    path = Path(filepath)
    if path.suffix in ['.xlsx', '.xls']:
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath)

    # 标准化列名（兼容中英文）
    col_map = {}
    for col in df.columns:
        lower = col.lower().strip()
        if lower in ['date', '日期', '销售日期']:
            col_map[col] = 'date'
        elif lower in ['sku', 'sku编码', '商品编码', 'item_id']:
            col_map[col] = 'sku'
        elif lower in ['quantity', 'qty', '销量', '数量', '销售量']:
            col_map[col] = 'quantity'
    df = df.rename(columns=col_map)

    required = ['date', 'sku', 'quantity']
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"ERROR: Missing required columns: {missing}")
        print(f"Available columns: {list(df.columns)}")
        sys.exit(1)

    df['date'] = pd.to_datetime(df['date'])
    df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0)
    return df


# ─── 子命令 ─────────────────────────────────────────────────────────────────

def cmd_single(args):
    df = load_sales_data(args.input)
    sku_df = df[df['sku'] == args.sku].set_index('date').sort_index()
    if sku_df.empty:
        print(f"ERROR: SKU '{args.sku}' not found in data")
        sys.exit(1)

    series = sku_df['quantity']
    result = forecast_sku(series, args.days)

    print(f"\n{'='*50}")
    print(f"SKU: {args.sku}  |  预测周期: {args.days}天")
    print(f"{'='*50}")
    print(f"使用模型:     {result['model_used']}")
    print(f"日均预测销量: {result['daily_avg_forecast']} 件/天")
    print(f"预测总销量:   {result['total_forecast']} 件")
    print(f"置信区间:     [{result['lower_bound']}, {result['upper_bound']}]")

    if args.stock is not None:
        replen = calculate_replenishment(
            result,
            current_stock=args.stock,
            in_transit=args.in_transit or 0,
            lead_time_days=args.lead_time or 14,
            safety_days=args.safety_days or 7,
        )
        print(f"\n── 补货建议 ──")
        print(f"当前可用库存: {replen['available_stock']} 件 ({replen['days_of_stock']} 天)")
        print(f"补货触发点:   {replen['reorder_point']} 件")
        print(f"建议补货量:   {replen['replenishment_qty']} 件")
        print(f"优先级:       {replen['priority']}")
    print()


def cmd_batch(args):
    df = load_sales_data(args.input)
    skus = df['sku'].unique()
    results = []

    for sku in skus:
        sku_df = df[df['sku'] == sku].set_index('date').sort_index()
        series = sku_df['quantity']
        result = forecast_sku(series, args.days)
        results.append({
            'sku': sku,
            **result,
        })

    out_df = pd.DataFrame(results)
    output_path = args.output or 'forecast_result.csv'
    out_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"✅ 批量预测完成，共 {len(results)} 个 SKU，结果已保存到: {output_path}")
    print(out_df[['sku', 'daily_avg_forecast', 'total_forecast', 'model_used']].to_string(index=False))


def cmd_evaluate(args):
    """评估历史预测准确率（对比预测值 vs 实际值）"""
    forecast_df = pd.read_csv(args.forecast)
    actual_df = load_sales_data(args.actual)

    # 简单 MAPE 计算
    merged = forecast_df.merge(
        actual_df.groupby('sku')['quantity'].sum().reset_index().rename(columns={'quantity': 'actual'}),
        on='sku'
    )
    merged['mape'] = abs(merged['total_forecast'] - merged['actual']) / merged['actual'] * 100
    avg_mape = merged['mape'].mean()

    print(f"\n── 预测准确率评估 ──")
    print(f"平均 MAPE: {avg_mape:.1f}%  ({'优秀' if avg_mape < 10 else '良好' if avg_mape < 20 else '需改进'})")
    print(merged[['sku', 'total_forecast', 'actual', 'mape']].to_string(index=False))


def cmd_report(args):
    """生成文字版预测报告"""
    forecast_df = pd.read_csv(args.forecast)

    urgent = forecast_df[forecast_df.get('priority', '') == '🔴 紧急'] if 'priority' in forecast_df.columns else pd.DataFrame()
    normal = forecast_df[forecast_df.get('priority', '') == '🟡 正常'] if 'priority' in forecast_df.columns else pd.DataFrame()

    print(f"\n{'='*60}")
    print(f"  销量预测报告")
    print(f"{'='*60}")
    print(f"预测 SKU 总数: {len(forecast_df)}")
    if not urgent.empty:
        print(f"\n🔴 紧急补货 ({len(urgent)} 个 SKU):")
        for _, row in urgent.iterrows():
            print(f"  - {row['sku']}: 建议补货 {row.get('replenishment_qty', 'N/A')} 件")
    if not normal.empty:
        print(f"\n🟡 正常补货 ({len(normal)} 个 SKU):")
        for _, row in normal.iterrows():
            print(f"  - {row['sku']}: 建议补货 {row.get('replenishment_qty', 'N/A')} 件")
    print(f"\n详细数据见: {args.forecast}")
    print()


# ─── 主入口 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='销量预测工具')
    sub = parser.add_subparsers(dest='command')

    # single
    p_single = sub.add_parser('single', help='单个 SKU 预测')
    p_single.add_argument('--sku', required=True)
    p_single.add_argument('--input', required=True, help='历史销售数据 CSV/Excel')
    p_single.add_argument('--days', type=int, default=30, help='预测天数')
    p_single.add_argument('--stock', type=float, help='当前库存量')
    p_single.add_argument('--in-transit', type=float, default=0, help='在途库存')
    p_single.add_argument('--lead-time', type=int, default=14, help='供应商交货周期（天）')
    p_single.add_argument('--safety-days', type=int, default=7, help='安全库存天数')

    # batch
    p_batch = sub.add_parser('batch', help='批量 SKU 预测')
    p_batch.add_argument('--input', required=True, help='历史销售数据 CSV/Excel')
    p_batch.add_argument('--output', default='forecast_result.csv')
    p_batch.add_argument('--days', type=int, default=30)

    # evaluate
    p_eval = sub.add_parser('evaluate', help='评估预测准确率')
    p_eval.add_argument('--forecast', required=True, help='预测结果 CSV')
    p_eval.add_argument('--actual', required=True, help='实际销售数据 CSV')

    # report
    p_report = sub.add_parser('report', help='生成预测报告')
    p_report.add_argument('--forecast', required=True, help='预测结果 CSV')

    args = parser.parse_args()
    if args.command == 'single':
        cmd_single(args)
    elif args.command == 'batch':
        cmd_batch(args)
    elif args.command == 'evaluate':
        cmd_evaluate(args)
    elif args.command == 'report':
        cmd_report(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
