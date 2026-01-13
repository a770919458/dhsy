import cv2
import numpy as np
from typing import List, Tuple, Dict, Optional, Union
import time


class ImageRecognition:
    def __init__(self, lang: str = 'ch_sim'):
        """
        图像识别类，支持窗口大小变化的自适应识别

        Args:
            lang (str): OCR识别语言
        """
        from util.EasyOCRTool import EasyOCRTool
        self.ocr_tool = EasyOCRTool(lang)
        self.reference_size = None  # 参考窗口尺寸，用于坐标缩放
        self.template_cache = {}  # 模板缓存

    def set_reference_size(self, width: int, height: int):
        """
        设置参考窗口尺寸，用于后续坐标缩放

        Args:
            width: 参考窗口宽度
            height: 参考窗口高度
        """
        self.reference_size = (width, height)
        print(f"设置参考窗口尺寸: {width} x {height}")

    def scale_coordinates(self, bbox: Tuple[int, int, int, int],
                          current_size: Tuple[int, int]) -> Tuple[int, int, int, int]:
        """
        根据当前窗口尺寸缩放坐标

        Args:
            bbox: 原始坐标 (x1, y1, x2, y2)
            current_size: 当前窗口尺寸 (width, height)

        Returns:
            缩放后的坐标 (x1, y1, x2, y2)
        """
        if self.reference_size is None:
            return bbox

        ref_width, ref_height = self.reference_size
        curr_width, curr_height = current_size

        # 计算缩放比例
        scale_x = curr_width / ref_width
        scale_y = curr_height / ref_height

        x1, y1, x2, y2 = bbox

        # 应用缩放
        scaled_x1 = int(x1 * scale_x)
        scaled_y1 = int(y1 * scale_y)
        scaled_x2 = int(x2 * scale_x)
        scaled_y2 = int(y2 * scale_y)

        return (scaled_x1, scaled_y1, scaled_x2, scaled_y2)

    def find_text(self,
                  image: np.ndarray,
                  target_text: str,
                  confidence_threshold: float = 0.7,
                  current_window_size: Optional[Tuple[int, int]] = None) -> Dict[str, any]:
        """
        查找文本并返回位置信息，支持窗口大小变化

        Args:
            image: 输入图像
            target_text: 目标文本
            confidence_threshold: 置信度阈值
            current_window_size: 当前窗口尺寸 (width, height)

        Returns:
            包含位置和状态信息的字典
        """
        try:
            # 查找文本位置
            bbox = self.ocr_tool.find_text_position(image, target_text, confidence_threshold)

            if bbox is None:
                return {
                    'found': False,
                    'text': target_text,
                    'position': None,
                    'confidence': 0.0,
                    'message': f'未找到文本"{target_text}"'
                }

            # 如果需要缩放坐标
            scaled_bbox = bbox
            if current_window_size and self.reference_size:
                scaled_bbox = self.scale_coordinates(bbox, current_window_size)

            # 计算中心点
            x1, y1, x2, y2 = scaled_bbox
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            width = x2 - x1
            height = y2 - y1

            return {
                'found': True,
                'text': target_text,
                'position': scaled_bbox,
                'center': (center_x, center_y),
                'size': (width, height),
                'confidence': confidence_threshold,
                'original_bbox': bbox if scaled_bbox != bbox else None
            }

        except Exception as e:
            return {
                'found': False,
                'text': target_text,
                'position': None,
                'confidence': 0.0,
                'message': f'查找文本时出错: {str(e)}'
            }

    def find_and_click_text(self,
                            image: np.ndarray,
                            target_text: str,
                            confidence_threshold: float = 0.7,
                            current_window_size: Optional[Tuple[int, int]] = None,
                            click_offset: Tuple[int, int] = (0, 0)) -> bool:
        """
        查找文本并模拟点击（需要安装pyautogui）

        Args:
            image: 输入图像
            target_text: 目标文本
            confidence_threshold: 置信度阈值
            current_window_size: 当前窗口尺寸
            click_offset: 点击偏移量 (x, y)

        Returns:
            是否成功点击
        """
        try:
            import pyautogui
        except ImportError:
            print("请安装pyautogui: pip install pyautogui")
            return False

        result = self.find_text(image, target_text, confidence_threshold, current_window_size)

        if not result['found']:
            print(f"未找到文本'{target_text}'，无法点击")
            return False

        # 获取中心点坐标
        center_x, center_y = result['center']

        # 应用偏移
        click_x = center_x + click_offset[0]
        click_y = center_y + click_offset[1]

        # 模拟点击
        pyautogui.click(click_x, click_y)
        print(f"在位置 ({click_x}, {click_y}) 点击文本'{target_text}'")

        return True

    def find_multiple_texts(self,
                            image: np.ndarray,
                            target_texts: List[str],
                            confidence_threshold: float = 0.7,
                            current_window_size: Optional[Tuple[int, int]] = None) -> Dict[str, any]:
        """
        批量查找多个文本

        Args:
            image: 输入图像
            target_texts: 目标文本列表
            confidence_threshold: 置信度阈值
            current_window_size: 当前窗口尺寸

        Returns:
            包含所有查找结果的字典
        """
        results = {}

        for text in target_texts:
            results[text] = self.find_text(image, text, confidence_threshold, current_window_size)

        # 统计结果
        found_count = sum(1 for result in results.values() if result['found'])

        return {
            'all_results': results,
            'found_count': found_count,
            'total_count': len(target_texts),
            'success_rate': found_count / len(target_texts) if target_texts else 0
        }

    def wait_for_text(self,
                      image_provider,  # 图像提供函数，返回当前图像
                      target_text: str,
                      timeout: int = 30,
                      confidence_threshold: float = 0.7,
                      check_interval: float = 1.0,
                      current_window_size: Optional[Tuple[int, int]] = None) -> Dict[str, any]:
        """
        等待文本出现

        Args:
            image_provider: 返回当前图像的函数
            target_text: 目标文本
            timeout: 超时时间（秒）
            confidence_threshold: 置信度阈值
            check_interval: 检查间隔（秒）
            current_window_size: 当前窗口尺寸

        Returns:
            等待结果
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # 获取当前图像
                current_image = image_provider()
                if current_image is None:
                    continue

                # 查找文本
                result = self.find_text(current_image, target_text, confidence_threshold, current_window_size)

                if result['found']:
                    result['wait_time'] = time.time() - start_time
                    result['status'] = 'success'
                    return result

                time.sleep(check_interval)

            except Exception as e:
                print(f"等待文本时出错: {e}")
                time.sleep(check_interval)

        return {
            'found': False,
            'text': target_text,
            'position': None,
            'confidence': 0.0,
            'wait_time': timeout,
            'status': 'timeout',
            'message': f'等待文本"{target_text}"超时'
        }

    def extract_text_from_region(self,
                                 image: np.ndarray,
                                 region: Tuple[int, int, int, int],
                                 current_window_size: Optional[Tuple[int, int]] = None) -> List[Dict[str, any]]:
        """
        从指定区域提取文本

        Args:
            image: 输入图像
            region: 区域坐标 (x1, y1, x2, y2)
            current_window_size: 当前窗口尺寸

        Returns:
            提取的文本列表
        """
        try:
            # 如果需要缩放区域
            if current_window_size and self.reference_size:
                region = self.scale_coordinates(region, current_window_size)

            x1, y1, x2, y2 = region
            roi = image[y1:y2, x1:x2]

            # 进行OCR识别
            ocr_results = self.ocr_tool.recognize_text_from_image(roi)

            extracted_texts = []
            for line in ocr_results:
                for detection in line:
                    text, confidence, bbox = detection

                    # 将相对坐标转换为绝对坐标
                    rel_x1, rel_y1, rel_x2, rel_y2 = bbox
                    abs_x1 = x1 + rel_x1
                    abs_y1 = y1 + rel_y1
                    abs_x2 = x1 + rel_x2
                    abs_y2 = y1 + rel_y2

                    extracted_texts.append({
                        'text': text,
                        'confidence': confidence,
                        'position': (abs_x1, abs_y1, abs_x2, abs_y2),
                        'region': region
                    })

            return extracted_texts

        except Exception as e:
            print(f"提取区域文本时出错: {e}")
            return []

    def create_text_template(self,
                             image: np.ndarray,
                             template_name: str,
                             target_text: str,
                             confidence_threshold: float = 0.8) -> bool:
        """
        创建文本模板，用于快速匹配

        Args:
            image: 输入图像
            template_name: 模板名称
            target_text: 目标文本
            confidence_threshold: 置信度阈值

        Returns:
            是否成功创建模板
        """
        result = self.find_text(image, target_text, confidence_threshold)

        if not result['found']:
            print(f"未找到文本'{target_text}'，无法创建模板")
            return False

        self.template_cache[template_name] = {
            'text': target_text,
            'reference_position': result['position'],
            'reference_size': self.reference_size,
            'created_time': time.time()
        }

        print(f"成功创建文本模板 '{template_name}'")
        return True

    def find_text_by_template(self,
                              image: np.ndarray,
                              template_name: str,
                              current_window_size: Optional[Tuple[int, int]] = None) -> Dict[str, any]:
        """
        使用模板查找文本

        Args:
            image: 输入图像
            template_name: 模板名称
            current_window_size: 当前窗口尺寸

        Returns:
            查找结果
        """
        if template_name not in self.template_cache:
            return {
                'found': False,
                'message': f'模板"{template_name}"不存在'
            }

        template = self.template_cache[template_name]
        return self.find_text(image, template['text'], 0.7, current_window_size)


# 使用示例
def example_usage():
    # 初始化图像识别器
    recognizer = ImageRecognition('ch_sim')

    # 设置参考窗口尺寸（首次识别时的窗口尺寸）
    recognizer.set_reference_size(832, 698)

    # 示例1：查找单个文本
    def get_current_image():
        # 这里应该是获取当前窗口图像的代码
        # 例如：return recognizer.ocr_tool.capture_window_as_numpy(hwnd)
        return cv2.imread('current_screen.png')

    current_image = get_current_image()
    current_window_size = (1600, 900)  # 当前窗口可能已经改变大小

    # 查找文本
    result = recognizer.find_text(
        image=current_image,
        target_text="登录",
        current_window_size=current_window_size
    )

    if result['found']:
        print(f"找到文本'{result['text']}'，位置: {result['position']}")

        # 如果需要点击
        # recognizer.find_and_click_text(current_image, "登录", current_window_size=current_window_size)

    # 示例2：等待文本出现
    wait_result = recognizer.wait_for_text(
        image_provider=get_current_image,
        target_text="加载完成",
        timeout=30,
        current_window_size=current_window_size
    )

    # 示例3：批量查找
    texts_to_find = ["用户名", "密码", "登录", "注册"]
    batch_result = recognizer.find_multiple_texts(
        image=current_image,
        target_texts=texts_to_find,
        current_window_size=current_window_size
    )

    print(f"成功找到 {batch_result['found_count']}/{batch_result['total_count']} 个文本")


if __name__ == "__main__":
    example_usage()