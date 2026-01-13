import asyncio
import threading
import pyperclip
import time
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from pywinauto import keyboard


class ClipboardManager:
    """线程安全的剪切板管理器"""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.operation_lock = threading.Lock()  # 用于同步pyperclip操作
        self.current_operation: Optional[str] = None  # 当前操作窗口标识
        self.operation_timestamps: Dict[str, float] = {}  # 操作时间戳

    @asynccontextmanager
    async def clipboard_operation(self, window_id: str, timeout: int = 10):
        """修复的剪切板操作上下文管理器"""
        start_time = time.time()

        # 等待其他操作完成
        while self.current_operation and self.current_operation != window_id:
            elapsed = time.time() - self.operation_timestamps.get(self.current_operation, 0)
            if elapsed < timeout:
                await asyncio.sleep(0.1)
                # 检查超时
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"剪切板操作超时，窗口 {window_id} 等待过久")
            else:
                # 其他操作超时，强制清除
                self.current_operation = None
                break

        async with self.lock:
            try:
                # 设置当前操作
                self.current_operation = window_id
                self.operation_timestamps[window_id] = time.time()

                # 执行剪切板操作 - 这里yield一个操作函数而不是self
                operation_result = None

                def _perform_operation(operation_type, *args, **kwargs):
                    """执行具体的剪切板操作"""
                    nonlocal operation_result
                    try:
                        if operation_type == "copy":
                            pyperclip.copy(*args, **kwargs)
                            operation_result = "copy_success"
                        elif operation_type == "paste":
                            operation_result = pyperclip.paste()
                        elif operation_type == "clear":
                            pyperclip.copy("")
                            operation_result = "clear_success"
                        return operation_result
                    except Exception as e:
                        operation_result = f"error: {str(e)}"
                        raise

                # yield操作函数给调用者使用
                yield _perform_operation

            finally:
                # 清理操作状态
                if self.current_operation == window_id:
                    self.current_operation = None
                    if window_id in self.operation_timestamps:
                        del self.operation_timestamps[window_id]

    async def safe_copy_operation(self, window_id: str, copy_callback, read_callback,
                                  max_retries: int = 3, retry_delay: float = 0.5) -> Optional[str]:
        """安全的复制-读取操作"""
        for attempt in range(max_retries):
            try:
                async with self.clipboard_operation(window_id) as clipboard:
                    # 执行复制操作
                    with self.operation_lock:
                        copy_callback()

                    # 短暂延迟确保复制完成
                    await asyncio.sleep(0.2)

                    # 读取剪切板内容
                    with self.operation_lock:
                        content = read_callback()

                    # 验证内容是否有效
                    if content and self._validate_content(content, window_id):
                        return content

                    # 如果无效，重试
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)

            except Exception as e:
                print(f"窗口 {window_id} 第 {attempt + 1} 次剪切板操作失败: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        return None

    def _validate_content(self, content: str, window_id: str) -> bool:
        """验证剪切板内容是否有效"""
        # 基本验证
        if not content or content.strip() == "":
            return False

        # 检查是否为明显的错误内容（如其他窗口的用户编号）
        # 这里可以根据具体业务逻辑添加更多验证
        if len(content) > 100:  # 内容过长可能不是用户编号
            return False

        return True

    def select_all_and_get_text(self, hwnd: int):
        """全选并获取选中的文本（简化版）"""

        import pyautogui

        # 保存当前剪切板内容
        try:
            original_text = pyperclip.paste()
        except:
            original_text = ""
        def copy_operation():
            # 清空剪切板以确保获取的是新内容
            pyperclip.copy("")

            # 发送Ctrl+A全选
            pyautogui.hotkey('ctrl', 'a')
            asyncio.sleep(0.1)
            # 发送Ctrl+C复制到剪切板
            pyautogui.hotkey('ctrl', 'c')

        def read_operation() -> Optional[str]:
            """执行读取操作"""
            try:
                return pyperclip.paste().strip()
            except Exception as e:
                print(f"读取剪切板失败: {e}")
                return None

        # 发送Ctrl+C复制
        self.safe_copy_operation(str(hwnd), copy_operation, read_operation)

        # 获取选中的文本
        try:
            selected_text = pyperclip.paste()
        except Exception as e:
            selected_text = ""
            print(f"读取剪切板失败: {e}")

        # 恢复原始剪切板内容
        try:
            pyperclip.copy(original_text)
        except:
            pass

        return selected_text

# 全局剪切板管理器实例
clipboard_manager = ClipboardManager()