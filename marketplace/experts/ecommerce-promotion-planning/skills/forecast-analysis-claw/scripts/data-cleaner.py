#!/usr/bin/env python3
"""
data-cleaner.py - 销售数据清洗脚本

功能:
  clean          - 清洗原始销售数据（去重、填补缺失、格式统一）
  detect-outliers - 检测异常值（促销峰值、录入错误等）

依赖: pandas, numpy

用法:
  python3 data-cleaner.py clean --input raw_sales.csv --output clean_sales.csv
  python3 data-cleaner.py detect-outliers --input sales.csv
"""

import argparse
import sys
from pathlib import Path

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: pandas and numpy are required. Run: pip install pandas numpy")
    sys.exit(1)


def load_data(filepath: str) -> pd.DataFrame:
    path = Path(filepath)
    if path.suffix in ['.xlsx', '.xls']:
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath)

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
    return df


def cmd_clean(args):
    df = load_data(args.input)
    original_rows = len(df)

    # 1. 解析日期
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    invalid_dates = df['date'].isna().sum()
    df = df.dropna(subset=['date'])

    # 2. 数值清洗
    df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0)
    df['quantity'] = df['quantity'].clip(lower=0)  # 去除负值

    # 3. 去重（同一天同一SKU保留最大值）
    df = df.sort_values('quantity', ascending=False).drop_duplicates(subset=['date', 'sku'], keep='first')

    # 4. 填补缺失日期（每个SKU的日期序列补0）
    if args.fill_missing:
        filled_rows = 0
        all_dates = pd.date_range(df['date'].min(), df['date'].max(), freq='D')
        filled_dfs = []
        for sku, group in df.groupby('sku'):
            group = group.set_index('date').reindex(all_dates, fill_value=0).reset_index()
            group.columns = ['date', 'quantity']
            group['sku'] = sku
            filled_dfs.append(group)
            filled_rows += len(all_dates) - len(group)
        df = pd.concat(filled_dfs, ignore_index=True)

    # 5. 排序
    df = df.sort_values(['sku', 'date']).reset_index(drop=True)

    output_path = args.output or 'clean_sales.csv'
    df.to_csv(output_path, index=False, encoding='utf-8-sig')

    print(f"✅ 数据清洗完成")
    print(f"   原始行数:     {original_rows}")
    print(f"   无效日期行:   {invalid_dates}")
    print(f"   清洗后行数:   {len(df)}")
    print(f"   SKU 数量:     {df['sku'].nunique()}")
    print(f"   日期范围:     {df['date'].min().date()} ~ {df['date'].max().date()}")
    print(f"   输出文件:     {output_path}")


def cmd_detect_outliers(args):
    df = load_data(args.input)
    df['date'] = pd.to_datetime(df['date'])
    df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0)

    outliers = []
    for sku, group in df.groupby('sku'):
        q = group['quantity']
        mean = q.mean()
        std = q.std()
        threshold = args.threshold  # 默认 3 倍标准差

        anomalies = group[np.abs(q - mean) > threshold * std]
        for _, row in anomalies.iterrows():
            outliers.append({
                'sku': sku,
                'date': row['date'].date(),
                'quantity': row['quantity'],
                'mean': round(mean, 1),
                'deviation': round((row['quantity'] - mean) / std, 1),
                'suggestion': '促销峰值（标注后保留）' if row['quantity'] > mean else '疑似录入错误（建议核查）'
            })

    if outliers:
        out_df = pd.DataFrame(outliers)
        print(f"\n⚠️  检测到 {len(outliers)} 个异常值：\n")
        print(out_df.to_string(index=False))
        if args.output:
            out_df.to_csv(args.output, index=False, encoding='utf-8-sig')
            print(f"\n结果已保存到: {args.output}")
    else:
        print("✅ 未检测到明显异常值")


def main():
    parser = argparse.ArgumentParser(description='销售数据清洗工具')
    sub = parser.add_subparsers(dest='command')

    p_clean = sub.add_parser('clean', help='清洗原始销售数据')
    p_clean.add_argument('--input', required=True)
    p_clean.add_argument('--output', default='clean_sales.csv')
    p_clean.add_argument('--fill-missing', action='store_true', help='填补缺失日期（补0）')

    p_outlier = sub.add_parser('detect-outliers', help='检测异常值')
    p_outlier.add_argument('--input', required=True)
    p_outlier.add_argument('--output', help='输出异常值报告 CSV')
    p_outlier.add_argument('--threshold', type=float, default=3.0, help='标准差倍数阈值（默认3）')

    args = parser.parse_args()
    if args.command == 'clean':
        cmd_clean(args)
    elif args.command == 'detect-outliers':
        cmd_detect_outliers(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
