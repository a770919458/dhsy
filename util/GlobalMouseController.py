# GlobalMouseController.py
import ctypes
import threading


class GlobalMouseController:
    """
    全局鼠标控制工具类
    提供系统级别的鼠标控制功能（谨慎使用）
    """

    def __init__(self):
        self.is_globally_disabled = False
        self.lock = threading.Lock()

    def disable_mouse_globally(self) -> bool:
        """
        全局禁用鼠标输入

        Returns:
            bool: 操作是否成功
        """
        try:
            with self.lock:
                result = ctypes.windll.user32.BlockInput(True)
                self.is_globally_disabled = True
                return bool(result)
        except Exception as e:
            print(f"全局禁用鼠标失败: {e}")
            return False

    def enable_mouse_globally(self) -> bool:
        """
        全局恢复鼠标输入

        Returns:
            bool: 操作是否成功
        """
        try:
            with self.lock:
                result = ctypes.windll.user32.BlockInput(False)
                self.is_globally_disabled = False
                return bool(result)
        except Exception as e:
            print(f"全局恢复鼠标失败: {e}")
            return False

    def is_mouse_globally_disabled(self) -> bool:
        """
        检查鼠标是否被全局禁用

        Returns:
            bool: 是否被全局禁用
        """
        return self.is_globally_disabled

    def temporary_disable(self, duration: float = 5.0) -> bool:
        """
        临时禁用鼠标一段时间

        Args:
            duration: 禁用时长（秒）

        Returns:
            bool: 操作是否成功
        """
        import time

        if self.disable_mouse_globally():
            def enable_after_delay():
                time.sleep(duration)
                self.enable_mouse_globally()

            thread = threading.Thread(target=enable_after_delay)
            thread.daemon = True
            thread.start()
            return True
        return False