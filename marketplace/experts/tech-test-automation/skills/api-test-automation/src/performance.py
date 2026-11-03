"""Performance Testing Module

Provides load testing and performance measurement tools.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import aiohttp
import httpx


@dataclass
class PerformanceResults:
    """Performance test results."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_time: float = 0.0
    min_response_time: float = float('inf')
    max_response_time: float = 0.0
    avg_response_time: float = 0.0
    response_times: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    @property
    def throughput(self) -> float:
        """Calculate requests per second."""
        if self.total_time > 0:
            return self.total_requests / self.total_time
        return 0.0
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate percentage."""
        if self.total_requests > 0:
            return (self.failed_requests / self.total_requests) * 100
        return 0.0
    
    @property
    def percentiles(self) -> Dict[str, float]:
        """Calculate response time percentiles."""
        if not self.response_times:
            return {}
        sorted_times = sorted(self.response_times)
        n = len(sorted_times)
        return {
            "p50": sorted_times[int(n * 0.5)],
            "p90": sorted_times[int(n * 0.9)],
            "p95": sorted_times[int(n * 0.95)],
            "p99": sorted_times[int(n * 0.99)],
        }
    
    def summary(self) -> str:
        """Generate summary report."""
        percentiles = self.percentiles
        return f"""
Performance Test Results
========================
Total Requests:      {self.total_requests}
Successful:          {self.successful_requests}
Failed:              {self.failed_requests}
Error Rate:          {self.error_rate:.2f}%

Timing (seconds)
----------------
Total Time:          {self.total_time:.3f}
Min Response:        {self.min_response_time:.3f}
Max Response:        {self.max_response_time:.3f}
Avg Response:        {self.avg_response_time:.3f}
Throughput:          {self.throughput:.2f} req/s

Percentiles
-----------
P50:                 {percentiles.get('p50', 0):.3f}s
P90:                 {percentiles.get('p90', 0):.3f}s
P95:                 {percentiles.get('p95', 0):.3f}s
P99:                 {percentiles.get('p99', 0):.3f}s
"""


class PerformanceTester:
    """Performance testing utility."""
    
    def __init__(self, base_url: str, concurrency: int = 10, duration: int = 60):
        self.base_url = base_url
        self.concurrency = concurrency
        self.duration = duration
        self.results = PerformanceResults()
        
    async def run_load_test(self, scenario: Callable, total_requests: int = 1000) -> PerformanceResults:
        """Run load test with specified concurrency."""
        self.results = PerformanceResults()
        semaphore = asyncio.Semaphore(self.concurrency)
        
        async def _execute():
            async with semaphore:
                start = time.time()
                try:
                    await scenario()
                    elapsed = time.time() - start
                    self.results.response_times.append(elapsed)
                    self.results.min_response_time = min(self.results.min_response_time, elapsed)
                    self.results.max_response_time = max(self.results.max_response_time, elapsed)
                    self.results.successful_requests += 1
                except Exception as e:
                    self.results.errors.append(str(e))
                    self.results.failed_requests += 1
                finally:
                    self.results.total_requests += 1
        
        start_time = time.time()
        tasks = [_execute() for _ in range(total_requests)]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.results.total_time = time.time() - start_time
        
        if self.results.response_times:
            self.results.avg_response_time = sum(self.results.response_times) / len(self.results.response_times)
        
        return self.results
    
    async def run_stress_test(self, scenario: Callable, max_concurrency: int = 100,
                              step: int = 10, step_duration: int = 30) -> Dict[int, PerformanceResults]:
        """Run stress test with increasing concurrency."""
        results = {}
        for concurrency in range(step, max_concurrency + 1, step):
            self.concurrency = concurrency
            print(f"Testing with {concurrency} concurrent users...")
            result = await self.run_load_test(scenario, total_requests=concurrency * step_duration)
            results[concurrency] = result
        return results
    
    async def run_spike_test(self, scenario: Callable, normal_load: int = 10,
                            spike_load: int = 100, spike_duration: int = 10) -> Dict[str, PerformanceResults]:
        """Run spike test."""
        # Normal load
        self.concurrency = normal_load
        normal_result = await self.run_load_test(scenario, total_requests=normal_load * 30)
        
        # Spike
        self.concurrency = spike_load
        spike_result = await self.run_load_test(scenario, total_requests=spike_load * spike_duration)
        
        # Recovery
        self.concurrency = normal_load
        recovery_result = await self.run_load_test(scenario, total_requests=normal_load * 30)
        
        return {
            "normal": normal_result,
            "spike": spike_result,
            "recovery": recovery_result
        }
    
    def measure_latency(self, scenario: Callable, iterations: int = 100) -> PerformanceResults:
        """Measure latency with single-threaded requests."""
        self.results = PerformanceResults()
        
        for _ in range(iterations):
            start = time.time()
            try:
                scenario()
                elapsed = time.time() - start
                self.results.response_times.append(elapsed)
                self.results.min_response_time = min(self.results.min_response_time, elapsed)
                self.results.max_response_time = max(self.results.max_response_time, elapsed)
                self.results.successful_requests += 1
            except Exception as e:
                self.results.errors.append(str(e))
                self.results.failed_requests += 1
            finally:
                self.results.total_requests += 1
        
        self.results.total_time = sum(self.results.response_times)
        if self.results.response_times:
            self.results.avg_response_time = sum(self.results.response_times) / len(self.results.response_times)
        
        return self.results
