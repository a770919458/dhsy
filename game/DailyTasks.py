import asyncio
import logging
import os
import sys
import time
from datetime import datetime, date
from enum import Enum
from typing import Dict, Any, List, Optional

from wx.core import wx

from util import fileUtils
from util.AsyncADBHelper import EnhancedAsyncADBHelper
from util.AsyncSleepUtils import AsyncRandomSleeper
from util.EasyOCRTool import EasyOCRTool
from util.WindowsAsyncAirtestHelper import EnhancedWindowsAsyncAirtestHelper as wAsyncAirtestHelper
from util.ClipboardUtils import ClipboardManager
from util.adb_utils import LeidianADB

logger = logging.getLogger(__name__)
# 添加配置类
class GameConfig:
    """游戏配置"""

    # 任务超时时间（秒）
    TASK_TIMEOUTS = {
        'tianting_run': 1800,  # 30分钟
        'bang_pai_ren_wu': 1200,  # 20分钟
        'shi_men_ren_wu': 900,  # 15分钟
        'bao_tu_ren_wu': 600,  # 10分钟
        # ... 其他任务超时配置
    }

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 5

class TaskRole(Enum):
    """任务角色"""
    LEADER = "leader"      # 队长
    MEMBER = "member"      # 队员
    SOLO = "solo"         # 单人任务

def get_week_day():
    # 获取今天的日期
    today = date.today()

    # 获取星期几（0=周一，6=周日）
    weekday_num = today.weekday()
    print(f"今天是星期{['一', '二', '三', '四', '五', '六', '日'][weekday_num]}")

    # 或者获取英文星期名称
    weekday_name = today.strftime("%A")
    print(f"今天是{weekday_name}")
    return weekday_num


class TeamTaskCoordinator:
    """组队任务协调器"""

    def __init__(self):
        self.team_tasks: Dict[str, Dict] = {}  # team_id -> 任务信息
        self.team_members: Dict[str, List[int]] = {}  # team_id -> [hwnd列表]
        self.lock = asyncio.Lock()
        self.team_events: Dict[str, asyncio.Event] = {}  # 队伍事件

    async def create_team(self, task_name: str, leader_hwnd: int, member_hwnds: List[int]) -> str:
        """创建队伍"""
        team_id = f"{task_name}_{leader_hwnd}_{int(time.time())}"

        async with self.lock:
            self.team_tasks[team_id] = {
                'task_name': task_name,
                'leader': leader_hwnd,
                'members': member_hwnds,
                'status': 'forming',
                'created_at': datetime.now()
            }
            self.team_members[team_id] = [leader_hwnd] + member_hwnds
            self.team_events[team_id] = asyncio.Event()

        print(f"创建队伍 {team_id}: 队长={leader_hwnd}, 队员={member_hwnds}")
        return team_id

    async def wait_for_team_ready(self, team_id: str, timeout: int = 60) -> bool:
        """等待队伍准备就绪"""
        try:
            await asyncio.wait_for(self.team_events[team_id].wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            print(f"队伍 {team_id} 准备超时")
            return False

    async def set_team_ready(self, team_id: str):
        """设置队伍准备就绪"""
        async with self.lock:
            if team_id in self.team_tasks:
                self.team_tasks[team_id]['status'] = 'ready'
                self.team_events[team_id].set()
                print(f"队伍 {team_id} 准备就绪")

    async def disband_team(self, team_id: str):
        """解散队伍"""
        async with self.lock:
            if team_id in self.team_tasks:
                del self.team_tasks[team_id]
                del self.team_members[team_id]
                if team_id in self.team_events:
                    del self.team_events[team_id]
                print(f"队伍 {team_id} 已解散")

    def get_team_role(self, team_id: str, hwnd: int) -> TaskRole:
        """获取窗口在队伍中的角色"""
        if team_id not in self.team_tasks:
            return TaskRole.SOLO

        team_info = self.team_tasks[team_id]
        if hwnd == team_info['leader']:
            return TaskRole.LEADER
        elif hwnd in team_info['members']:
            return TaskRole.MEMBER
        else:
            return TaskRole.SOLO

    def get_team_members(self, team_id: str) -> List[int]:
        """获取队伍成员列表"""
        return self.team_members.get(team_id, [])





class WindowTaskExecutor:
    """单个窗口任务执行器 - 支持组队模式"""

    def __init__(self, team_coordinator: TeamTaskCoordinator, window_info: dict):

        self.team_coordinator = team_coordinator
        self.window_info = window_info
        self.hwnd = window_info['hwnd']
        self.helper = wAsyncAirtestHelper(window_handle=window_info['hwnd'], use_thread_pool=False)
        self.is_running = False
        self.current_team_id: Optional[str] = None
        self.clipboard_manager = ClipboardManager()  # 添加剪切板管理器
        self.is_adb = False
        self.sleeper = AsyncRandomSleeper()
        self.ocr_tool = EasyOCRTool()
        self.team_coordinator = team_coordinator
        if '雷电模拟器' in window_info['title']:
            self.is_adb = True
            port = self.window_info['port']
            self.adb_helper = EnhancedAsyncADBHelper(emulator_port=port)
            # 连接adb
            self.adb_helper.connect_sync()
        # 设置文件路径
        self.get_images_path()

    def get_images_path(self):
            """设置项目路径"""
            # 获取脚本所在目录 (dhsy/scripts/)
            self.script_dir = os.path.dirname(os.path.abspath(__file__))
            # 获取项目根目录 (dhsy/)
            self.project_root = os.path.dirname(self.script_dir)
            # 图片目录 (dhsy/images/)
            self.images_dir = os.path.join(self.project_root, "images")

            # 设置工作目录到项目根目录
            os.chdir(self.project_root)
            # 添加项目根目录到Python路径
            sys.path.insert(0, self.project_root)

            print(f"📁 项目根目录: {self.project_root}")
            print(f"📁 脚本目录: {self.script_dir}")
            print(f"🖼️  图片目录: {self.images_dir}")
            print(f"💻 工作目录: {os.getcwd()}")

    async def execute_all_tasks(self):
        """执行该窗口的所有任务 - 支持组队模式"""
        if self.is_running:
            return {"status": "running", "hwnd": self.hwnd}

        self.is_running = True
        results = {}

        try:
            # 连接设备
            await self.helper.connect_to_window_async(self.hwnd)
            print(f"开始执行窗口 {self.hwnd} 的所有任务")

            # 获取任务执行顺序
            task_sequence = self._get_task_sequence()

            # 串行执行每个任务
            for task_name, task_func, task_config in task_sequence:
                if not self.is_running:
                    break

                print(f"窗口 {self.hwnd} 开始执行: {task_name}")
                start_time = datetime.now()

                try:
                    # 执行任务（支持组队模式）
                    result = await self._execute_single_task(
                        task_name, task_func, task_config
                    )

                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()

                    results[task_name] = {
                        'status': 'success',
                        'duration': duration,
                        'role': result.get('role', 'solo'),
                        'team_id': result.get('team_id'),
                        'start_time': start_time.strftime('%H:%M:%S'),
                        'end_time': end_time.strftime('%H:%M:%S')
                    }
                    print(f"窗口 {self.hwnd} 任务 {task_name} 完成, 耗时: {duration:.1f}秒")

                except Exception as e:
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    logger.error(e, exc_info=True)
                    results[task_name] = {
                        'status': 'failed',
                        'error': str(e),
                        'duration': duration,
                        'start_time': start_time.strftime('%H:%M:%S'),
                        'end_time': end_time.strftime('%H:%M:%S')
                    }
                    print(f"窗口 {self.hwnd} 任务 {task_name} 失败: {e}")

            return {
                "status": "success",
                "hwnd": self.hwnd,
                "task_results": results,
                "completed_at": datetime.now().strftime('%H:%M:%S')
            }

        except Exception as e:
            return {
                "status": "failed",
                "hwnd": self.hwnd,
                "error": str(e),
                "completed_at": datetime.now().strftime('%H:%M:%S')
            }
        finally:
            self.is_running = False
            # 清理队伍信息
            if self.current_team_id:
                await self.team_coordinator.disband_team(self.current_team_id)

    def _get_task_sequence(self) -> List[tuple]:
        """获取任务执行顺序和配置"""
        # 单人任务配置
        solo_tasks = [
            # ('获取用户信息', self.get_user_info, {'is_team_task': False}),
            ('帮派任务', self.bang_pai_ren_wu, {'is_team_task': False}),
            # ('师门任务', self.shi_men_ren_wu, {'is_team_task': False}),
            # ('宝图任务', self.bao_tu_ren_wu, {'is_team_task': False}),
        ]

        # 组队任务配置
        team_tasks = [
            # ('三界妖王', self.san_jie_yao_wang, {'is_team_task': True, 'team_size': 5}),
            # ('野外封妖', self.ye_wai_feng_yao, {'is_team_task': True, 'team_size': 5}),
            # ('天庭降妖', self.tianting_run, {'is_team_task': True, 'team_size': 5}),
        ]

        # 周常任务
        week_day_num = get_week_day()
        weekly_tasks = []

        # if week_day_num == 0:  # 周一
        #     weekly_tasks.append(('天降灵猴', self.ling_hou, {'is_team_task': False}))
        # elif week_day_num == 1:  # 周二
        #     weekly_tasks.append(('水陆大会', self.shui_lu_da_hui, {'is_team_task': True, 'team_size': 5}))
        # elif week_day_num == 5:  # 周六
        #     weekly_tasks.append(('情花任务', self.qing_hua, {'is_team_task': False}))
        #     weekly_tasks.append(('跑环任务', self.pao_huan, {'is_team_task': False}))

        return solo_tasks + team_tasks + weekly_tasks

    async def _execute_single_task(self, task_name: str, task_func, task_config: dict):
        """执行单个任务 - 支持组队模式"""
        # 判断是否是组队任务
        if task_config.get('is_team_task', False):
            return await self._execute_team_task(task_name, task_func, task_config)
        else:
            # 单人任务
            return await self._execute_solo_task(task_func)

    async def _execute_team_task(self, task_name: str, task_func, task_config: dict):
        """执行组队任务"""
        # 这里需要获取队友窗口信息（从全局配置或其他方式）
        teammate_hwnds = self._get_teammates_for_task(task_name, task_config.get('team_size', 5))

        if not teammate_hwnds:
            # 没有队友，执行单人模式
            print(f"窗口 {self.hwnd} 执行 {task_name} 单人模式")
            return await self._execute_solo_task(task_func)

        # 创建队伍
        team_id = await self.team_coordinator.create_team(task_name, self.hwnd, teammate_hwnds)
        self.current_team_id = team_id

        # 获取角色
        role = self.team_coordinator.get_team_role(team_id, self.hwnd)

        if role == TaskRole.LEADER:
            print(f"窗口 {self.hwnd} 作为队长执行 {task_name}")
            result = await task_func(role, team_id)
        elif role == TaskRole.MEMBER:
            print(f"窗口 {self.hwnd} 作为队员执行 {task_name}")
            result = await task_func(role, team_id)
        else:
            result = await self._execute_solo_task(task_func)

        result['role'] = role.value
        result['team_id'] = team_id
        return result

    async def _execute_solo_task(self, task_func):
        """执行单人任务"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: task_func(self.hwnd)
        )
        result['role'] = 'solo'
        logger.info(f"{task_func.__name__} result: {result}")
        return result

    def _get_teammates_for_task(self, task_name: str, team_size: int) -> List[int]:
        """获取队友窗口（这里需要你根据实际情况实现）"""
        # 示例：从配置或界面选择中获取队友
        # 返回除自己外的队友列表
        all_windows = self.window_info.get('available_windows', [])
        teammates = [hwnd for hwnd in all_windows if hwnd != self.hwnd]

        # 限制队伍大小
        return teammates[:team_size - 1] if teammates else []

    # ========== 组队任务实现 ==========

    def tianting_run(self, hwnd: int, role: TaskRole, team_id: Optional[str] = None):
        """天庭降妖 - 支持组队模式"""
        import time

        print(f"窗口 {hwnd} 开始执行天庭降妖，角色: {role.value}")
        start_time = time.time()

        try:
            if role == TaskRole.LEADER:
                result = self._tianting_leader(hwnd, team_id)
            elif role == TaskRole.MEMBER:
                result = self._tianting_member(hwnd, team_id)

            duration = time.time() - start_time
            print(f"窗口 {hwnd} 天庭降妖完成，角色: {role.value}, 耗时: {duration:.1f}秒")
            return result

        except Exception as e:
            print(f"窗口 {hwnd} 天庭降妖执行失败: {e}")
            raise

    def _tianting_leader(self, hwnd: int, team_id: str) -> Dict[str, Any]:
        """队长操作流程"""
        # 1. 打开组队界面
        self.helper.wait_and_click_async(target="images/队伍.png")
        # sleep(2)

        # 2. 创建固定队伍
        # if exists(Template("create_team_btn.png")):
        #     touch((150, 250))
        #     sleep(1)

        # 3. 邀请队友（需要队友hwnd信息）
        teammates = self.team_coordinator.get_team_members(team_id)
        for i, teammate_hwnd in enumerate(teammates):
            # 这里需要根据队友信息进行邀请
            # touch((200 + i*50, 300))  # 点击邀请按钮
            print(f"队长 {hwnd} 邀请队友 {teammate_hwnd}")
            time.sleep(1)

        # 4. 等待队友准备
        # if exists(Template("all_ready.png")):
        #     touch((300, 400))  # 点击开始任务
        #     sleep(2)

        # 5. 执行任务
        # self._execute_combat_auto(device, "天庭降妖")

        # 模拟执行时间
        time.sleep(10)

        return {"combat_count": 10, "reward": "经验*10000"}

    def _tianting_member(self, hwnd: int, team_id: str) -> Dict[str, Any]:
        """队员操作流程"""
        from airtest.core.api import touch, exists, sleep, wait

        # 1. 等待队长邀请
        # if exists(Template("team_invite.png"), timeout=30):
        #     touch((250, 300))  # 点击接受
        #     sleep(2)

        # 2. 点击准备
        # if exists(Template("ready_btn.png")):
        #     touch((280, 350))
        #     sleep(1)

        # 3. 等待进入战斗
        # wait(Template("combat_start.png"), timeout=60)

        # 4. 设置自动战斗
        # self._setup_auto_combat(device)

        # 模拟执行时间
        sleep(10)

        return {"combat_count": 10, "reward": "经验*8000"}

    def _execute_combat_auto(self, task_name: str):
        """执行自动战斗流程（队长用）"""
        from airtest.core.api import touch, exists, sleep, wait

        combat_count = 0
        max_combats = 10  # 最大战斗次数

        while combat_count < max_combats:
            # 1. 寻找怪物
            # if exists(Template("monster_icon.png")):
            #     touch((300, 400))  # 点击怪物
            #     sleep(3)

            # 2. 进入战斗后设置自动
            # if exists(Template("combat_start.png")):
            #     self._setup_auto_combat(device)

            # 3. 等待战斗结束
            # wait(Template("combat_end.png"), timeout=180)
            # sleep(2)

            combat_count += 1
            print(f"完成第 {combat_count} 场战斗")

            # 检查任务是否完成
            # if exists(Template("task_complete.png")):
            #     break

            sleep(2)  # 模拟战斗间隔

    def _setup_auto_combat(self):
        """设置自动战斗"""
        from airtest.core.api import touch, exists, sleep

        # 1. 选择技能
        # touch((500, 600))  # 点击技能1
        # sleep(1)

        # 2. 开启自动
        # if exists(Template("auto_btn.png")):
        #     touch((600, 700))  # 点击自动按钮
        #     sleep(1)

        print("已设置自动战斗")

    def get_user_info(self, hwnd: int):
        """获取窗口用户信息"""
        async def get_info():
            title = self.window_info.get('title')
            if '雷电模拟器' in title:
                # self.adb_helper
                pass
            else:
                pass
                # 安全获取用户信息
            #     user_info = await self.helper.find_area_text((0,0,700,50))
            #     logger.info(f"user_info:{user_info}")
            #
            # return {"user_name": user_info, "user_number": user_info}

        return asyncio.run(get_info())


    # 其他组队任务的类似实现
    def san_jie_yao_wang(self, hwnd: int, role: TaskRole, team_id: Optional[str] = None):
        """三界妖王 - 组队模式"""
        from airtest.core.api import sleep
        import time

        print(f"窗口 {hwnd} 开始执行三界妖王，角色: {role.value}")
        start_time = time.time()

        if role == TaskRole.LEADER:
            # 队长逻辑
            sleep(8)
            result = {"combat_count": 3, "reward": "妖王宝箱*1"}
        elif role == TaskRole.MEMBER:
            # 队员逻辑
            sleep(8)
            result = {"combat_count": 3, "reward": "妖王宝箱*1"}
        else:
            # 单人逻辑
            sleep(12)
            result = {"combat_count": 1, "reward": "小妖宝箱*1"}

        duration = time.time() - start_time
        print(f"窗口 {hwnd} 三界妖王完成，角色: {role.value}, 耗时: {duration:.1f}秒")
        return result

    def ye_wai_feng_yao(self, hwnd: int, role: TaskRole, team_id: Optional[str] = None):
        """野外封妖 - 组队模式"""
        from airtest.core.api import sleep
        import time

        print(f"窗口 {hwnd} 开始执行野外封妖，角色: {role.value}")
        start_time = time.time()

        if role == TaskRole.LEADER:
            sleep(6)
            result = {"combat_count": 5, "reward": "封妖积分*50"}
        elif role == TaskRole.MEMBER:
            sleep(6)
            result = {"combat_count": 5, "reward": "封妖积分*40"}
        else:
            sleep(10)
            result = {"combat_count": 2, "reward": "封妖积分*20"}

        duration = time.time() - start_time
        print(f"窗口 {hwnd} 野外封妖完成，角色: {role.value}, 耗时: {duration:.1f}秒")
        return result
    def shi_men_ren_wu(self, hwnd: int):
        """师门任务"""
        from airtest.core.api import sleep
        sleep(2)
        print(f"窗口 {hwnd} 师门任务完成")

    def bang_pai_ren_wu(self, hwnd: int):
        """帮派任务 - 同步执行"""
        if self.is_adb:
            async def _bangpai():
                huo_dong_bool = await self.adb_helper.touch_async(target=f"{os.path.join(self.images_dir, "huo_dong.png")}")
                if huo_dong_bool:
                    logger.info("点击活动按钮成功")
                # pos = self.ocr_tool.feature_match(f"{os.path.join(self.images_dir, "huo_dong.png")}", file, min_matches=1)[0]
                # center_pos = pos['center']
                # logger.info(f"帮派任务，查找活动按钮:{center_pos}")
                # # 删除临时文件
                # fileUtils.delete_image_basic(file)
                # self.adb_helper.safe_tap(center_pos[0], center_pos[1])
                # result = await self.sleeper.sleep_random(1.0, 4.0)  # 2-5秒延迟
                # if not result.success:
                #     print(f"延迟异常: {result.error}")
                #     # 可以添加重试逻辑
                # stats = self.sleeper.get_stats()
                # print(f"已延迟 {stats['total_sleeps']} 次，累计 {stats['total_sleep_time']:.1f}秒")
                # # 寻找帮派任务
                # find_btn = False
                # while not find_btn:
                #     file = self.adb_helper.capture_screen()
                #     # pos = self.ocr_tool.search_text(file, "帮派任务")
                #     pos = self.ocr_tool.feature_match(f"{os.path.join(self.images_dir, "bang_pai_ren_wu.png")}", file, match_ratio=0.95, min_matches=1)[0]
                #     if pos['bbox']:
                #         renwu_pos = self.ocr_tool.feature_match_in_region(f"{os.path.join(self.images_dir, "bang_pai_ren_wu.png")}",
                #                                               file, min_matches=1, draw_matches=False)[0]
                #         self.adb_helper.safe_tap(renwu_pos['center'][0], renwu_pos['center'][1])
                #         find_btn = True
                #     else:
                #         self.adb_helper.safe_swipe(self.window_info['left'] * 0.5, self.window_info['bottom'] / 0.7,
                #                                    self.window_info['left'] * 0.5, self.window_info['bottom'] / 0.3)
                #     result = await self.sleeper.sleep_random(1.0, 4.0)  # 2-5秒延迟
                #     if not result.success:
                #         print(f"延迟异常: {result.error}")
                #         # 可以添加重试逻辑
                #     stats = self.sleeper.get_stats()
                #     print(f"已延迟 {stats['total_sleeps']} 次，累计 {stats['total_sleep_time']:.1f}秒")
                #     fileUtils.delete_image_basic(file)

        asyncio.run(_bangpai())
        print(f"窗口 {hwnd} 开始执行帮派任务")
        start_time = time.time()
        return {"stats": start_time}

        try:
            # 具体的帮派任务逻辑
            # ...
            time.sleep(3)  # 模拟执行时间

            duration = time.time() - start_time
            print(f"窗口 {hwnd} 帮派任务完成，耗时: {duration:.1f}秒")

        except Exception as e:
            print(f"窗口 {hwnd} 帮派任务执行失败: {e}")
            raise

    def bao_tu_ren_wu(self, hwnd: int):
        """宝图任务"""
        from airtest.core.api import sleep
        sleep(2)
        print(f"窗口 {hwnd} 宝图任务完成")

    def ling_hou(self, hwnd: int):
        """天降灵猴"""
        from airtest.core.api import sleep
        sleep(4)
        print(f"窗口 {hwnd} 天降灵猴完成")

    def shui_lu_da_hui(self, hwnd: int):
        """水陆大会"""
        from airtest.core.api import sleep
        sleep(5)
        print(f"窗口 {hwnd} 水陆大会完成")

    def qing_hua(self, hwnd: int):
        """情花任务"""
        from airtest.core.api import sleep
        sleep(3)
        print(f"窗口 {hwnd} 情花任务完成")

    def pao_huan(self, hwnd: int):
        """跑环任务"""
        from airtest.core.api import sleep
        sleep(10)
        print(f"窗口 {hwnd} 跑环任务完成")

class DailyTasks:
    """主任务管理器 - 支持组队协调"""

    def __init__(self):
        self.team_coordinator = TeamTaskCoordinator()
        self.is_running = False
        self.window_executors: Dict[int, WindowTaskExecutor] = {}

    async def start_task(self, selected_windows):
        """启动任务 - 支持组队协调"""
        if not selected_windows:
            wx.MessageBox("请先选择要启动的窗口", "提示", wx.OK | wx.ICON_INFORMATION)
            return

        if self.is_running:
            wx.MessageBox("任务正在执行中，请等待完成", "提示", wx.OK | wx.ICON_INFORMATION)
            return

        self.is_running = True

        try:
            # 为每个窗口创建执行器
            tasks = []
            for window_info in selected_windows:
                window_info['available_windows'] = [w['hwnd'] for w in selected_windows]  # 传递所有窗口信息

                # 创建窗口任务执行器
                executor = WindowTaskExecutor(
                    self.team_coordinator,
                    window_info
                )
                self.window_executors[window_info['hwnd']] = executor

                # 提交任务
                task = asyncio.create_task(executor.execute_all_tasks())
                tasks.append(task)

            # 等待所有窗口任务完成
            await asyncio.gather(*tasks, return_exceptions=True)

            # 收集并显示结果
            # results = self.task_manager.get_results()
            # self._show_results(results)

        except Exception as e:
            wx.MessageBox(f"任务执行失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
            logger.error(f"任务执行失败: {e}", exc_info=True)
        finally:
            self.is_running = False

    def stop_tasks(self):
        """停止所有任务"""
        self.is_running = False
        for executor in self.window_executors.values():
            executor.is_running = False
        print("所有任务停止信号已发送")

    def _show_results(self, results: Dict[str, Any]):
        """显示任务结果"""
        success_windows = []
        failed_windows = []

        for task_id, result in results.items():
            if result.get('status') == 'success':
                success_windows.append(result.get('hwnd', '未知'))
            else:
                failed_windows.append(result.get('hwnd', '未知'))

        message = f"任务执行完成！\n\n成功窗口: {len(success_windows)}个\n"
        if success_windows:
            message += f"成功窗口ID: {success_windows}\n\n"

        message += f"失败窗口: {len(failed_windows)}个"
        if failed_windows:
            message += f"\n失败窗口ID: {failed_windows}"

        wx.MessageBox(message, "任务完成", wx.OK | wx.ICON_INFORMATION)


class GameAutomationManager:
    """游戏自动化管理器 - 简化版本，主要用于窗口间并发"""

    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.task_results: Dict[str, Any] = {}
        self.task_counter = 0

    async def submit_task(self, task_func, *args, task_name: str = None, **kwargs) -> str:
        """提交任务 - 带并发控制"""
        self.task_counter += 1
        task_id = task_name or f"task_{self.task_counter}"

        # 创建任务
        task = asyncio.create_task(
            self._run_task_with_limit(task_id, task_func, *args, **kwargs)
        )

        self.active_tasks[task_id] = task
        task.add_done_callback(lambda t: self._task_done_callback(task_id, t))

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 提交任务: {task_id}")
        return task_id

    async def _run_task_with_limit(self, task_id: str, task_func, *args, **kwargs):
        """带并发限制的任务执行"""
        async with self.semaphore:
            try:
                result = await task_func(*args, **kwargs)
                return result
            except Exception as e:
                print(f"任务 {task_id} 执行失败: {e}")
                raise

    def _task_done_callback(self, task_id: str, future: asyncio.Future):
        """任务完成回调"""
        try:
            result = future.result()
            self.task_results[task_id] = result
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务完成: {task_id}")
        except Exception as e:
            self.task_results[task_id] = {
                'status': 'failed',
                'error': str(e),
                'completed_at': datetime.now().strftime('%H:%M:%S')
            }
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务失败: {task_id}, 错误: {e}")

        if task_id in self.active_tasks:
            del self.active_tasks[task_id]

    async def wait_all_complete(self, timeout: int = None):
        """等待所有任务完成"""
        if not self.active_tasks:
            return

        print(f"等待 {len(self.active_tasks)} 个任务完成...")
        try:
            await asyncio.wait_for(
                asyncio.gather(*self.active_tasks.values(), return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            print(f"等待超时，还有 {len(self.active_tasks)} 个任务未完成")

    def get_results(self) -> Dict[str, Any]:
        """获取所有任务结果"""
        return self.task_results.copy()

    def shutdown(self):
        """关闭管理器"""
        # 取消所有未完成的任务
        for task in self.active_tasks.values():
            if not task.done():
                task.cancel()
        print("任务管理器已关闭")



