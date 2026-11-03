#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PPT讲师备注自动更新工具
从教案中提取讲师活动，自动写入对应PPT幻灯片备注
"""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# 尝试导入pptx库
try:
    from pptx import Presentation
    from pptx.util import Pt
except ImportError:
    print("正在安装 python-pptx 库...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-pptx", "-q"])
    from pptx import Presentation
    from pptx.util import Pt

# 课程目录
COURSE_DIR = r"G:\own\备教\2026上半年腾讯合作人工智能课"


def extract_text_from_docx(docx_path):
    """从docx文件中提取所有文本内容"""
    try:
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(docx_path, 'r') as z:
            with z.open('word/document.xml') as f:
                content = f.read()
        
        root = ET.fromstring(content)
        texts = []
        for t in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
            if t.text:
                texts.append(t.text)
        return ''.join(texts)
    except Exception as e:
        print(f"读取教案出错: {e}")
        return ""


def extract_lecture_activities(full_text):
    """从教案文本中提取讲师活动"""
    activities = {}
    
    # 简单按教学阶段划分（这里需要根据实际教案结构调整）
    # 实际上这个函数需要更复杂的逻辑来匹配PPT
    
    # 简化版：返回空字典，后续用内置的映射
    return activities


def find_course_files(course_dir):
    """查找课程文件夹中的教案和课件"""
    courses = []
    
    if not os.path.exists(course_dir):
        print(f"目录不存在: {course_dir}")
        return courses
    
    for item in os.listdir(course_dir):
        item_path = os.path.join(course_dir, item)
        if os.path.isdir(item_path):
           教案 = None
            课件 = None
            
            for f in os.listdir(item_path):
                if f.endswith('-教案.docx') or f.endswith('教案.docx'):
                    教案 = os.path.join(item_path, f)
                if f.endswith('-课件.pptx') or f.endswith('课件.pptx'):
                    课件 = os.path.join(item_path, f)
            
            if 教案 and 课件:
                courses.append({
                    'name': item,
                    '教案': 教案,
                    '课件': 课件
                })
    
    return courses


def get_latest_pptx(course_dir):
    """获取最新更新的PPT文件"""
    latest_file = None
    latest_time = 0
    
    for root, dirs, files in os.walk(course_dir):
        for f in files:
            if f.endswith('.pptx'):
                fpath = os.path.join(root, f)
                mtime = os.path.getmtime(fpath)
                if mtime > latest_time:
                    latest_time = mtime
                    latest_file = fpath
    
    return latest_file


def update_ppt_notes(pptx_path, output_path=None):
    """更新PPT的讲师备注（使用通用模板）"""
    if output_path is None:
        name, ext = os.path.splitext(pptx_path)
        output_path = f"{name}-更新{ext}"
    
    prs = Presentation(pptx_path)
    slide_count = len(prs.slides)
    
    print(f"PPT共有 {slide_count} 张幻灯片")
    
    # 这里可以添加从教案提取的逻辑
    # 目前先保存
    
    prs.save(output_path)
    print(f"已保存到: {output_path}")
    return output_path


def main():
    """主函数"""
    print("=" * 50)
    print("PPT讲师备注自动更新工具")
    print("=" * 50)
    
    # 查找课程
    courses = find_course_files(COURSE_DIR)
    
    if not courses:
        print("未找到任何课程文件")
        return
    
    print(f"\n找到 {len(courses)} 个课程:")
    for i, c in enumerate(courses, 1):
        print(f"  {i}. {c['name']}")
    
    # 获取最新的PPT
    latest_ppt = get_latest_pptx(COURSE_DIR)
    if latest_ppt:
        print(f"\n最新更新的PPT: {latest_ppt}")
    
    print("\n请在PowerPoint中通过 视图 -> 演讲者备注 查看内容")


if __name__ == "__main__":
    main()
