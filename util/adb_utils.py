"""
雷电模拟器ADB工具类 - 游戏脚本专用版
设计原则：最小化干扰、避免检测、不争抢鼠标控制权
"""
import re
import subprocess
import random
import time
import os
from typing import Optional, Tuple


class LeidianADB:
    def __init__(self, emulator_port: int = 5555, ld_console_path: Optional[str] = None):
        """
        初始化雷电模拟器ADB连接

        Args:
            emulator_port: 模拟器ADB端口，默认5555
            ld_console_path: 雷电多开器路径，如 D:/LDPlayer/LDPlayer9/ldconsole.exe
        """
        self.emulator_port = emulator_port
        self.ld_console_path = ld_console_path
        self.adb_path = self._find_adb()
        self.connected = False

        # 反检测参数配置
        self.human_params = {
            'click_delay': (0.05, 0.2),  # 点击延迟范围(秒)
            'swipe_delay': (0.1, 0.3),  # 滑动延迟范围
            'random_offset': 3,  # 随机偏移像素
            'curve_points': 3,  # 曲线滑动点数
            'action_gap': (0.5, 1.5),  # 动作间隔范围
        }

        # 操作历史记录（用于避免模式化）
        self.action_history = []
        self.max_history = 10

    def _find_adb(self) -> str:
        """自动查找ADB路径"""
        # 优先使用系统环境变量中的adb
        try:
            subprocess.run("adb version", shell=True, capture_output=True, check=True)
            return "adb"
        except:
            # 尝试查找雷电模拟器自带的adb
            common_paths = [
                "D:/LDPlayer/LDPlayer9/adb.exe",
                "C:/LDPlayer/LDPlayer9/adb.exe",
                "D:/leidian/LDPlayer9/adb.exe",
                "/mnt/c/LDPlayer/LDPlayer9/adb.exe"
            ]
            for path in common_paths:
                if os.path.exists(path):
                    return path
            return "adb"  # 最后尝试系统adb

    def connect(self, index: int = 0) -> bool:
        """
        连接雷电模拟器

        Args:
            index: 模拟器索引（多开时使用）
        Returns:
            bool: 连接是否成功
        """
        try:
            # 方法1: 如果提供了ldconsole路径，通过多开器连接
            if self.ld_console_path and os.path.exists(self.ld_console_path):
                cmd = f'"{self.ld_console_path}" adb --index {index} --command "connect 127.0.0.1:{self.emulator_port}"'
                subprocess.run(cmd, shell=True, capture_output=True)
                time.sleep(1)

            # 方法2: 直接连接
            result = subprocess.run(
                f"{self.adb_path} connect 127.0.0.1:{self.emulator_port}",
                shell=True,
                capture_output=True,
                text=True
            )

            if "connected" in result.stdout or "already" in result.stdout:
                self.connected = True
                print(f"✅ 成功连接到雷电模拟器 127.0.0.1:{self.emulator_port}")
                return True
            else:
                print(f"❌ 连接失败: {result.stdout}")
                return False

        except Exception as e:
            print(f"❌ 连接异常: {e}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.connected:
            subprocess.run(f"{self.adb_path} disconnect 127.0.0.1:{self.emulator_port}", shell=True)
            self.connected = False
            print("已断开连接")


    def get_port_from_handle(self, title: str) -> Optional[int]:
        """
        从窗口标题提取端口号

        雷电模拟器窗口标题可能包含的模式:
        - "雷电模拟器" -> 端口 5555
        - "雷电模拟器-1" -> 端口 5555
        - "雷电模拟器-2" -> 端口 5557
        - "LDPlayer" -> 端口 5555
        - "LDPlayer1" -> 端口 5555
        - "LDPlayer2" -> 端口 5557
        - 包含"5555"等数字 -> 直接提取
        """
        if not title:
            return None

        title_lower = title.lower()

        # 直接查找端口号
        port_match = re.search(r'(\d{4,5})', title)
        if port_match:
            port = int(port_match.group(1))
            if 5555 <= port <= 5580:  # 雷电常用端口范围
                return port

        # 根据雷电模拟器编号映射端口
        if "雷电模拟器" in title or "ldplayer" in title_lower:
            # 查找模拟器编号
            index_match = re.search(r'[_-]?(\d+)', title)
            if index_match:
                index = int(index_match.group(1))
                # 雷电模拟器端口映射: 索引1->5555, 索引2->5557, 索引3->5559, 等等
                return 5555 + (index) * 2
            else:
                # 默认第一个模拟器
                return 5555

        return None

    def _execute_adb(self, command: str, capture: bool = True) -> Optional[str]:
        """执行ADB命令"""
        if not self.connected:
            if not self.connect():
                return None

        full_cmd = f"{self.adb_path} -s 127.0.0.1:{self.emulator_port} {command}"

        try:
            if capture:
                result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
                return result.stdout.strip()
            else:
                subprocess.run(full_cmd, shell=True, capture_output=False)
                return "executed"
        except Exception as e:
            print(f"ADB命令执行失败: {e}")
            return None

    def _add_random_offset(self, x: int, y: int) -> Tuple[int, int]:
        """添加随机偏移，防止固定坐标"""
        offset = self.human_params['random_offset']
        x_new = x + random.randint(-offset, offset)
        y_new = y + random.randint(-offset, offset)
        return x_new, y_new

    def _get_random_delay(self, delay_type: str = 'click') -> float:
        """获取随机延迟时间"""
        delay_range = self.human_params.get(f'{delay_type}_delay', (0.1, 0.3))
        return random.uniform(*delay_range)

    def _human_interval(self):
        """人类行为间隔"""
        time.sleep(random.uniform(*self.human_params['action_gap']))

    def _record_action(self, action_type: str, params: dict):
        """记录操作历史，用于避免模式化"""
        self.action_history.append({
            'type': action_type,
            'params': params,
            'timestamp': time.time()
        })
        if len(self.action_history) > self.max_history:
            self.action_history.pop(0)

    def _avoid_pattern(self, action_type: str, base_params: dict) -> dict:
        """避免操作模式化"""
        # 分析历史记录，避免重复模式
        recent_actions = [a for a in self.action_history[-3:] if a['type'] == action_type]

        if len(recent_actions) >= 2:
            # 如果最近有相似操作，增加一些变化
            if action_type == 'tap':
                x, y = base_params.get('x', 0), base_params.get('y', 0)
                x, y = self._add_random_offset(x, y)
                base_params.update({'x': x, 'y': y})

        return base_params

    def get_screen_resolution(self) -> Optional[Tuple[int, int]]:
        """获取屏幕分辨率"""
        output = self._execute_adb("shell wm size")
        if output and "Physical size" in output:
            size_str = output.split(": ")[1]
            width, height = map(int, size_str.split("x"))
            return width, height
        return None

    def safe_tap(self, x: int, y: int, delay_before: bool = True, delay_after: bool = True) -> bool:
        """
        安全点击（带随机偏移和延迟）

        Args:
            x, y: 点击坐标
            delay_before: 点击前是否延迟
            delay_after: 点击后是否延迟
        """
        try:
            # 避免模式化
            params = self._avoid_pattern('tap', {'x': x, 'y': y})
            x, y = params['x'], params['y']

            # 最终添加随机偏移
            x, y = self._add_random_offset(x, y)

            if delay_before:
                time.sleep(self._get_random_delay('click'))

            # 执行点击
            result = self._execute_adb(f"shell input tap {x} {y}")

            if delay_after:
                time.sleep(self._get_random_delay('click'))

            self._record_action('tap', {'x': x, 'y': y})
            self._human_interval()

            return result is not None

        except Exception as e:
            print(f"点击失败: {e}")
            return False

    def safe_swipe(self, x1: int, y1: int, x2: int, y2: int,
                   duration: Optional[int] = None, curve: bool = True) -> bool:
        """
        自然滑动（支持曲线滑动）

        Args:
            x1, y1: 起始坐标
            x2, y2: 结束坐标
            duration: 滑动持续时间(ms)，None则随机生成
            curve: 是否使用曲线滑动
        """
        try:
            # 随机滑动时间
            if duration is None:
                duration = random.randint(300, 800)

            if curve:
                # 曲线滑动（更自然）
                return self._curve_swipe(x1, y1, x2, y2, duration)
            else:
                # 直线滑动
                x1, y1 = self._add_random_offset(x1, y1)
                x2, y2 = self._add_random_offset(x2, y2)

                time.sleep(self._get_random_delay('swipe'))

                result = self._execute_adb(f"shell input swipe {x1} {y1} {x2} {y2} {duration}")

                self._record_action('swipe', {
                    'x1': x1, 'y1': y1,
                    'x2': x2, 'y2': y2,
                    'duration': duration
                })

                self._human_interval()
                return result is not None

        except Exception as e:
            print(f"滑动失败: {e}")
            return False

    def _curve_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
        """曲线滑动实现"""
        # 生成曲线控制点
        control_points = []
        num_points = self.human_params['curve_points']

        for i in range(1, num_points + 1):
            t = i / (num_points + 1)
            # 贝塞尔曲线插值
            cx = int(x1 + (x2 - x1) * t + random.randint(-20, 20))
            cy = int(y1 + (y2 - y1) * t + random.randint(-20, 20))
            control_points.append((cx, cy))

        # 分段滑动
        points = [(x1, y1)] + control_points + [(x2, y2)]
        segment_duration = duration // len(points)

        for i in range(len(points) - 1):
            px1, py1 = points[i]
            px2, py2 = points[i + 1]

            # 每段添加随机偏移
            px1, py1 = self._add_random_offset(px1, py1)
            px2, py2 = self._add_random_offset(px2, py2)

            self._execute_adb(f"shell input swipe {px1} {py1} {px2} {py2} {segment_duration}")
            time.sleep(segment_duration / 1000 * random.uniform(0.8, 1.2))

        return True

    def tap_with_vibration(self, x: int, y: int) -> bool:
        """
        模拟触摸反馈（短震动）
        注意：需要模拟器支持震动
        """
        # 先点击
        self.safe_tap(x, y)

        # 短暂震动（100ms）
        self._execute_adb("shell vibrate 100")

        return True

    def capture_screen(self, filename: str = None) -> Optional[str]:
        """
        截取屏幕（不保存到模拟器内部）

        Args:
            filename: 保存文件名，None则生成时间戳文件名
        Returns:
            保存的文件路径
        """
        try:
            screenshots_dir = os.path.join(os.getcwd(), "screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            if filename is None:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.png"

            # 确保文件名在screenshots目录下
            if not filename.startswith(screenshots_dir):
                filename = os.path.join(screenshots_dir, filename)

            # 直接获取截图数据，不保存到模拟器
            cmd = f"exec-out screencap -p > {filename}"
            result = subprocess.run(
                f"{self.adb_path} -s 127.0.0.1:{self.emulator_port} {cmd}",
                shell=True,
                capture_output=True
            )

            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                # 获取相对路径用于显示
                relative_path = os.path.relpath(filename, os.getcwd())
                print(f"📸📸 截图保存: {relative_path}")
                return filename
            else:
                # 备用方法
                temp_path = f"/sdcard/temp_screen_{int(time.time())}.png"
                self._execute_adb(f"shell screencap -p {temp_path}")
                self._execute_adb(f"pull {temp_path} {filename}")
                self._execute_adb(f"shell rm {temp_path}")

                if os.path.exists(filename):
                    return filename

        except Exception as e:
            print(f"截图失败: {e}")

        return None

    def long_press(self, x: int, y: int, duration: float = 1.0) -> bool:
        """
        长按操作

        Args:
            duration: 长按时间(秒)
        """
        try:
            x, y = self._add_random_offset(x, y)

            # 长按通过滑动实现（相同坐标滑动）
            swipe_duration = int(duration * 1000)
            result = self._execute_adb(f"shell input swipe {x} {y} {x} {y} {swipe_duration}")

            self._record_action('long_press', {'x': x, 'y': y, 'duration': duration})
            self._human_interval()

            return result is not None

        except Exception as e:
            print(f"长按失败: {e}")
            return False

    def input_text(self, text: str) -> bool:
        """
        输入文本（模拟人类输入速度）
        """
        try:
            # 逐个字符输入，模拟人类打字
            for char in text:
                self._execute_adb(f'shell input text "{char}"')
                time.sleep(random.uniform(0.05, 0.15))  # 打字间隔

            self._record_action('input_text', {'length': len(text)})
            return True

        except Exception as e:
            print(f"输入文本失败: {e}")
            return False

    def key_event(self, keycode: int) -> bool:
        """按键事件"""
        result = self._execute_adb(f"shell input keyevent {keycode}")
        time.sleep(random.uniform(0.1, 0.3))
        return result is not None

    def get_foreground_app(self) -> Optional[str]:
        """获取前台应用包名"""
        output = self._execute_adb("shell dumpsys window | grep mCurrentFocus")
        if output:
            # 解析输出获取包名
            import re
            match = re.search(r'[a-zA-Z0-9_.]+/[a-zA-Z0-9_.]+', output)
            if match:
                return match.group(0)
        return None

    def is_screen_on(self) -> bool:
        """检查屏幕是否亮着"""
        output = self._execute_adb("shell dumpsys power | grep 'Display Power'")
        return output and "ON" in output if output else False

    def wake_up(self) -> bool:
        """唤醒屏幕"""
        if not self.is_screen_on():
            self.key_event(26)  # POWER键
            time.sleep(0.5)
        return True


# 使用示例
if __name__ == "__main__":
    # 初始化连接
    adb = LeidianADB(emulator_port=5555)

    if adb.connect():
        # 获取分辨率
        resolution = adb.get_screen_resolution()
        if resolution:
            print(f"屏幕分辨率: {resolution[0]}x{resolution[1]}")

        # 安全点击示例
        adb.safe_tap(500, 1000)

        # 自然滑动示例
        adb.safe_swipe(500, 1500, 500, 500, curve=True)

        # 截图
        adb.capture_screen("game_screen.png")

        # 获取当前应用
        app = adb.get_foreground_app()
        print(f"当前应用: {app}")

        # 断开连接
        adb.disconnect()