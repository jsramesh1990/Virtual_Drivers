#!/usr/bin/env python3
"""
performance-analyzer.py - Performance Analysis Tool for Virtual Devices

This tool analyzes performance data from virtual devices and provides
detailed reports, visualizations, and recommendations for optimization.

Version: 1.0.0
Author: Intel NUC Virtual Device Platform Team
License: GPL v2
"""

import os
import sys
import json
import time
import math
import statistics
import argparse
import logging
import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Colors for output
COLORS = {
    'RESET': '\033[0m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m',
    'WHITE': '\033[37m',
    'BOLD': '\033[1m'
}

# ==================== Data Classes ====================

@dataclass
class PerformanceThresholds:
    """Performance thresholds"""
    cpu_min: float = 0.0
    cpu_max: float = 80.0
    memory_min: float = 0.0
    memory_max: float = 80.0
    disk_min: float = 0.0
    disk_max: float = 80.0
    network_min: float = 0.0
    network_max: float = 80.0
    latency_min: float = 0.0
    latency_max: float = 100.0

@dataclass
class PerformanceMetric:
    """Performance metric analysis"""
    name: str
    value: float
    unit: str
    min: float
    max: float
    avg: float
    std: float
    p50: float
    p95: float
    p99: float
    samples: int

@dataclass
class PerformanceReport:
    """Performance analysis report"""
    timestamp: str
    device: str
    type: str
    duration: float
    metrics: Dict[str, PerformanceMetric]
    issues: List[str]
    recommendations: List[str]

# ==================== Performance Analyzer ====================

class PerformanceAnalyzer:
    """Analyze performance data"""
    
    def __init__(self, thresholds: PerformanceThresholds = None):
        self.thresholds = thresholds or PerformanceThresholds()
        self.data: Dict[str, List[float]] = defaultdict(list)
        self.reports: List[PerformanceReport] = []
    
    def load_data(self, data: Dict):
        """Load performance data from dict"""
        if 'system' in data:
            for metric in data['system']:
                self.data['cpu'].append(metric.get('cpu_percent', 0))
                self.data['memory'].append(metric.get('memory_percent', 0))
                self.data['disk'].append(metric.get('disk_usage', 0))
                self.data['temperature'].append(metric.get('temperature', 0))
        
        if 'devices' in data:
            for name, device in data['devices'].items():
                if 'metrics' in device:
                    for metric_name, values in device['metrics'].items():
                        key = f"{name}_{metric_name}"
                        self.data[key] = [v[1] for v in values if len(v) > 1]
    
    def analyze(self) -> List[PerformanceReport]:
        """Analyze loaded data"""
        reports = []
        
        # Analyze system metrics
        system_report = self._analyze_system()
        if system_report:
            reports.append(system_report)
        
        # Analyze device metrics
        device_reports = self._analyze_devices()
        reports.extend(device_reports)
        
        self.reports = reports
        return reports
    
    def _analyze_system(self) -> Optional[PerformanceReport]:
        """Analyze system metrics"""
        metrics = {}
        issues = []
        recommendations = []
        
        # CPU analysis
        if self.data.get('cpu'):
            cpu_data = self.data['cpu']
            cpu_metric = self._analyze_metric(
                'CPU Usage', cpu_data, '%',
                self.thresholds.cpu_min, self.thresholds.cpu_max
            )
            metrics['cpu'] = cpu_metric
            
            if cpu_metric.avg > self.thresholds.cpu_max:
                issues.append(f"High CPU usage: {cpu_metric.avg:.1f}%")
                recommendations.append(
                    "Consider reducing load or upgrading CPU"
                )
            elif cpu_metric.p95 > self.thresholds.cpu_max:
                issues.append(f"CPU spikes detected: {cpu_metric.p95:.1f}%")
                recommendations.append(
                    "Investigate processes causing CPU spikes"
                )
        
        # Memory analysis
        if self.data.get('memory'):
            mem_data = self.data['memory']
            mem_metric = self._analyze_metric(
                'Memory Usage', mem_data, '%',
                self.thresholds.memory_min, self.thresholds.memory_max
            )
            metrics['memory'] = mem_metric
            
            if mem_metric.avg > self.thresholds.memory_max:
                issues.append(f"High memory usage: {mem_metric.avg:.1f}%")
                recommendations.append(
                    "Consider increasing RAM or reducing memory usage"
                )
        
        # Disk analysis
        if self.data.get('disk'):
            disk_data = self.data['disk']
            disk_metric = self._analyze_metric(
                'Disk Usage', disk_data, '%',
                self.thresholds.disk_min, self.thresholds.disk_max
            )
            metrics['disk'] = disk_metric
            
            if disk_metric.avg > self.thresholds.disk_max:
                issues.append(f"High disk usage: {disk_metric.avg:.1f}%")
                recommendations.append(
                    "Consider cleaning up disk or adding more storage"
                )
        
        # Temperature analysis
        if self.data.get('temperature'):
            temp_data = [t for t in self.data['temperature'] if t > 0]
            if temp_data:
                temp_metric = self._analyze_metric(
                    'Temperature', temp_data, '°C',
                    0, 80
                )
                metrics['temperature'] = temp_metric
                
                if temp_metric.avg > 70:
                    issues.append(f"High temperature: {temp_metric.avg:.1f}°C")
                    recommendations.append(
                        "Check cooling system and airflow"
                    )
        
        if metrics:
            return PerformanceReport(
                timestamp=datetime.datetime.now().isoformat(),
                device='system',
                type='system',
                duration=len(self.data.get('cpu', [])) or 0,
                metrics=metrics,
                issues=issues,
                recommendations=recommendations
            )
        
        return None
    
    def _analyze_devices(self) -> List[PerformanceReport]:
        """Analyze device metrics"""
        reports = []
        
        for key, data in self.data.items():
            if '_' in key and not key.startswith('system_'):
                parts = key.split('_')
                if len(parts) >= 2:
                    device = parts[0]
                    metric = '_'.join(parts[1:])
                    
                    if len(data) > 10:  # Need enough samples
                        metric_analysis = self._analyze_metric(
                            metric, data, 'units',
                            0, None
                        )
                        
                        # Create device report
                        report = PerformanceReport(
                            timestamp=datetime.datetime.now().isoformat(),
                            device=device,
                            type='device',
                            duration=len(data),
                            metrics={metric: metric_analysis},
                            issues=[],
                            recommendations=[]
                        )
                        reports.append(report)
        
        return reports
    
    def _analyze_metric(self, name: str, data: List[float], unit: str,
                       min_val: float = None, max_val: float = None) -> PerformanceMetric:
        """Analyze a single metric"""
        if not data:
            return PerformanceMetric(name, 0, unit, 0, 0, 0, 0, 0, 0, 0, 0)
        
        sorted_data = sorted(data)
        n = len(sorted_data)
        
        metric = PerformanceMetric(
            name=name,
            value=sorted_data[-1] if sorted_data else 0,
            unit=unit,
            min=sorted_data[0] if sorted_data else 0,
            max=sorted_data[-1] if sorted_data else 0,
            avg=statistics.mean(data) if data else 0,
            std=statistics.stdev(data) if len(data) > 1 else 0,
            p50=sorted_data[int(n * 0.5)] if n > 0 else 0,
            p95=sorted_data[int(n * 0.95)] if n > 0 else 0,
            p99=sorted_data[int(n * 0.99)] if n > 0 else 0,
            samples=n
        )
        
        return metric
    
    def generate_report(self, output_format: str = 'text') -> str:
        """Generate analysis report"""
        if not self.reports:
            return "No data analyzed"
        
        if output_format == 'text':
            return self._generate_text_report()
        elif output_format == 'json':
            return self._generate_json_report()
        elif output_format == 'html':
            return self._generate_html_report()
        else:
            return f"Unsupported format: {output_format}"
    
    def _generate_text_report(self) -> str:
        """Generate text report"""
        lines = []
        
        lines.append("=" * 80)
        lines.append("PERFORMANCE ANALYSIS REPORT")
        lines.append("=" * 80)
        lines.append(f"Generated: {datetime.datetime.now().isoformat()}")
        lines.append("")
        
        for report in self.reports:
            lines.append(f"{COLORS['CYAN']}=== {report.device} ({report.type}) ==={COLORS['RESET']}")
            lines.append(f"Duration: {report.duration} samples")
            lines.append("")
            
            for name, metric in report.metrics.items():
                lines.append(f"  {COLORS['YELLOW']}{name}{COLORS['RESET']}:")
                lines.append(f"    Current: {metric.value:.2f} {metric.unit}")
                lines.append(f"    Min:     {metric.min:.2f} {metric.unit}")
                lines.append(f"    Max:     {metric.max:.2f} {metric.unit}")
                lines.append(f"    Avg:     {metric.avg:.2f} {metric.unit}")
                lines.append(f"    Std:     {metric.std:.2f} {metric.unit}")
                lines.append(f"    P50:     {metric.p50:.2f} {metric.unit}")
                lines.append(f"    P95:     {metric.p95:.2f} {metric.unit}")
                lines.append(f"    P99:     {metric.p99:.2f} {metric.unit}")
                lines.append(f"    Samples: {metric.samples}")
                lines.append("")
            
            if report.issues:
                lines.append(f"  {COLORS['RED']}Issues:{COLORS['RESET']}")
                for issue in report.issues:
                    lines.append(f"    ⚠ {issue}")
                lines.append("")
            
            if report.recommendations:
                lines.append(f"  {COLORS['GREEN']}Recommendations:{COLORS['RESET']}")
                for rec in report.recommendations:
                    lines.append(f"    → {rec}")
                lines.append("")
        
        # Summary
        lines.append("=" * 80)
        lines.append("SUMMARY")
        lines.append("=" * 80)
        
        total_issues = sum(len(r.issues) for r in self.reports)
        total_recs = sum(len(r.recommendations) for r in self.reports)
        
        lines.append(f"Total Issues: {total_issues}")
        lines.append(f"Total Recommendations: {total_recs}")
        
        if total_issues > 0:
            lines.append(f"{COLORS['YELLOW']}⚠ System may need optimization{COLORS['RESET']}")
        else:
            lines.append(f"{COLORS['GREEN']}✓ System performance is healthy{COLORS['RESET']}")
        
        return "\n".join(lines)
    
    def _generate_json_report(self) -> str:
        """Generate JSON report"""
        report_data = {
            'timestamp': datetime.datetime.now().isoformat(),
            'reports': []
        }
        
        for report in self.reports:
            report_dict = {
                'device': report.device,
                'type': report.type,
                'duration': report.duration,
                'metrics': {},
                'issues': report.issues,
                'recommendations': report.recommendations
            }
            
            for name, metric in report.metrics.items():
                report_dict['metrics'][name] = {
                    'value': metric.value,
                    'unit': metric.unit,
                    'min': metric.min,
                    'max': metric.max,
                    'avg': metric.avg,
                    'std': metric.std,
                    'p50': metric.p50,
                    'p95': metric.p95,
                    'p99': metric.p99,
                    'samples': metric.samples
                }
            
            report_data['reports'].append(report_dict)
        
        return json.dumps(report_data, indent=2)
    
    def _generate_html_report(self) -> str:
        """Generate HTML report"""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Performance Analysis Report</title>
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: #1a1a2e;
                    color: #eee;
                    padding: 20px;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                }
                .header {
                    background: linear-gradient(135deg, #16213e, #0f3460);
                    padding: 20px;
                    border-radius: 10px;
                    margin-bottom: 20px;
                }
                .header h1 {
                    color: #e94560;
                    margin: 0;
                }
                .report {
                    background: #16213e;
                    border-radius: 10px;
                    padding: 20px;
                    margin-bottom: 20px;
                }
                .report h2 {
                    color: #e94560;
                    border-bottom: 1px solid #2a3a5e;
                    padding-bottom: 10px;
                }
                .metric-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 10px;
                    margin: 15px 0;
                }
                .metric-item {
                    background: #1a2a4e;
                    padding: 10px;
                    border-radius: 5px;
                }
                .metric-item .label {
                    color: #8899aa;
                    font-size: 12px;
                }
                .metric-item .value {
                    font-size: 20px;
                    font-weight: 300;
                }
                .metric-item .unit {
                    color: #8899aa;
                    font-size: 14px;
                }
                .issue {
                    color: #ff6b6b;
                    padding: 5px 10px;
                    background: #2a1a1a;
                    border-radius: 3px;
                    margin: 5px 0;
                }
                .recommendation {
                    color: #51cf66;
                    padding: 5px 10px;
                    background: #1a2a1a;
                    border-radius: 3px;
                    margin: 5px 0;
                }
                .summary {
                    background: #16213e;
                    border-radius: 10px;
                    padding: 20px;
                    text-align: center;
                }
                .healthy {
                    color: #51cf66;
                }
                .warning {
                    color: #ffd43b;
                }
                .status-badge {
                    display: inline-block;
                    padding: 5px 15px;
                    border-radius: 20px;
                    font-size: 14px;
                }
                .status-healthy {
                    background: #1a3a1a;
                    color: #51cf66;
                }
                .status-warning {
                    background: #3a3a1a;
                    color: #ffd43b;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Performance Analysis Report</h1>
                    <p>Generated: """ + datetime.datetime.now().isoformat() + """</p>
                </div>
        """
        
        for report in self.reports:
            html += f"""
                <div class="report">
                    <h2>{report.device} ({report.type})</h2>
                    <p>Samples: {report.duration}</p>
                    <div class="metric-grid">
            """
            
            for name, metric in report.metrics.items():
                html += f"""
                        <div class="metric-item">
                            <div class="label">{name}</div>
                            <div class="value">{metric.value:.1f} <span class="unit">{metric.unit}</span></div>
                            <div style="font-size:12px;color:#8899aa;">
                                Min: {metric.min:.1f} | Max: {metric.max:.1f} | Avg: {metric.avg:.1f}
                            </div>
                            <div style="font-size:12px;color:#8899aa;">
                                P50: {metric.p50:.1f} | P95: {metric.p95:.1f} | P99: {metric.p99:.1f}
                            </div>
                        </div>
                """
            
            html += """
                    </div>
            """
            
            if report.issues:
                html += '<h3>⚠ Issues</h3>'
                for issue in report.issues:
                    html += f'<div class="issue">⚠ {issue}</div>'
            
            if report.recommendations:
                html += '<h3>💡 Recommendations</h3>'
                for rec in report.recommendations:
                    html += f'<div class="recommendation">→ {rec}</div>'
            
            html += '</div>'
        
        # Summary
        total_issues = sum(len(r.issues) for r in self.reports)
        total_recs = sum(len(r.recommendations) for r in self.reports)
        
        status = "healthy" if total_issues == 0 else "warning"
        status_text = "System performance is healthy" if total_issues == 0 else "System may need optimization"
        
        html += f"""
                <div class="summary">
                    <h2>Summary</h2>
                    <p>Total Issues: {total_issues}</p>
                    <p>Total Recommendations: {total_recs}</p>
                    <div class="status-badge status-{status}">{status_text}</div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html

# ==================== Command Line Interface ====================

class PerformanceCLI:
    """Command line interface for performance analyzer"""
    
    def __init__(self):
        self.analyzer = PerformanceAnalyzer()
    
    def run(self, args):
        """Run performance analysis"""
        if args.command == 'analyze':
            self._analyze(args)
        elif args.command == 'report':
            self._generate_report(args)
        elif args.command == 'threshold':
            self._set_thresholds(args)
        else:
            print(f"Unknown command: {args.command}")
    
    def _analyze(self, args):
        """Analyze performance data"""
        # Load data
        if args.input:
            with open(args.input, 'r') as f:
                data = json.load(f)
            self.analyzer.load_data(data)
            logger.info(f"Loaded data from {args.input}")
        
        # Analyze
        reports = self.analyzer.analyze()
        
        # Generate report
        report = self.analyzer.generate_report(args.format)
        
        # Output
        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            logger.info(f"Report saved to {args.output}")
        else:
            print(report)
    
    def _generate_report(self, args):
        """Generate report from existing analysis"""
        report = self.analyzer.generate_report(args.format)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            logger.info(f"Report saved to {args.output}")
        else:
            print(report)
    
    def _set_thresholds(self, args):
        """Set performance thresholds"""
        thresholds = PerformanceThresholds(
            cpu_max=args.cpu_max or 80,
            memory_max=args.memory_max or 80,
            disk_max=args.disk_max or 80
        )
        self.analyzer.thresholds = thresholds
        logger.info("Thresholds updated")

def create_parser():
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description="Performance Analysis Tool for Virtual Devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze performance data
  performance-analyzer.py analyze -i data.json

  # Generate text report
  performance-analyzer.py analyze -i data.json -o report.txt

  # Generate HTML report
  performance-analyzer.py analyze -i data.json --format html -o report.html

  # Set custom thresholds
  performance-analyzer.py threshold --cpu-max 70 --memory-max 75
        """
    )
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze performance data')
    analyze_parser.add_argument('-i', '--input', required=True,
                               help='Input JSON data file')
    analyze_parser.add_argument('-o', '--output',
                               help='Output report file')
    analyze_parser.add_argument('--format', default='text',
                               choices=['text', 'json', 'html'],
                               help='Output format (default: text)')
    
    # Report command
    report_parser = subparsers.add_parser('report', help='Generate report from analysis')
    report_parser.add_argument('--format', default='text',
                              choices=['text', 'json', 'html'],
                              help='Output format (default: text)')
    report_parser.add_argument('-o', '--output',
                              help='Output report file')
    
    # Threshold command
    threshold_parser = subparsers.add_parser('threshold', help='Set performance thresholds')
    threshold_parser.add_argument('--cpu-max', type=float,
                                 help='Maximum CPU usage (%)')
    threshold_parser.add_argument('--memory-max', type=float,
                                 help='Maximum memory usage (%)')
    threshold_parser.add_argument('--disk-max', type=float,
                                 help='Maximum disk usage (%)')
    
    return parser

def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if not args.command:
        parser.print_help()
        return
    
    cli = PerformanceCLI()
    try:
        cli.run(args)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
