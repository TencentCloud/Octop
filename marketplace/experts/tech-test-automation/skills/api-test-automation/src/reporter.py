"""Test Reporter Module

Provides test report generation capabilities.
"""

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Template


HTML_REPORT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>API Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        .summary { background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .test-case { margin: 10px 0; padding: 10px; border-left: 4px solid #ccc; }
        .passed { border-left-color: #4caf50; background: #e8f5e9; }
        .failed { border-left-color: #f44336; background: #ffebee; }
        .skipped { border-left-color: #ff9800; background: #fff3e0; }
        .timestamp { color: #666; font-size: 0.9em; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4caf50; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <h1>API Test Report</h1>
    <p class="timestamp">Generated: {{ timestamp }}</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <p>Total Tests: {{ total }}</p>
        <p>Passed: {{ passed }} ({{ pass_rate }}%)</p>
        <p>Failed: {{ failed }}</p>
        <p>Skipped: {{ skipped }}</p>
        <p>Duration: {{ duration }}s</p>
    </div>
    
    <h2>Test Cases</h2>
    <table>
        <tr>
            <th>Name</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Message</th>
        </tr>
        {% for test in tests %}
        <tr class="{{ test.status }}">
            <td>{{ test.name }}</td>
            <td>{{ test.status.upper() }}</td>
            <td>{{ test.duration }}s</td>
            <td>{{ test.message or '' }}</td>
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""


@dataclass
class TestResult:
    """Single test result."""
    name: str
    status: str  # passed, failed, skipped
    duration: float = 0.0
    message: Optional[str] = None
    output: Optional[str] = None


@dataclass
class TestReport:
    """Complete test report."""
    timestamp: datetime
    results: List[TestResult]
    total_duration: float = 0.0
    
    @property
    def total(self) -> int:
        return len(self.results)
    
    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "passed")
    
    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")
    
    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")
    
    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100


class TestReporter:
    """Test report generator."""
    
    def __init__(self, output_dir: str = "./reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_html_report(self, report: TestReport, filename: Optional[str] = None) -> str:
        """Generate HTML report."""
        if filename is None:
            filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        filepath = self.output_dir / filename
        
        template = Template(HTML_REPORT_TEMPLATE)
        html_content = template.render(
            timestamp=report.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            total=report.total,
            passed=report.passed,
            failed=report.failed,
            skipped=report.skipped,
            pass_rate=f"{report.pass_rate:.1f}",
            duration=f"{report.total_duration:.2f}",
            tests=[
                {
                    "name": r.name,
                    "status": r.status,
                    "duration": f"{r.duration:.3f}",
                    "message": r.message
                }
                for r in report.results
            ]
        )
        
        with open(filepath, "w") as f:
            f.write(html_content)
        
        return str(filepath)
    
    def generate_json_report(self, report: TestReport, filename: Optional[str] = None) -> str:
        """Generate JSON report."""
        if filename is None:
            filename = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.output_dir / filename
        
        data = {
            "timestamp": report.timestamp.isoformat(),
            "summary": {
                "total": report.total,
                "passed": report.passed,
                "failed": report.failed,
                "skipped": report.skipped,
                "pass_rate": report.pass_rate,
                "duration": report.total_duration
            },
            "tests": [
                {
                    "name": r.name,
                    "status": r.status,
                    "duration": r.duration,
                    "message": r.message,
                    "output": r.output
                }
                for r in report.results
            ]
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        return str(filepath)
    
    def generate_junit_xml(self, report: TestReport, filename: Optional[str] = None) -> str:
        """Generate JUnit XML report."""
        if filename is None:
            filename = f"junit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
        
        filepath = self.output_dir / filename
        
        testsuite = ET.Element("testsuite")
        testsuite.set("name", "API Tests")
        testsuite.set("tests", str(report.total))
        testsuite.set("failures", str(report.failed))
        testsuite.set("skipped", str(report.skipped))
        testsuite.set("time", str(report.total_duration))
        testsuite.set("timestamp", report.timestamp.isoformat())
        
        for result in report.results:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", result.name)
            testcase.set("time", str(result.duration))
            
            if result.status == "failed":
                failure = ET.SubElement(testcase, "failure")
                failure.set("message", result.message or "Test failed")
                failure.text = result.output
            elif result.status == "skipped":
                skipped = ET.SubElement(testcase, "skipped")
                skipped.set("message", result.message or "Test skipped")
        
        tree = ET.ElementTree(testsuite)
        tree.write(filepath, encoding="utf-8", xml_declaration=True)
        
        return str(filepath)
    
    def generate_allure_report(self, report: TestReport) -> None:
        """Generate Allure compatible results."""
        allure_dir = self.output_dir / "allure-results"
        allure_dir.mkdir(exist_ok=True)
        
        for result in report.results:
            allure_result = {
                "name": result.name,
                "status": result.status,
                "start": int(report.timestamp.timestamp() * 1000),
                "stop": int((report.timestamp.timestamp() + result.duration) * 1000),
                "uuid": f"{result.name}_{int(report.timestamp.timestamp())}",
                "historyId": result.name,
                "testCaseId": result.name,
                "fullName": result.name,
                "labels": [
                    {"name": "suite", "value": "API Tests"},
                    {"name": "framework", "value": "pytest"}
                ]
            }
            
            if result.status == "failed" and result.message:
                allure_result["statusDetails"] = {
                    "message": result.message,
                    "trace": result.output
                }
            
            filename = f"{allure_result['uuid']}-result.json"
            with open(allure_dir / filename, "w") as f:
                json.dump(allure_result, f, indent=2)


# Import dataclass
from dataclasses import dataclass
