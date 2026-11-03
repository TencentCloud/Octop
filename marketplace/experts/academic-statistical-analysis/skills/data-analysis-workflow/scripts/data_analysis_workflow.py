#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Analysis Workflow - 标准化数据分析工作流
"""

import os
import sys
import io
import pandas as pd
from datetime import datetime

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

WORKFLOW_STAGES = [
    {'name': '数据导入与检查', 'duration': '5-10 分钟'},
    {'name': '数据清洗与预处理', 'duration': '15-30 分钟'},
    {'name': '描述统计与探索', 'duration': '20-40 分钟'},
    {'name': '推断统计分析', 'duration': '30-60 分钟'},
    {'name': '可视化呈现', 'duration': '20-40 分钟'},
    {'name': '结果报告', 'duration': '15-30 分钟'}
]

ANALYSIS_TYPES = {
    'experimental': {
        'description': '实验数据分析',
        'tests': ['t-test', 'ANOVA', 'chi-square'],
        'visualizations': ['boxplot', 'violin', 'bar']
    },
    'survey': {
        'description': '调查数据分析',
        'tests': ['correlation', 'regression', 'factor-analysis'],
        'visualizations': ['heatmap', 'scatter', 'histogram']
    },
    'exploratory': {
        'description': '探索性数据分析',
        'tests': ['descriptive', 'correlation'],
        'visualizations': ['pairplot', 'distribution', 'correlation-matrix']
    }
}

def print_stage(stage_num, stage_info):
    """打印阶段信息"""
    print(f"\n阶段 {stage_num}: {stage_info['name']} ({stage_info['duration']})")

def load_data(file_path):
    """加载数据"""
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    elif file_path.endswith('.xlsx'):
        df = pd.read_excel(file_path)
    elif file_path.endswith('.sav'):
        df = pd.read_spss(file_path)
    else:
        raise ValueError(f"不支持的文件格式：{file_path}")
    
    return df

def check_data(df):
    """数据检查"""
    print("\n" + "="*60)
    print("数据检查报告")
    print("="*60)
    
    print(f"\n数据维度：{df.shape[0]} 行 × {df.shape[1]} 列")
    
    print(f"\n变量类型:")
    print(df.dtypes)
    
    print(f"\n缺失值统计:")
    missing = df.isnull().sum()
    missing_percent = (df.isnull().sum() / len(df) * 100).round(2)
    missing_report = pd.DataFrame({'缺失数': missing, '缺失百分比': missing_percent})
    print(missing_report[missing_report['缺失数'] > 0])
    
    print(f"\n描述统计:")
    print(df.describe())
    
    print("="*60)

def data_analysis_workflow(file_path, analysis_type='experimental', stage=None):
    """数据分析工作流"""
    print(f"📊 开始数据分析：{file_path}")
    print(f"分析类型：{analysis_type}")
    print(f"分析类型描述：{ANALYSIS_TYPES.get(analysis_type, {}).get('description', 'Unknown')}")
    
    # 显示 6 个阶段
    print("\n" + "="*60)
    print("数据分析工作流 - 6 个阶段")
    print("="*60)
    for i, stage in enumerate(WORKFLOW_STAGES, 1):
        print_stage(i, stage)
    
    # 总时间估算
    total_time = "2-4 小时"
    print(f"\n预计总时间：{total_time}")
    print("="*60)
    
    # 加载数据
    print("\n阶段 1: 加载数据...")
    try:
        df = load_data(file_path)
        print(f"✅ 数据加载成功：{df.shape[0]} 行 × {df.shape[1]} 列")
        
        # 数据检查
        check_data(df)
        
    except Exception as e:
        print(f"❌ 数据加载失败：{e}")
        return None
    
    if stage:
        print(f"\n执行阶段 {stage}: {WORKFLOW_STAGES[stage-1]['name']}")
    else:
        print("\n建议执行步骤：")
        print("1. 阶段 1-2: 使用 data-analysis 进行数据清洗")
        print("2. 阶段 3: 使用 seaborn 进行探索性分析")
        print("3. 阶段 4: 使用 statistical-analysis 进行统计检验")
        print("4. 阶段 5: 使用 scientific-visualization 生成出版级图表")
        print("5. 阶段 6: 使用 statistical-analysis 生成 APA 格式报告")
    
    return df

if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else "data.csv"
    analysis_type = sys.argv[2] if len(sys.argv) > 2 else "experimental"
    stage = int(sys.argv[3]) if len(sys.argv) > 3 else None
    
    data_analysis_workflow(file_path, analysis_type, stage)
