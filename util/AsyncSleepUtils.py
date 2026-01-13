import asyncio
import random
import time
from typing import Union, Optional, List, Dict
from dataclasses import dataclass
from enum import Enum
import logging


class SleepMode(Enum):
    """睡眠模式"""
    RANDOM = "random"  # 随机时间
    FIXED = "fixed"  # 固定时间
    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"  # 线性递增


@dataclass
class SleepResult:
    """睡眠结果"""
    sleep_time: float
    actual_sleep: float
    start_time: float
    end_time: float
    mode: SleepMode
    success: bool
    error: Optional[str] = None


class AsyncRandomSleeper:
    """
    异步随机睡眠工具类
    支持多种睡眠模式和策略
    """

    def __init__(self,
                 logger: Optional[logging.Logger] = None,
                 default_min: float = 1.0,
                 default_max: float = 3.0):
        """
        初始化

        Args:
            logger: 日志记录器
            default_min: 默认最小睡眠时间
            default_max: 默认最大睡眠时间
        """
        self.logger = logger or logging.getLogger(__name__)
        self.default_min = default_min
        self.default_max = default_max

        # 统计信息
        self.stats = {
            'total_sleeps': 0,
            'total_sleep_time': 0.0,
            'min_sleep_time': float('inf'),
            'max_sleep_time': 0.0
        }

    def _update_stats(self, sleep_time: float):
        """更新统计信息"""
        self.stats['total_sleeps'] += 1
        self.stats['total_sleep_time'] += sleep_time
        self.stats['min_sleep_time'] = min(self.stats['min_sleep_time'], sleep_time)
        self.stats['max_sleep_time'] = max(self.stats['max_sleep_time'], sleep_time)

    async def sleep_random(self,
                           min_time: Optional[float] = None,
                           max_time: Optional[float] = None,
                           precision: int = 2) -> SleepResult:
        """
        随机睡眠

        Args:
            min_time: 最小睡眠时间，默认1.0
            max_time: 最大睡眠时间，默认3.0
            precision: 时间精度（小数位数）

        Returns:
            SleepResult: 睡眠结果
        """
        min_time = min_time or self.default_min
        max_time = max_time or self.default_max

        # 参数验证
        if min_time <= 0 or max_time <= 0:
            raise ValueError("睡眠时间必须大于0")
        if min_time > max_time:
            raise ValueError(f"最小时间({min_time})不能大于最大时间({max_time})")

        # 生成随机睡眠时间
        sleep_time = round(random.uniform(min_time, max_time), precision)

        return await self._sleep_impl(sleep_time, SleepMode.RANDOM)

    async def sleep_fixed(self,
                          time: float,
                          jitter: float = 0.0) -> SleepResult:
        """
        固定时间睡眠，可添加抖动

        Args:
            time: 固定睡眠时间
            jitter: 抖动范围（±jitter）

        Returns:
            SleepResult: 睡眠结果
        """
        if jitter > 0:
            # 添加抖动
            sleep_time = random.uniform(time - jitter, time + jitter)
            sleep_time = max(0.1, sleep_time)  # 确保不小于0.1秒
        else:
            sleep_time = time

        return await self._sleep_impl(sleep_time, SleepMode.FIXED)

    async def sleep_exponential(self,
                                base_time: float = 1.0,
                                max_time: float = 30.0,
                                attempt: int = 1) -> SleepResult:
        """
        指数退避睡眠

        Args:
            base_time: 基础时间
            max_time: 最大时间
            attempt: 尝试次数（从1开始）

        Returns:
            SleepResult: 睡眠结果
        """
        # 指数计算：base * 2^(attempt-1)
        sleep_time = base_time * (2 ** (attempt - 1))

        # 添加随机抖动（10%）
        jitter = sleep_time * 0.1
        sleep_time = random.uniform(sleep_time - jitter, sleep_time + jitter)

        # 限制最大时间
        sleep_time = min(sleep_time, max_time)
        sleep_time = max(0.1, sleep_time)  # 确保不小于0.1秒

        return await self._sleep_impl(sleep_time, SleepMode.EXPONENTIAL)

    async def sleep_linear(self,
                           base_time: float = 1.0,
                           increment: float = 1.0,
                           max_time: float = 10.0,
                           attempt: int = 1) -> SleepResult:
        """
        线性递增睡眠

        Args:
            base_time: 基础时间
            increment: 每次递增量
            max_time: 最大时间
            attempt: 尝试次数

        Returns:
            SleepResult: 睡眠结果
        """
        sleep_time = base_time + (increment * (attempt - 1))

        # 添加随机抖动（10%）
        jitter = sleep_time * 0.1
        sleep_time = random.uniform(sleep_time - jitter, sleep_time + jitter)

        # 限制最大时间
        sleep_time = min(sleep_time, max_time)
        sleep_time = max(0.1, sleep_time)

        return await self._sleep_impl(sleep_time, SleepMode.LINEAR)

    async def _sleep_impl(self, sleep_time: float, mode: SleepMode) -> SleepResult:
        """
        睡眠实现

        Args:
            sleep_time: 睡眠时间
            mode: 睡眠模式

        Returns:
            SleepResult: 睡眠结果
        """
        start_time = time.time()

        try:
            self.logger.info(f"开始睡眠 [{mode.value}]，时间: {sleep_time:.2f}秒")

            # 记录开始时间
            await asyncio.sleep(sleep_time)

            # 计算实际睡眠时间
            end_time = time.time()
            actual_sleep = end_time - start_time

            # 更新统计
            self._update_stats(sleep_time)

            self.logger.info(f"睡眠完成，实际: {actual_sleep:.2f}秒")

            return SleepResult(
                sleep_time=sleep_time,
                actual_sleep=actual_sleep,
                start_time=start_time,
                end_time=end_time,
                mode=mode,
                success=True
            )

        except asyncio.CancelledError:
            # 任务被取消
            end_time = time.time()
            actual_sleep = end_time - start_time

            self.logger.warning(f"睡眠被取消，已睡: {actual_sleep:.2f}秒")

            return SleepResult(
                sleep_time=sleep_time,
                actual_sleep=actual_sleep,
                start_time=start_time,
                end_time=end_time,
                mode=mode,
                success=False,
                error="Cancelled"
            )

        except Exception as e:
            # 其他错误
            end_time = time.time()
            actual_sleep = end_time - start_time

            self.logger.error(f"睡眠出错: {e}")

            return SleepResult(
                sleep_time=sleep_time,
                actual_sleep=actual_sleep,
                start_time=start_time,
                end_time=end_time,
                mode=mode,
                success=False,
                error=str(e)
            )

    def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = self.stats.copy()

        if stats['total_sleeps'] > 0:
            stats['average_sleep_time'] = stats['total_sleep_time'] / stats['total_sleeps']
        else:
            stats['average_sleep_time'] = 0.0

        return stats

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_sleeps': 0,
            'total_sleep_time': 0.0,
            'min_sleep_time': float('inf'),
            'max_sleep_time': 0.0
        }