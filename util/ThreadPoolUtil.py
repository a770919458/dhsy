import threading
import queue
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future, as_completed
from threading import Thread, Lock, RLock, Semaphore, Condition, Event, Timer
from typing import Any, Callable, Dict, List, Optional, Union, Tuple, Set, Generator, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import os
from collections import deque
from contextlib import contextmanager
import uuid
import functools

# 类型变量定义
T = TypeVar('T')
R = TypeVar('R')

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """任务结果"""
    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[Exception] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    @property
    def duration(self) -> Optional[float]:
        """任务执行时长"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'status': self.status.value,
            'result': str(self.result) if self.result is not None else None,
            'error': str(self.error) if self.error is not None else None,
            'duration': self.duration
        }


@dataclass(order=True)
class PriorityTask:
    """优先级任务包装器"""
    priority: int
    created_at: float = field(compare=False)
    task: Any = field(compare=False)
    task_id: str = field(compare=False)
    callback: Optional[Callable] = field(default=None, compare=False)
    on_error: Optional[Callable] = field(default=None, compare=False)


class ThreadWorker(Thread):
    """工作线程"""

    def __init__(
            self,
            task_queue: 'PriorityQueue',
            worker_id: int,
            name: Optional[str] = None,
            daemon: bool = True
    ):
        super().__init__(name=name or f"Worker-{worker_id}", daemon=daemon)
        self.worker_id = worker_id
        self.task_queue = task_queue
        self._stop_event = threading.Event()
        self.current_task: Optional[PriorityTask] = None
        self.tasks_completed = 0
        self.start_time = time.time()
        self.lock = threading.Lock()

    def run(self):
        """线程运行主循环"""
        logger.debug(f"Worker {self.worker_id} started")

        while not self._stop_event.is_set():
            try:
                # 从队列获取任务
                task_item = self.task_queue.get(timeout=1)
                if task_item is None:  # 停止信号
                    break

                self.current_task = task_item
                self._execute_task(task_item)
                self.current_task = None
                self.tasks_completed += 1

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}", exc_info=True)

        logger.debug(f"Worker {self.worker_id} stopped. Completed {self.tasks_completed} tasks")

    def _execute_task(self, task_item: PriorityTask):
        """执行任务"""
        try:
            # 执行任务
            result = task_item.task()

            # 执行回调
            if task_item.callback:
                try:
                    task_item.callback(result)
                except Exception as e:
                    logger.error(f"Callback error for task {task_item.task_id}: {e}")

        except Exception as e:
            logger.error(f"Task {task_item.task_id} failed: {e}", exc_info=True)

            # 错误回调
            if task_item.on_error:
                try:
                    task_item.on_error(e)
                except Exception as callback_error:
                    logger.error(f"Error callback failed: {callback_error}")

        finally:
            self.task_queue.task_done()

    def stop(self):
        """停止工作线程"""
        self._stop_event.set()

    def get_stats(self) -> Dict[str, Any]:
        """获取线程统计信息"""
        with self.lock:
            return {
                'worker_id': self.worker_id,
                'name': self.name,
                'daemon': self.daemon,
                'tasks_completed': self.tasks_completed,
                'running_time': time.time() - self.start_time,
                'is_alive': self.is_alive(),
                'has_current_task': self.current_task is not None,
                'current_task_id': self.current_task.task_id if self.current_task else None
            }


class PriorityQueue(queue.PriorityQueue):
    """优先级队列"""

    def __init__(self, maxsize: int = 0):
        super().__init__(maxsize)
        self._task_counter = 0
        self._lock = threading.Lock()

    def put_task(
            self,
            task: Callable,
            priority: TaskPriority = TaskPriority.NORMAL,
            task_id: Optional[str] = None,
            callback: Optional[Callable] = None,
            on_error: Optional[Callable] = None
    ) -> str:
        """添加任务到队列"""
        task_id = task_id or str(uuid.uuid4())

        with self._lock:
            self._task_counter += 1

        task_item = PriorityTask(
            priority=priority.value,
            created_at=time.time(),
            task=task,
            task_id=task_id,
            callback=callback,
            on_error=on_error
        )

        self.put(task_item)
        return task_id

    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        return {
            'qsize': self.qsize(),
            'maxsize': self.maxsize,
            'unfinished_tasks': self.unfinished_tasks,
            'full': self.full(),
            'empty': self.empty()
        }


class ThreadPool:
    """线程池管理器"""

    def __init__(
            self,
            max_workers: Optional[int] = None,
            name_prefix: str = "ThreadPool",
            daemon: bool = True,
            enable_monitor: bool = True
    ):
        """初始化线程池

        Args:
            max_workers: 最大工作线程数，默认为CPU核心数*2
            name_prefix: 线程名前缀
            daemon: 是否为守护线程
            enable_monitor: 是否启用监控线程
        """
        self.max_workers = max_workers or min(32, (os.cpu_count() or 1) * 2)
        self.name_prefix = name_prefix
        self.daemon = daemon

        # 任务队列
        self.task_queue = PriorityQueue()

        # 工作线程列表
        self.workers: List[ThreadWorker] = []

        # 任务结果映射
        self.task_results: Dict[str, TaskResult] = {}

        # 锁
        self._lock = threading.RLock()
        self._results_lock = threading.RLock()

        # 停止事件
        self._stop_event = threading.Event()

        # 监控
        self.enable_monitor = enable_monitor
        self.monitor_thread: Optional[Thread] = None
        self.monitor_interval = 5  # 监控间隔(秒)

        # 初始化工作线程
        self._init_workers()

        # 启动监控
        if enable_monitor:
            self._start_monitor()

        logger.info(f"ThreadPool initialized with {self.max_workers} workers")

    def _init_workers(self):
        """初始化工作线程"""
        for i in range(self.max_workers):
            worker = ThreadWorker(
                task_queue=self.task_queue,
                worker_id=i + 1,
                name=f"{self.name_prefix}-Worker-{i + 1}",
                daemon=self.daemon
            )
            worker.start()
            self.workers.append(worker)

    def _start_monitor(self):
        """启动监控线程"""

        def monitor():
            while not self._stop_event.is_set():
                try:
                    self._log_stats()
                    time.sleep(self.monitor_interval)
                except Exception as e:
                    logger.error(f"Monitor error: {e}")

        self.monitor_thread = Thread(
            target=monitor,
            name=f"{self.name_prefix}-Monitor",
            daemon=True
        )
        self.monitor_thread.start()

    def submit(
            self,
            func: Callable[..., Any],
            *args,
            priority: TaskPriority = TaskPriority.NORMAL,
            task_id: Optional[str] = None,
            callback: Optional[Callable] = None,
            on_error: Optional[Callable] = None,
            **kwargs
    ) -> str:
        """提交任务

        Args:
            func: 要执行的函数
            *args: 函数参数
            priority: 任务优先级
            task_id: 任务ID，不指定则自动生成
            callback: 成功回调函数
            on_error: 错误回调函数
            **kwargs: 函数关键字参数

        Returns:
            任务ID
        """
        if self._stop_event.is_set():
            raise RuntimeError("ThreadPool is shutting down")

        # 包装任务函数
        def task_wrapper():
            try:
                return func(*args, **kwargs)
            except Exception as e:
                raise e

        # 记录任务开始
        task_id = task_id or str(uuid.uuid4())
        task_result = TaskResult(
            task_id=task_id,
            status=TaskStatus.PENDING
        )

        with self._results_lock:
            self.task_results[task_id] = task_result

        # 包装回调函数
        def wrapped_callback(result):
            with self._results_lock:
                if task_id in self.task_results:
                    self.task_results[task_id].status = TaskStatus.COMPLETED
                    self.task_results[task_id].result = result
                    self.task_results[task_id].end_time = time.time()

            if callback:
                callback(result)

        def wrapped_on_error(error):
            with self._results_lock:
                if task_id in self.task_results:
                    self.task_results[task_id].status = TaskStatus.FAILED
                    self.task_results[task_id].error = error
                    self.task_results[task_id].end_time = time.time()

            if on_error:
                on_error(error)

        # 设置任务开始时间
        with self._results_lock:
            if task_id in self.task_results:
                self.task_results[task_id].start_time = time.time()
                self.task_results[task_id].status = TaskStatus.RUNNING

        # 添加到队列
        return self.task_queue.put_task(
            task=task_wrapper,
            priority=priority,
            task_id=task_id,
            callback=wrapped_callback,
            on_error=wrapped_on_error
        )

    def map(
            self,
            func: Callable[..., R],
            iterable: List[Any],
            timeout: Optional[float] = None,
            max_concurrent: Optional[int] = None
    ) -> Generator[R, None, None]:
        """并发执行多个任务

        Args:
            func: 要执行的函数
            iterable: 参数列表
            timeout: 超时时间(秒)
            max_concurrent: 最大并发数

        Yields:
            任务结果
        """
        if not iterable:
            return

        max_concurrent = max_concurrent or self.max_workers
        semaphore = Semaphore(max_concurrent)
        results = []
        futures = []

        def worker(item, idx):
            with semaphore:
                try:
                    result = func(item)
                    return idx, result, None
                except Exception as e:
                    return idx, None, e

        # 提交所有任务
        for i, item in enumerate(iterable):
            future = self.submit(
                worker,
                item,
                i,
                callback=None
            )
            futures.append(future)

        # 收集结果
        start_time = time.time()
        completed = 0

        while completed < len(futures):
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Map operation timed out after {timeout} seconds")

            for task_id in list(futures):
                with self._results_lock:
                    task_result = self.task_results.get(task_id)

                if task_result and task_result.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    if task_result.status == TaskStatus.COMPLETED:
                        yield task_result.result
                    else:
                        raise task_result.error

                    completed += 1
                    futures.remove(task_id)

            time.sleep(0.01)

    def wait_completion(self, timeout: Optional[float] = None) -> bool:
        """等待所有任务完成

        Args:
            timeout: 超时时间(秒)

        Returns:
            是否所有任务都已完成
        """
        start_time = time.time()

        while True:
            # 检查队列是否为空且没有运行中的任务
            queue_empty = self.task_queue.empty()
            workers_busy = any(w.current_task is not None for w in self.workers)

            if queue_empty and not workers_busy:
                return True

            if timeout and (time.time() - start_time) > timeout:
                return False

            time.sleep(0.1)

    def get_result(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """获取任务结果

        Args:
            task_id: 任务ID
            timeout: 超时时间(秒)

        Returns:
            任务结果

        Raises:
            KeyError: 任务不存在
            TimeoutError: 超时
        """
        start_time = time.time()

        while True:
            with self._results_lock:
                task_result = self.task_results.get(task_id)

            if not task_result:
                raise KeyError(f"Task {task_id} not found")

            if task_result.status == TaskStatus.COMPLETED:
                return task_result.result
            elif task_result.status == TaskStatus.FAILED:
                raise task_result.error or Exception(f"Task {task_id} failed")
            elif task_result.status == TaskStatus.CANCELLED:
                raise RuntimeError(f"Task {task_id} was cancelled")

            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Timeout waiting for task {task_id}")

            time.sleep(0.01)

    def cancel_task(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否取消成功
        """
        # 注意：Python的queue不支持从中间删除元素
        # 这里只能标记任务状态
        with self._results_lock:
            if task_id in self.task_results:
                self.task_results[task_id].status = TaskStatus.CANCELLED
                self.task_results[task_id].end_time = time.time()
                return True
        return False

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None):
        """关闭线程池

        Args:
            wait: 是否等待任务完成
            timeout: 超时时间(秒)
        """
        if self._stop_event.is_set():
            return

        logger.info("Shutting down ThreadPool...")
        self._stop_event.set()

        # 停止监控线程
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)

        # 停止工作线程
        for worker in self.workers:
            worker.stop()

        # 向队列发送停止信号
        for _ in self.workers:
            self.task_queue.put(None)

        # 等待工作线程结束
        if wait:
            start_time = time.time()
            for worker in self.workers:
                remaining = None
                if timeout:
                    elapsed = time.time() - start_time
                    remaining = max(0, timeout - elapsed)

                worker.join(timeout=remaining)

        logger.info("ThreadPool shut down completed")

    def _log_stats(self):
        """记录统计信息"""
        with self._lock:
            stats = self.get_stats()

        logger.info(
            f"ThreadPool Stats: "
            f"Workers={stats['workers']['total']}({stats['workers']['idle']} idle), "
            f"Tasks={stats['tasks']['total']}({stats['tasks']['pending']} pending, "
            f"{stats['tasks']['completed']} completed, {stats['tasks']['failed']} failed), "
            f"Queue={stats['queue_size']}"
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取线程池统计信息"""
        with self._lock:
            workers_stats = []
            for worker in self.workers:
                workers_stats.append(worker.get_stats())

            tasks_stats = {'pending': 0, 'running': 0, 'completed': 0, 'failed': 0, 'cancelled': 0, 'total': 0}
            with self._results_lock:
                for task_result in self.task_results.values():
                    tasks_stats[task_result.status.value] += 1
                    tasks_stats['total'] += 1

            idle_workers = sum(1 for w in self.workers if w.current_task is None)

            return {
                'workers': {
                    'total': len(self.workers),
                    'active': len(self.workers) - idle_workers,
                    'idle': idle_workers,
                    'details': workers_stats
                },
                'tasks': tasks_stats,
                'queue_size': self.task_queue.qsize(),
                'is_shutting_down': self._stop_event.is_set(),
                'max_workers': self.max_workers
            }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown(wait=True)


class AsyncThreadPool:
    """异步线程池（支持async/await）"""

    def __init__(self, max_workers: Optional[int] = None):
        """初始化异步线程池"""
        self.max_workers = max_workers or min(32, (os.cpu_count() or 1) * 4)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.loop = asyncio.new_event_loop()

    async def run_in_thread(self, func: Callable[..., T], *args, **kwargs) -> T:
        """在线程池中运行函数"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            functools.partial(func, *args, **kwargs)
        )

    async def map_async(
            self,
            func: Callable[..., R],
            iterable: List[Any],
            max_concurrent: Optional[int] = None
    ) -> List[R]:
        """异步并发执行多个任务"""
        if not iterable:
            return []

        max_concurrent = max_concurrent or self.max_workers
        semaphore = asyncio.Semaphore(max_concurrent)

        async def worker(item):
            async with semaphore:
                return await self.run_in_thread(func, item)

        tasks = [worker(item) for item in iterable]
        return await asyncio.gather(*tasks, return_exceptions=False)

    def shutdown(self, wait: bool = True):
        """关闭线程池"""
        self.executor.shutdown(wait=wait)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown(wait=True)


class TaskScheduler:
    """任务调度器"""

    def __init__(self, max_workers: int = 4):
        """初始化任务调度器"""
        self.max_workers = max_workers
        self.scheduler = ThreadPoolExecutor(max_workers=max_workers)
        self.scheduled_tasks: Dict[str, Future] = {}
        self.periodic_tasks: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()

    def schedule(
            self,
            func: Callable,
            delay: float,
            *args,
            task_id: Optional[str] = None,
            **kwargs
    ) -> str:
        """延迟执行任务

        Args:
            func: 要执行的函数
            delay: 延迟时间(秒)
            *args: 函数参数
            task_id: 任务ID
            **kwargs: 函数关键字参数

        Returns:
            任务ID
        """
        task_id = task_id or str(uuid.uuid4())

        def scheduled_task():
            time.sleep(delay)
            return func(*args, **kwargs)

        future = self.scheduler.submit(scheduled_task)

        with self.lock:
            self.scheduled_tasks[task_id] = future

        return task_id

    def schedule_at(
            self,
            func: Callable,
            run_time: datetime,
            *args,
            task_id: Optional[str] = None,
            **kwargs
    ) -> str:
        """在指定时间执行任务

        Args:
            func: 要执行的函数
            run_time: 执行时间
            *args: 函数参数
            task_id: 任务ID
            **kwargs: 函数关键字参数

        Returns:
            任务ID
        """
        delay = (run_time - datetime.now()).total_seconds()
        if delay < 0:
            delay = 0

        return self.schedule(func, delay, *args, task_id=task_id, **kwargs)

    def schedule_periodic(
            self,
            func: Callable,
            interval: float,
            *args,
            task_id: Optional[str] = None,
            immediate: bool = False,
            **kwargs
    ) -> str:
        """周期性执行任务

        Args:
            func: 要执行的函数
            interval: 执行间隔(秒)
            *args: 函数参数
            task_id: 任务ID
            immediate: 是否立即执行第一次
            **kwargs: 函数关键字参数

        Returns:
            任务ID
        """
        task_id = task_id or str(uuid.uuid4())
        stop_event = threading.Event()

        def periodic_task():
            if immediate:
                func(*args, **kwargs)

            while not stop_event.is_set():
                time.sleep(interval)
                if not stop_event.is_set():
                    func(*args, **kwargs)

        future = self.scheduler.submit(periodic_task)

        with self.lock:
            self.periodic_tasks[task_id] = {
                'future': future,
                'stop_event': stop_event,
                'interval': interval,
                'func': func,
                'args': args,
                'kwargs': kwargs
            }

        return task_id

    def cancel(self, task_id: str) -> bool:
        """取消任务

        Args:
            task_id: 任务ID

        Returns:
            是否取消成功
        """
        with self.lock:
            # 检查一次性任务
            if task_id in self.scheduled_tasks:
                future = self.scheduled_tasks.pop(task_id)
                future.cancel()
                return True

            # 检查周期性任务
            if task_id in self.periodic_tasks:
                task_info = self.periodic_tasks.pop(task_id)
                task_info['stop_event'].set()
                task_info['future'].cancel()
                return True

        return False

    def shutdown(self, wait: bool = True):
        """关闭调度器"""
        with self.lock:
            # 停止所有周期性任务
            for task_info in self.periodic_tasks.values():
                task_info['stop_event'].set()

            # 取消所有任务
            for future in self.scheduled_tasks.values():
                future.cancel()

            self.scheduled_tasks.clear()
            self.periodic_tasks.clear()

        self.scheduler.shutdown(wait=wait)

    def get_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        with self.lock:
            return {
                'scheduled_tasks': len(self.scheduled_tasks),
                'periodic_tasks': len(self.periodic_tasks),
                'max_workers': self.max_workers
            }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown(wait=True)


class RateLimiter:
    """速率限制器"""

    def __init__(self, max_calls: int, period: float):
        """初始化速率限制器

        Args:
            max_calls: 周期内最大调用次数
            period: 周期长度(秒)
        """
        self.max_calls = max_calls
        self.period = period
        self.calls: deque = deque()
        self.lock = threading.RLock()

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """获取执行许可

        Args:
            blocking: 是否阻塞
            timeout: 超时时间

        Returns:
            是否获取到许可
        """
        with self.lock:
            now = time.time()

            # 移除过期的调用记录
            while self.calls and now - self.calls[0] > self.period:
                self.calls.popleft()

            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return True

        if not blocking:
            return False

        if timeout is None:
            timeout = float('inf')

        # 计算需要等待的时间
        wait_time = self.calls[0] + self.period - now
        if wait_time > timeout:
            return False

        time.sleep(wait_time)
        return self.acquire(blocking=False)

    @contextmanager
    def limit(self):
        """使用上下文管理器进行限流"""
        acquired = self.acquire()
        if not acquired:
            raise RuntimeError("Rate limit exceeded")

        try:
            yield
        finally:
            pass

    async def acquire_async(self) -> bool:
        """异步获取执行许可"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.acquire)

    @contextmanager
    async def limit_async(self):
        """异步上下文管理器进行限流"""
        acquired = await self.acquire_async()
        if not acquired:
            raise RuntimeError("Rate limit exceeded")

        try:
            yield
        finally:
            pass


class ConcurrentUtils:
    """并发工具类"""

    @staticmethod
    def parallel_map(
            func: Callable[..., R],
            items: List[Any],
            max_workers: Optional[int] = None,
            timeout: Optional[float] = None
    ) -> List[R]:
        """并行映射

        Args:
            func: 要执行的函数
            items: 输入列表
            max_workers: 最大工作线程数
            timeout: 超时时间

        Returns:
            结果列表
        """
        max_workers = max_workers or min(32, (os.cpu_count() or 1) * 2)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(func, item): i for i, item in enumerate(items)}
            results = [None] * len(items)

            try:
                for future in as_completed(futures.keys(), timeout=timeout):
                    idx = futures[future]
                    try:
                        results[idx] = future.result()
                    except Exception as e:
                        results[idx] = e
            except TimeoutError:
                # 取消未完成的任务
                for future in futures:
                    if not future.done():
                        future.cancel()
                raise

        return results

    @staticmethod
    def parallel_starmap(
            func: Callable[..., R],
            args_list: List[Tuple],
            max_workers: Optional[int] = None,
            timeout: Optional[float] = None
    ) -> List[R]:
        """并行starmap（支持多参数）"""
        max_workers = max_workers or min(32, (os.cpu_count() or 1) * 2)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(func, *args): i for i, args in enumerate(args_list)}
            results = [None] * len(args_list)

            try:
                for future in as_completed(futures.keys(), timeout=timeout):
                    idx = futures[future]
                    try:
                        results[idx] = future.result()
                    except Exception as e:
                        results[idx] = e
            except TimeoutError:
                for future in futures:
                    if not future.done():
                        future.cancel()
                raise

        return results

    @staticmethod
    def process_map(
            func: Callable[..., R],
            items: List[Any],
            max_workers: Optional[int] = None,
            timeout: Optional[float] = None
    ) -> List[R]:
        """使用进程池并行映射（适合CPU密集型任务）"""
        max_workers = max_workers or os.cpu_count() or 1

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(func, item): i for i, item in enumerate(items)}
            results = [None] * len(items)

            try:
                for future in as_completed(futures.keys(), timeout=timeout):
                    idx = futures[future]
                    try:
                        results[idx] = future.result()
                    except Exception as e:
                        results[idx] = e
            except TimeoutError:
                for future in futures:
                    if not future.done():
                        future.cancel()
                raise

        return results

    @staticmethod
    def retry(
            func: Callable[..., T],
            max_retries: int = 3,
            delay: float = 1.0,
            backoff: float = 2.0,
            exceptions: Tuple[BaseException, ...] = (Exception,)
    ) -> Callable[..., T]:
        """重试装饰器

        Args:
            func: 要重试的函数
            max_retries: 最大重试次数
            delay: 初始延迟时间(秒)
            backoff: 退避因子
            exceptions: 要捕获的异常类型

        Returns:
            包装后的函数
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {current_delay:.2f}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"All {max_retries} attempts failed")

            raise last_exception or RuntimeError("Retry failed")

        return wrapper

    @staticmethod
    def timeout(
            seconds: float,
            timeout_message: str = "Operation timed out"
    ) -> Callable:
        """超时装饰器

        Args:
            seconds: 超时时间(秒)
            timeout_message: 超时消息

        Returns:
            包装后的函数
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> T:
                result = None
                exception = None

                def worker():
                    nonlocal result, exception
                    try:
                        result = func(*args, **kwargs)
                    except Exception as e:
                        exception = e

                thread = Thread(target=worker)
                thread.daemon = True
                thread.start()
                thread.join(timeout=seconds)

                if thread.is_alive():
                    raise TimeoutError(timeout_message)

                if exception is not None:
                    raise exception

                return result

            return wrapper

        return decorator

    @staticmethod
    def synchronized(lock: Optional[threading.Lock] = None):
        """同步装饰器（线程安全）"""

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            func_lock = lock or threading.Lock()

            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> T:
                with func_lock:
                    return func(*args, **kwargs)

            return wrapper

        return decorator


class ThreadSafeCache:
    """线程安全缓存"""

    def __init__(self, maxsize: int = 128, ttl: Optional[float] = None):
        """初始化缓存

        Args:
            maxsize: 最大缓存大小
            ttl: 生存时间(秒)，None表示永不过期
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache: Dict[str, Tuple[Any, Optional[float]]] = {}
        self.lock = threading.RLock()

    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值

        Args:
            key: 缓存键
            default: 默认值

        Returns:
            缓存值或默认值
        """
        with self.lock:
            if key not in self.cache:
                return default

            value, expire_time = self.cache[key]

            # 检查是否过期
            if expire_time is not None and time.time() > expire_time:
                del self.cache[key]
                return default

            return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间(秒)，None使用默认值
        """
        with self.lock:
            # 如果缓存已满，移除最老的项
            if len(self.cache) >= self.maxsize:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]

            expire_time = None
            if ttl is not None:
                expire_time = time.time() + ttl
            elif self.ttl is not None:
                expire_time = time.time() + self.ttl

            self.cache[key] = (value, expire_time)

    def delete(self, key: str) -> bool:
        """删除缓存值

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        with self.lock:
            return {
                'size': len(self.cache),
                'maxsize': self.maxsize,
                'ttl': self.ttl
            }


class ThreadManager:
    """线程管理器（单例）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.initialized = True
            self.thread_pools: Dict[str, ThreadPool] = {}
            self.async_pools: Dict[str, AsyncThreadPool] = {}
            self.schedulers: Dict[str, TaskScheduler] = {}
            self.caches: Dict[str, ThreadSafeCache] = {}
            self.rate_limiters: Dict[str, RateLimiter] = {}
            self.lock = threading.RLock()

    def get_thread_pool(
            self,
            name: str = "default",
            max_workers: Optional[int] = None
    ) -> ThreadPool:
        """获取或创建线程池"""
        with self.lock:
            if name not in self.thread_pools:
                self.thread_pools[name] = ThreadPool(
                    max_workers=max_workers,
                    name_prefix=f"Pool-{name}"
                )
            return self.thread_pools[name]

    def get_async_pool(
            self,
            name: str = "default",
            max_workers: Optional[int] = None
    ) -> AsyncThreadPool:
        """获取或创建异步线程池"""
        with self.lock:
            if name not in self.async_pools:
                self.async_pools[name] = AsyncThreadPool(max_workers=max_workers)
            return self.async_pools[name]

    def get_scheduler(
            self,
            name: str = "default",
            max_workers: int = 4
    ) -> TaskScheduler:
        """获取或创建调度器"""
        with self.lock:
            if name not in self.schedulers:
                self.schedulers[name] = TaskScheduler(max_workers=max_workers)
            return self.schedulers[name]

    def get_cache(
            self,
            name: str = "default",
            maxsize: int = 128,
            ttl: Optional[float] = None
    ) -> ThreadSafeCache:
        """获取或创建缓存"""
        with self.lock:
            if name not in self.caches:
                self.caches[name] = ThreadSafeCache(maxsize=maxsize, ttl=ttl)
            return self.caches[name]

    def get_rate_limiter(
            self,
            name: str = "default",
            max_calls: int = 10,
            period: float = 1.0
    ) -> RateLimiter:
        """获取或创建速率限制器"""
        with self.lock:
            if name not in self.rate_limiters:
                self.rate_limiters[name] = RateLimiter(
                    max_calls=max_calls,
                    period=period
                )
            return self.rate_limiters[name]

    def shutdown_all(self, wait: bool = True):
        """关闭所有资源"""
        with self.lock:
            # 关闭所有线程池
            for name, pool in self.thread_pools.items():
                logger.info(f"Shutting down thread pool: {name}")
                pool.shutdown(wait=wait)

            # 关闭所有异步线程池
            for name, pool in self.async_pools.items():
                logger.info(f"Shutting down async pool: {name}")
                pool.shutdown(wait=wait)

            # 关闭所有调度器
            for name, scheduler in self.schedulers.items():
                logger.info(f"Shutting down scheduler: {name}")
                scheduler.shutdown(wait=wait)

            self.thread_pools.clear()
            self.async_pools.clear()
            self.schedulers.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取所有资源统计"""
        with self.lock:
            stats = {
                'thread_pools': {},
                'async_pools': {},
                'schedulers': {},
                'caches': {},
                'rate_limiters': {}
            }

            for name, pool in self.thread_pools.items():
                stats['thread_pools'][name] = pool.get_stats()

            for name, scheduler in self.schedulers.items():
                stats['schedulers'][name] = scheduler.get_stats()

            for name, cache in self.caches.items():
                stats['caches'][name] = cache.get_stats()

            return stats

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown_all(wait=True)


# 全局线程管理器实例
thread_manager = ThreadManager()


# 使用示例
def example_usage():
    """使用示例"""

    # 示例1: 使用线程池
    print("示例1: 使用线程池")
    with ThreadPool(max_workers=4) as pool:
        # 提交任务
        task_ids = []
        for i in range(10):
            def task(x):
                time.sleep(0.5)
                return f"Task {x} completed"

            task_id = pool.submit(task, i, callback=lambda r: print(r))
            task_ids.append(task_id)

        # 等待所有任务完成
        pool.wait_completion(timeout=10)

        # 获取统计信息
        stats = pool.get_stats()
        print(f"任务统计: {stats['tasks']}")

    # 示例2: 并行处理
    print("\n示例2: 并行处理")

    def process_item(item):
        time.sleep(0.1)
        return item * 2

    items = list(range(20))
    results = ConcurrentUtils.parallel_map(process_item, items, max_workers=5)
    print(f"处理结果: {results[:5]}...")  # 显示前5个

    # 示例3: 使用任务调度器
    print("\n示例3: 使用任务调度器")
    scheduler = TaskScheduler()

    def scheduled_task(name):
        print(f"Scheduled task {name} executed at {datetime.now()}")

    # 延迟执行
    scheduler.schedule(scheduled_task, 2, "delayed")

    # 周期性执行
    task_id = scheduler.schedule_periodic(
        scheduled_task,
        1,
        "periodic",
        immediate=True
    )

    time.sleep(5)

    # 取消周期性任务
    scheduler.cancel(task_id)
    scheduler.shutdown()

    # 示例4: 使用速率限制器
    print("\n示例4: 使用速率限制器")
    limiter = RateLimiter(max_calls=3, period=1)  # 每秒最多3次

    def limited_call(i):
        with limiter.limit():
            print(f"Call {i} at {time.time()}")
            return i

    # 批量调用，会被限流
    with ThreadPool(max_workers=10) as pool:
        for i in range(10):
            pool.submit(limited_call, i)

        pool.wait_completion(timeout=5)

    # 示例5: 使用线程安全缓存
    print("\n示例5: 使用线程安全缓存")
    cache = ThreadSafeCache(maxsize=10, ttl=5)  # 5秒过期

    def expensive_operation(key):
        time.sleep(1)  # 模拟耗时操作
        return f"result_for_{key}"

    def get_cached_value(key):
        # 先从缓存获取
        value = cache.get(key)
        if value is not None:
            return value

        # 缓存不存在，执行耗时操作
        value = expensive_operation(key)
        cache.set(key, value)
        return value

    # 测试缓存
    start = time.time()
    result1 = get_cached_value("key1")
    print(f"第一次获取耗时: {time.time() - start:.2f}s, 结果: {result1}")

    start = time.time()
    result2 = get_cached_value("key1")  # 应该从缓存获取
    print(f"第二次获取耗时: {time.time() - start:.2f}s, 结果: {result2}")

    # 示例6: 使用装饰器
    print("\n示例6: 使用装饰器")

    @ConcurrentUtils.retry(max_retries=3, delay=0.1)
    def unreliable_operation():
        import random
        if random.random() < 0.5:
            raise ValueError("随机失败")
        return "成功"

    @ConcurrentUtils.timeout(seconds=2)
    def long_operation():
        time.sleep(1)
        return "完成"

    # 测试重试
    for _ in range(3):
        try:
            result = unreliable_operation()
            print(f"操作结果: {result}")
            break
        except Exception as e:
            print(f"操作失败: {e}")

    # 测试超时
    try:
        result = long_operation()
        print(f"长操作结果: {result}")
    except TimeoutError as e:
        print(f"操作超时: {e}")

    # 示例7: 使用全局线程管理器
    print("\n示例7: 使用全局线程管理器")

    # 获取默认线程池
    pool = thread_manager.get_thread_pool("default")

    # 提交多个任务
    futures = []
    for i in range(5):
        future = pool.submit(lambda x: x * 2, i)
        futures.append(future)

    # 获取结果
    for i, future in enumerate(futures):
        try:
            result = pool.get_result(future, timeout=5)
            print(f"任务{i}结果: {result}")
        except Exception as e:
            print(f"任务{i}失败: {e}")

    # 获取统计信息
    stats = thread_manager.get_stats()
    print(f"管理器统计: {stats}")


async def async_example():
    """异步示例"""
    print("\n异步示例: 使用异步线程池")

    async with AsyncThreadPool() as pool:
        # 在线程池中运行阻塞函数
        result = await pool.run_in_thread(time.sleep, 0.5)
        print(f"异步运行结果: {result}")

        # 并行处理
        async def process(item):
            await asyncio.sleep(0.1)
            return item * 2

        items = list(range(10))
        results = await pool.map_async(process, items)
        print(f"异步并行结果: {results}")


if __name__ == "__main__":
    # 运行示例
    example_usage()

    # 运行异步示例
    asyncio.run(async_example())

    # 关闭所有线程池
    thread_manager.shutdown_all()