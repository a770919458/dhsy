"""
窗口操作工具类，支持通过句柄精确定位控件并直接发送消息完成读写或点击操作。

相比通过鼠标模拟点击，这种方式不会抢占全局光标，也更节省资源。
"""
from __future__ import annotations

import ctypes
import time
from typing import Callable, Dict, List, Optional, Tuple

import win32con
import win32gui


class WindowAutomationError(Exception):
    """Raised when a window handle cannot be used for the requested action."""


class WindowAutomation:
    """
    对外暴露若干常用能力：

    1. 查找窗口/控件句柄
    2. 获取或设置控件文本
    3. 发送无鼠标的按钮点击
    """

    def __init__(self):
        self._user32 = ctypes.windll.user32

    # ------------------------------------------------------------------ 查找类
    def find_windows(
        self,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
        exact_match: bool = False,
    ) -> List[int]:
        """
        返回符合标题/类名条件的顶层窗口句柄列表。

        Args:
            title: 窗口标题（None 表示忽略此条件）
            class_name: 窗口类名
            exact_match: True 则要求完全匹配，否则做子串匹配
        """
        windows: List[int] = []
        title_lower = title.lower() if title and not exact_match else title
        class_lower = class_name.lower() if class_name and not exact_match else class_name

        def _enum_handler(hwnd: int, _param: Optional[int]):
            if title_lower is not None:
                current_title = win32gui.GetWindowText(hwnd)
                cmp_title = current_title if exact_match else current_title.lower()
                if (exact_match and cmp_title != title_lower) or (
                    not exact_match and title_lower not in cmp_title
                ):
                    return True

            if class_lower is not None:
                current_class = win32gui.GetClassName(hwnd)
                cmp_class = current_class if exact_match else current_class.lower()
                if (exact_match and cmp_class != class_lower) or (
                    not exact_match and class_lower not in cmp_class
                ):
                    return True

            windows.append(hwnd)
            return True

        win32gui.EnumWindows(_enum_handler, None)
        return windows

    def find_window(
        self,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
        exact_match: bool = False,
    ) -> Optional[int]:
        """返回第一个匹配的顶层窗口句柄。"""
        matches = self.find_windows(title=title, class_name=class_name, exact_match=exact_match)
        return matches[0] if matches else None

    def find_child_window(
        self,
        parent_hwnd: int,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
        exact_match: bool = False,
        predicate: Optional[Callable[[int], bool]] = None,
    ) -> Optional[int]:
        """
        查找子窗口。

        Args:
            parent_hwnd: 父窗口句柄
            title: 子窗口标题
            class_name: 子窗口类名
            exact_match: 是否需要完全匹配
            predicate: 更复杂的自定义条件，返回 True 时表示命中
        """
        if not win32gui.IsWindow(parent_hwnd):
            return None

        target = None
        title_lower = title.lower() if title and not exact_match else title
        class_lower = class_name.lower() if class_name and not exact_match else class_name

        def _matcher(hwnd: int) -> bool:
            if title_lower is not None:
                hwnd_title = win32gui.GetWindowText(hwnd)
                cmp_title = hwnd_title if exact_match else hwnd_title.lower()
                if (exact_match and cmp_title != title_lower) or (
                    not exact_match and title_lower not in cmp_title
                ):
                    return False

            if class_lower is not None:
                hwnd_class = win32gui.GetClassName(hwnd)
                cmp_class = hwnd_class if exact_match else hwnd_class.lower()
                if (exact_match and cmp_class != class_lower) or (
                    not exact_match and class_lower not in cmp_class
                ):
                    return False

            if predicate:
                return predicate(hwnd)
            return True

        def _enum_child(hwnd: int, _param: Optional[int]):
            nonlocal target
            if _matcher(hwnd):
                target = hwnd
                return False
            return True

        win32gui.EnumChildWindows(parent_hwnd, _enum_child, None)
        return target

    def get_child_elements(
        self,
        parent_hwnd: int,
        recursive: bool = False,
        max_depth: int = 3,
        include_invisible: bool = False,
    ) -> List[Dict[str, object]]:
        """
        根据父窗口句柄列出其子控件信息，可选递归获取更深层级。

        Args:
            parent_hwnd: 父窗口句柄
            recursive: True 时继续遍历子孙控件
            max_depth: 递归时的最大深度（从 1 开始计）
            include_invisible: 是否保留不可见控件
        """
        if not win32gui.IsWindow(parent_hwnd):
            raise WindowAutomationError(f"Invalid parent hwnd: {parent_hwnd}")

        elements: List[Dict[str, object]] = []

        def _walk(hwnd: int, level: int) -> None:
            if not include_invisible and not win32gui.IsWindowVisible(hwnd):
                return

            info = self.get_window_info(hwnd)
            info["level"] = level
            elements.append(info)

            if recursive and level < max_depth:
                def _enum(child_hwnd: int, _param: Optional[int]):
                    _walk(child_hwnd, level + 1)
                    return True

                win32gui.EnumChildWindows(hwnd, _enum, None)

        def _root_enum(hwnd: int, _param: Optional[int]):
            _walk(hwnd, 1)
            return True

        win32gui.EnumChildWindows(parent_hwnd, _root_enum, None)
        return elements

    def find_elements_by_keyword(
        self,
        parent_hwnd: int,
        keyword: str,
        include_text: bool = False,
        max_depth: int = 5,
        include_invisible: bool = False,
    ) -> List[Dict[str, object]]:
        """
        递归遍历子控件并返回标题/类名/文本包含关键字的元素信息。

        Args:
            parent_hwnd: 父窗口句柄
            keyword: 需要匹配的关键字（不区分大小写）
            include_text: True 时会尝试读取控件文本并参与匹配
            max_depth: 最大递归深度
            include_invisible: 是否包含不可见控件
                             max_depth <= 0 表示不限制层级
        """
        if not win32gui.IsWindow(parent_hwnd):
            raise WindowAutomationError(f"Invalid parent hwnd: {parent_hwnd}")
        if not keyword:
            return []

        depth_limit = max_depth if max_depth and max_depth > 0 else None
        keyword_lower = keyword.lower()
        matched: List[Dict[str, object]] = []

        def _check_and_collect(hwnd: int, level: int) -> None:
            if not include_invisible and not win32gui.IsWindowVisible(hwnd):
                return

            info = self.get_window_info(hwnd)

            candidates = []
            if info.get("title"):
                candidates.append(info["title"].lower())
            if info.get("class_name"):
                candidates.append(info["class_name"].lower())

            if include_text:
                try:
                    text = self.get_control_text(hwnd)
                except WindowAutomationError:
                    text = ""
                info["control_text"] = text
                if text:
                    candidates.append(text.lower())

            if any(keyword_lower in candidate for candidate in candidates):
                info["level"] = level
                matched.append(info)

            if depth_limit and level >= depth_limit:
                return

            def _enum(child_hwnd: int, _param: Optional[int]):
                _check_and_collect(child_hwnd, level + 1)
                return True

            win32gui.EnumChildWindows(hwnd, _enum, None)

        def _root_enum(hwnd: int, _param: Optional[int]):
            _check_and_collect(hwnd, 1)
            return True

        win32gui.EnumChildWindows(parent_hwnd, _root_enum, None)
        return matched

    def wait_for_window(
        self,
        title: Optional[str] = None,
        class_name: Optional[str] = None,
        timeout: float = 5.0,
        interval: float = 0.3,
    ) -> Optional[int]:
        """
        在超时前循环查找窗口，适用于外部应用稍慢启动的场景。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            hwnd = self.find_window(title=title, class_name=class_name)
            if hwnd:
                return hwnd
            time.sleep(interval)
        return None

    # ------------------------------------------------------------------ 信息读写
    def get_window_info(self, hwnd: int) -> Dict[str, object]:
        """返回标题、类名以及坐标等常用信息。"""
        if not win32gui.IsWindow(hwnd):
            raise WindowAutomationError(f"Invalid hwnd: {hwnd}")

        rect = win32gui.GetWindowRect(hwnd)
        return {
            "hwnd": hwnd,
            "title": win32gui.GetWindowText(hwnd),
            "class_name": win32gui.GetClassName(hwnd),
            "rect": rect,
            "width": rect[2] - rect[0],
            "height": rect[3] - rect[1],
            "visible": win32gui.IsWindowVisible(hwnd),
            "enabled": win32gui.IsWindowEnabled(hwnd),
        }

    def get_control_text(self, hwnd: int) -> str:
        """通过 WM_GETTEXT 获取控件文本。"""
        if not win32gui.IsWindow(hwnd):
            raise WindowAutomationError(f"Invalid hwnd: {hwnd}")

        length = win32gui.SendMessage(hwnd, win32con.WM_GETTEXTLENGTH, 0, 0)
        buffer = ctypes.create_unicode_buffer(length + 1)
        win32gui.SendMessage(hwnd, win32con.WM_GETTEXT, length + 1, buffer)
        return buffer.value

    def set_control_text(self, hwnd: int, text: str) -> None:
        """设置输入框等控件的文本。"""
        if not win32gui.IsWindow(hwnd):
            raise WindowAutomationError(f"Invalid hwnd: {hwnd}")
        win32gui.SendMessage(hwnd, win32con.WM_SETTEXT, 0, text)

    # ------------------------------------------------------------------ 控制类
    def click_control(self, hwnd: int) -> None:
        """
        对按钮类控件发送 BM_CLICK，不需要移动鼠标或激活窗口。
        """
        if not win32gui.IsWindow(hwnd):
            raise WindowAutomationError(f"Invalid hwnd: {hwnd}")
        win32gui.SendMessage(hwnd, win32con.BM_CLICK, 0, 0)

    def send_command(self, target_hwnd: int, command: int, notify_code: int = 0) -> None:
        """
        直接向父窗口发送 WM_COMMAND，可用于菜单或自定义控件。
        """
        if not win32gui.IsWindow(target_hwnd):
            raise WindowAutomationError(f"Invalid hwnd: {target_hwnd}")

        parent = win32gui.GetParent(target_hwnd)
        if not parent:
            raise WindowAutomationError("Target control does not have a parent window.")

        control_id = win32gui.GetDlgCtrlID(target_hwnd)
        wparam = (notify_code << 16) | (control_id & 0xFFFF)
        win32gui.SendMessage(parent, win32con.WM_COMMAND, wparam, target_hwnd)

    # ------------------------------------------------------------------ 便捷组合
    def find_and_click(
        self,
        window_title: str,
        button_title: Optional[str] = None,
        button_class: Optional[str] = "Button",
        timeout: float = 5.0,
    ) -> bool:
        """
        等待窗口出现后查找按钮并点击，常用于自动化登录/弹窗处理。
        """
        hwnd = self.wait_for_window(title=window_title, timeout=timeout)
        if not hwnd:
            return False

        btn = self.find_child_window(hwnd, title=button_title, class_name=button_class)
        if not btn:
            return False

        self.click_control(btn)
        return True
