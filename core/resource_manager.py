"""
Resource Manager - Calculate optimal workers based on CPU/RAM
Ensures resource usage stays under 80% threshold
"""

import os
import psutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class ResourceConfig:
    """Configuration for parallel processing"""
    max_workers: int
    cpu_percent_limit: float
    ram_percent_limit: float
    estimated_ram_per_file_mb: int

    def __str__(self):
        return f"Workers: {self.max_workers}, CPU limit: {self.cpu_percent_limit}%, RAM limit: {self.ram_percent_limit}%"


class ResourceManager:
    """Manage system resources for parallel processing"""

    # Default limits
    DEFAULT_CPU_LIMIT = 0.80  # 80% CPU
    DEFAULT_RAM_LIMIT = 0.80  # 80% RAM
    DEFAULT_RAM_PER_FILE_MB = 300  # Estimated RAM per PDF file being processed
    MIN_WORKERS = 1
    MAX_WORKERS_CAP = 16  # Hard cap to prevent too many processes

    @classmethod
    def get_system_info(cls) -> dict:
        """Get current system resource information"""
        cpu_count = os.cpu_count() or 1
        memory = psutil.virtual_memory()

        return {
            'cpu_count': cpu_count,
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'ram_total_mb': memory.total // (1024 * 1024),
            'ram_available_mb': memory.available // (1024 * 1024),
            'ram_percent_used': memory.percent,
        }

    @classmethod
    def calculate_optimal_workers(
        cls,
        cpu_limit: float = DEFAULT_CPU_LIMIT,
        ram_limit: float = DEFAULT_RAM_LIMIT,
        ram_per_file_mb: int = DEFAULT_RAM_PER_FILE_MB,
        file_count: Optional[int] = None
    ) -> ResourceConfig:
        """
        Calculate optimal number of workers based on system resources.

        Args:
            cpu_limit: Maximum CPU usage (0.0 - 1.0), default 0.80 (80%)
            ram_limit: Maximum RAM usage (0.0 - 1.0), default 0.80 (80%)
            ram_per_file_mb: Estimated RAM per file in MB
            file_count: Number of files to process (optional, for optimization)

        Returns:
            ResourceConfig with optimal settings
        """
        info = cls.get_system_info()

        # Calculate workers based on CPU (leave 20% for system)
        cpu_workers = max(1, int(info['cpu_count'] * cpu_limit))

        # Calculate workers based on available RAM
        # Only use ram_limit of available RAM
        usable_ram_mb = int(info['ram_available_mb'] * ram_limit)
        ram_workers = max(1, usable_ram_mb // ram_per_file_mb)

        # Take minimum of CPU and RAM constraints
        optimal_workers = min(cpu_workers, ram_workers, cls.MAX_WORKERS_CAP)

        # If file_count provided, don't use more workers than files
        if file_count is not None and file_count > 0:
            optimal_workers = min(optimal_workers, file_count)

        # Ensure at least 1 worker
        optimal_workers = max(cls.MIN_WORKERS, optimal_workers)

        return ResourceConfig(
            max_workers=optimal_workers,
            cpu_percent_limit=cpu_limit * 100,
            ram_percent_limit=ram_limit * 100,
            estimated_ram_per_file_mb=ram_per_file_mb
        )

    @classmethod
    def get_current_usage(cls) -> dict:
        """Get current CPU and RAM usage"""
        memory = psutil.virtual_memory()
        return {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'ram_percent': memory.percent,
            'ram_used_mb': (memory.total - memory.available) // (1024 * 1024),
            'ram_available_mb': memory.available // (1024 * 1024),
        }

    @classmethod
    def is_resource_available(
        cls,
        cpu_limit: float = DEFAULT_CPU_LIMIT,
        ram_limit: float = DEFAULT_RAM_LIMIT
    ) -> bool:
        """Check if resources are available under the limit"""
        usage = cls.get_current_usage()
        return (
            usage['cpu_percent'] < cpu_limit * 100 and
            usage['ram_percent'] < ram_limit * 100
        )
