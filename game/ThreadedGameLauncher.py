import threading
import concurrent.futures
import queue
from typing import List, Dict, Callable

from game.GameDahuaXiyou import DaHuaXiYouGame


class ThreadedGameLauncher:
    def __init__(self, max_workers: int = 3):
        """
        多线程游戏启动器

        Args:
            max_workers (int): 最大线程数
        """
        self.max_workers = max_workers
        self.results_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.stop_event = threading.Event()

    def launch_games_threaded(self, adb_manager, selected_windows: List[Dict],
                              progress_callback: Callable = None,
                              log_callback: Callable = None) -> Dict:
        """
        多线程启动游戏

        Args:
            adb_manager: ADB管理器实例
            selected_windows: 选中的窗口列表
            progress_callback: 进度回调函数
            log_callback: 日志回调函数

        Returns:
            Dict: 启动结果统计
        """
        total_windows = len(selected_windows)
        completed_count = 0
        results = {
            'total': total_windows,
            'success': 0,
            'failed': 0,
            'details': []
        }

        def _log_message(message: str):
            """线程安全的日志记录"""
            if log_callback:
                log_callback(message)
            else:
                print(message)

        def _update_progress(current: int, message: str):
            """线程安全的进度更新"""
            if progress_callback:
                progress_callback(current, message)

        def _launch_single_game(window_info: Dict) -> Dict:
            """启动单个游戏（工作线程函数）"""
            try:
                hwnd = window_info['hwnd']
                title = window_info.get('title', '未知')

                # 发送进度更新
                self.progress_queue.put({
                    'type': 'start',
                    'hwnd': hwnd,
                    'title': title,
                    'message': f"开始启动: {title}"
                })

                # 获取端口号
                adb_port = adb_manager.get_port_from_handle(window_info)
                window_info['adb_port'] = adb_port
                # 连接到模拟器
                if not adb_manager.connect_to_simulator(hwnd, adb_port):
                    result = {
                        'hwnd': hwnd,
                        'title': title,
                        'success': False,
                        'error': '连接失败',
                        'message': f"✗ 连接失败: {title}"
                    }
                    self.progress_queue.put({
                        'type': 'fail',
                        'hwnd': hwnd,
                        'title': title,
                        'message': result['message']
                    })
                    return result

                # 创建游戏实例并启动
                game = DaHuaXiYouGame(adb_manager, hwnd)
                if game.launch_game(window_info):
                    result = {
                        'hwnd': hwnd,
                        'title': title,
                        'success': True,
                        'error': None,
                        'message': f"✓ 成功启动: {title}",
                        'game_instance': game
                    }
                    self.progress_queue.put({
                        'type': 'success',
                        'hwnd': hwnd,
                        'title': title,
                        'message': result['message']
                    })
                else:
                    result = {
                        'hwnd': hwnd,
                        'title': title,
                        'success': False,
                        'error': '启动失败',
                        'message': f"✗ 启动失败: {title}"
                    }
                    self.progress_queue.put({
                        'type': 'fail',
                        'hwnd': hwnd,
                        'title': title,
                        'message': result['message']
                    })

                return result

            except Exception as e:
                error_msg = f"启动异常: {str(e)}"
                result = {
                    'hwnd': hwnd,
                    'title': title,
                    'success': False,
                    'error': error_msg,
                    'message': f"✗ 异常: {title} - {error_msg}"
                }
                self.progress_queue.put({
                    'type': 'error',
                    'hwnd': hwnd,
                    'title': title,
                    'message': result['message']
                })
                return result

        # 使用线程池执行
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_window = {
                executor.submit(_launch_single_game, window): window
                for window in selected_windows
            }

            # 启动进度监控线程
            progress_thread = threading.Thread(
                target=self._monitor_progress,
                args=(total_windows, _update_progress, _log_message)
            )
            progress_thread.daemon = True
            progress_thread.start()

            # 收集结果
            for future in concurrent.futures.as_completed(future_to_window):
                if self.stop_event.is_set():
                    break

                window = future_to_window[future]
                try:
                    result = future.result(timeout=300)  # 5分钟超时
                    results['details'].append(result)

                    if result['success']:
                        results['success'] += 1
                    else:
                        results['failed'] += 1

                except concurrent.futures.TimeoutError:
                    result = {
                        'hwnd': window['hwnd'],
                        'title': window.get('title', '未知'),
                        'success': False,
                        'error': '超时',
                        'message': f"✗ 启动超时: {window.get('title', '未知')}"
                    }
                    results['details'].append(result)
                    results['failed'] += 1
                    _log_message(result['message'])

                except Exception as e:
                    result = {
                        'hwnd': window['hwnd'],
                        'title': window.get('title', '未知'),
                        'success': False,
                        'error': str(e),
                        'message': f"✗ 执行异常: {window.get('title', '未知')} - {e}"
                    }
                    results['details'].append(result)
                    results['failed'] += 1
                    _log_message(result['message'])

        # 等待进度线程结束
        self.stop_event.set()
        progress_thread.join(timeout=5)

        return results

    def _monitor_progress(self, total: int, progress_callback: Callable, log_callback: Callable):
        """监控进度并更新UI"""
        completed = 0
        active_tasks = {}

        while not self.stop_event.is_set() and completed < total:
            try:
                # 非阻塞获取进度更新
                progress_info = self.progress_queue.get(timeout=1.0)

                if progress_info['type'] == 'start':
                    active_tasks[progress_info['hwnd']] = progress_info
                    log_callback(f"[开始] {progress_info['message']}")

                elif progress_info['type'] in ['success', 'fail', 'error']:
                    completed += 1
                    if progress_info['hwnd'] in active_tasks:
                        del active_tasks[progress_info['hwnd']]

                    log_callback(progress_info['message'])

                # 更新进度
                progress_msg = f"已完成 {completed}/{total} 个窗口"
                if active_tasks:
                    current_tasks = list(active_tasks.values())[:3]  # 显示前3个进行中的任务
                    task_msgs = [task['title'] for task in current_tasks]
                    progress_msg += f" | 进行中: {', '.join(task_msgs)}"
                    if len(active_tasks) > 3:
                        progress_msg += f" 等{len(active_tasks)}个"

                progress_callback(completed, progress_msg)

            except queue.Empty:
                # 队列为空，继续等待
                continue
            except Exception as e:
                log_callback(f"[进度监控错误] {e}")
                break