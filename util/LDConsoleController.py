import subprocess
from pathlib import Path
from typing import Optional


class LDConsoleController:
    """
    简单封装雷电 ldconsole 的 runapp 功能，只负责启动指定模拟器里的某个包。
    用法：
        1. 找到 ldconsole.exe 所在目录（例如 r"D:\leidian\LDPlayer9"），
           传给 LDConsoleController(ldconsole_dir).
        2. 通过 get_instances() 查看所有实例名称/编号。
        3. 调用 run_app("LDPlayer", "com.netease.dhxy") 即可启动大话西游。
    """

    def __init__(self, ldconsole_dir: str):
        self.ldconsole_path = Path(ldconsole_dir) / "ldconsole.exe"
        if not self.ldconsole_path.exists():
            raise FileNotFoundError(f"ldconsole.exe not found at {self.ldconsole_path}")

    def _run_ldconsole(self, args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
        cmd = [str(self.ldconsole_path)] + args
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def get_instances(self) -> list[str]:
        """
        返回所有实例名称，例如 ['LDPlayer', 'LDPlayer-1', 'LDPlayer-2'].
        """
        result = self._run_ldconsole(["list2"])
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "ldconsole list2 failed")

        names = []
        for line in result.stdout.splitlines():
            columns = [c.strip() for c in line.split(",") if c.strip()]
            # list2 输出格式：name,index,pid,state,adb,top_activity
            if columns:
                names.append(columns[0])
        return names

    def run_app(self, instance_name: str, package_name: str) -> bool:
        """
        直接让指定实例启动包名（无须 Activity），等价于 `ldconsole runapp --name <inst> --packagename <pkg>`
        """
        result = self._run_ldconsole([
            "runapp",
            "--name", instance_name,
            "--packagename", package_name,
        ])
        if result.returncode != 0:
            print(result.stderr or "ldconsole runapp failed")
            return False

        print(result.stdout.strip() or f"{instance_name} runapp {package_name} success")
        return True


if __name__ == "__main__":
    controller = LDConsoleController(r"D:\leidian\LDPlayer9")  # 替换为你的安装目录
    instances = controller.get_instances()
    print("模拟器实例：", instances)

    # 假设要在默认实例 LDPlayer 上启动大话西游
    controller.run_app("LDPlayer", "com.netease.dhxy")
