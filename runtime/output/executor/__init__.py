"""Physical execution contracts and non-actuating dry-run implementation."""

from .contract import ExecutionLeaseState, PhysicalExecutor, ReadbackRequirement
from .dry_run import DryRunExecutor
from .records import ExecutionRecord
from .command_plan import PhysicalCommandPlan, PhysicalCommandStep, build_command_plan
from .bench_shadow import BenchExecutionShadow, BenchObservation, BenchShadowResult

__all__ = ["PhysicalExecutor", "ReadbackRequirement", "ExecutionLeaseState", "DryRunExecutor", "ExecutionRecord", "PhysicalCommandPlan", "PhysicalCommandStep", "build_command_plan", "BenchExecutionShadow", "BenchObservation", "BenchShadowResult"]
