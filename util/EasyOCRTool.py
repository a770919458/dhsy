import os
import re
from typing import List, Any, Optional, Tuple, Dict, Union
import cv2
import numpy as np
from easyocr import Reader
from PIL import Image
import logging


class EasyOCRTool:
    """
    功能完整的OCR工具类，支持文字识别、文字搜索、区域识别等多种功能（优化特征匹配）
    """

    def __init__(self, lang: Union[str, List[str]] = 'ch_sim', gpu: bool = False,
                 logger: Optional[logging.Logger] = None):
        """
        初始化 EasyOCR 工具类

        Args:
            lang: 识别语言，可以是字符串或列表，例如 'ch_sim'（简体中文）、'en'（英文）
            gpu: 是否使用GPU加速
            logger: 日志记录器，如果为None则创建默认logger
        """
        if isinstance(lang, str):
            lang_list = [lang]
        else:
            lang_list = lang

        self.reader = Reader(lang_list, gpu=gpu)
        self.logger = logger or self._setup_default_logger()

    def _setup_default_logger(self) -> logging.Logger:
        """设置默认日志记录器"""
        logger = logging.getLogger('EasyOCRTool')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

    def load_image(self, image_input: Union[str, np.ndarray, Image.Image]) -> np.ndarray:
        """
        加载图像并转换为numpy数组格式（保持原有逻辑）
        """
        try:
            if isinstance(image_input, str):
                if not os.path.isabs(image_input):
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    possible_paths = [
                        image_input,
                        os.path.join(project_root, image_input),
                        os.path.join(project_root, "images", image_input),
                        os.path.join(project_root, "screenshots", image_input),
                    ]
                    cwd = os.getcwd()
                    possible_paths.extend([
                        os.path.join(cwd, image_input),
                        os.path.join(cwd, "images", image_input),
                        os.path.join(cwd, "screenshots", image_input),
                    ])
                    for path in possible_paths:
                        if os.path.exists(path):
                            image_input = path
                            break

                img = cv2.imread(image_input)
                if img is None:
                    try:
                        pil_img = Image.open(image_input)
                        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
                    except Exception as pil_error:
                        raise ValueError(f"无法加载图像: {image_input} (cv2和PIL都失败)")

                if img is None:
                    raise ValueError(f"无法加载图像: {image_input}")
                return img
            elif isinstance(image_input, Image.Image):
                img = cv2.cvtColor(np.array(image_input), cv2.COLOR_RGB2BGR)
                return img
            elif isinstance(image_input, np.ndarray):
                return image_input.copy()
            else:
                raise ValueError(f"不支持的图像格式: {type(image_input)}")

        except Exception as e:
            self.logger.error(f"加载图像失败: {e}")
            if isinstance(image_input, str):
                self.logger.error(f"图像路径: {image_input}")
                self.logger.error(f"文件存在: {os.path.exists(image_input)}")
                if os.path.exists(image_input):
                    self.logger.error(f"文件大小: {os.path.getsize(image_input)} bytes")
            raise

    def _image_preprocess(self, img: np.ndarray, enhance_contrast: bool = True, denoise: bool = True) -> np.ndarray:
        """
        图像预处理：增强对比度、降噪，突出目标特征
        """
        # 转换为灰度图
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 降噪（高斯模糊+双边滤波，保留边缘）
        if denoise:
            gray = cv2.GaussianBlur(gray, (3, 3), 0.5)
            gray = cv2.bilateralFilter(gray, 5, 75, 75)

        # 对比度增强（CLAHE自适应直方图均衡）
        if enhance_contrast:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

        return gray

    def feature_match(self,
                      image1,
                      image2,
                      method: str = 'akaze',  # 优先使用AKAZE（鲁棒性更强）
                      match_ratio: float = 0.7,  # 更严格的比例阈值
                      min_matches: int = 8,  # 适度提高最小匹配数
                      draw_matches: bool = True,
                      enhance_contrast: bool = True,
                      denoise: bool = True,
                      use_flann_matcher: bool = False,  # 大数据量时使用FLANN加速
                      nms_overlap_threshold: float = 0.5,  # 非极大值抑制阈值
                      scale_ratios: List[float] = None) -> tuple:
        """
        优化后的特征匹配函数：提升抗干扰能力，减少背景影响

        新增参数：
            enhance_contrast: 是否增强图像对比度
            denoise: 是否对图像降噪
            use_flann_matcher: 是否使用FLANN匹配器（适合大数据量）
            nms_overlap_threshold: 非极大值抑制阈值（去除重叠匹配）
            scale_ratios: 多尺度匹配的缩放比例列表，如[0.8, 1.0, 1.2]
        """
        try:
            # 加载图像
            img1 = self.load_image(image1)
            img2 = self.load_image(image2)

            # 多尺度匹配初始化
            all_matches = []
            scale_ratios = scale_ratios or [1.0]  # 默认仅原尺度

            for scale in scale_ratios:
                # 缩放模板图像（image1）
                if scale != 1.0:
                    h, w = img1.shape[:2]
                    scaled_img1 = cv2.resize(img1, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
                else:
                    scaled_img1 = img1.copy()

                # 图像预处理
                gray1 = self._image_preprocess(scaled_img1, enhance_contrast, denoise)
                gray2 = self._image_preprocess(img2, enhance_contrast, denoise)

                # 选择鲁棒性更强的特征检测器
                detector = self._get_feature_detector(method)
                if detector is None:
                    self.logger.warning("特征检测器初始化失败，回退到AKAZE")
                    detector = cv2.AKAZE_create()

                # 检测关键点和描述符（增加参数提升特征点质量）
                kp1, des1 = detector.detectAndCompute(gray1, None)
                kp2, des2 = detector.detectAndCompute(gray2, None)

                if des1 is None or des2 is None or len(kp1) < min_matches or len(kp2) < min_matches:
                    self.logger.warning(f"尺度{scale}: 特征点数量不足，跳过")
                    continue

                # 选择匹配器（FLANN适合大数据量，BFMatcher适合小数据量）
                matcher = self._get_matcher(method, use_flann_matcher, len(des1), len(des2))

                # KNN匹配
                if use_flann_matcher:
                    matches = matcher.knnMatch(des1, des2, k=2)
                else:
                    matches = matcher.knnMatch(des1, des2, k=2)

                # 严格筛选匹配点（比例阈值+距离阈值）
                good_matches = []
                for m, n in matches:
                    if m.distance < match_ratio * n.distance and m.distance < 30:  # 增加绝对距离阈值
                        good_matches.append(m)

                self.logger.info(f"尺度{scale}: 原始匹配{len(matches)}，筛选后{len(good_matches)}")

                if len(good_matches) < min_matches:
                    continue

                # 单应性矩阵校验（更严格的RANSAC阈值）
                src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

                # 计算单应性矩阵（RANSAC阈值从5.0降至3.0，更严格）
                M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 3.0)
                if M is None:
                    continue

                # 过滤错误的单应性矩阵（检查矩阵合理性）
                if not self._validate_homography_matrix(M):
                    continue

                # 计算匹配区域
                h, w = gray1.shape
                pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
                dst = cv2.perspectiveTransform(pts, M)

                # 计算边界框和置信度
                x_coords = dst[:, 0, 0]
                y_coords = dst[:, 0, 1]
                x_min, x_max = int(np.min(x_coords)), int(np.max(x_coords))
                y_min, y_max = int(np.min(y_coords)), int(np.max(y_coords))
                center_x = (x_min + x_max) // 2
                center_y = (y_min + y_max) // 2

                # 计算匹配质量分（匹配数/特征点数 + 单应性矩阵稳定性）
                confidence = (len(good_matches) / max(len(kp1), len(kp2))) * self._get_homography_stability(M)

                all_matches.append({
                    'match_success': True,
                    'match_count': len(good_matches),
                    'total_matches': len(matches),
                    'center': (center_x, center_y),
                    'bbox': (x_min, y_min, x_max, y_max),
                    'confidence': confidence,
                    'scale': scale,
                    'homography_matrix': M,
                    'dst_points': dst
                })

        except Exception as e:
            self.logger.error(f"特征匹配失败: {e}", exc_info=True)
            return None, None, None

        # 非极大值抑制，去除重叠的匹配结果
        if all_matches:
            filtered_matches = self._non_max_suppression(all_matches, nms_overlap_threshold)
            # 选择置信度最高的匹配
            best_match = max(filtered_matches, key=lambda x: x['confidence'])
            self.logger.info(f"最终匹配结果: 置信度{best_match['confidence']:.3f}, 匹配数{best_match['match_count']}")
        else:
            self.logger.warning("未找到有效匹配")
            return None, None, None

        # 绘制匹配结果
        img_matches = None
        img2_with_bbox = None
        if draw_matches:
            # 绘制匹配点
            img_matches = cv2.drawMatches(
                self.load_image(image1),
                self._get_feature_detector(method).detect(self._image_preprocess(self.load_image(image1))),
                img2,
                self._get_feature_detector(method).detect(self._image_preprocess(img2)),
                [m for m in good_matches[:20]],  # 仅绘制前20个匹配点
                None,
                flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
            )

            # 绘制匹配区域
            img2_with_bbox = img2.copy()
            cv2.polylines(img2_with_bbox, [np.int32(best_match['dst_points'])], True, (0, 255, 0), 3)
            cv2.circle(img2_with_bbox, best_match['center'], 5, (0, 0, 255), -1)
            cv2.putText(img2_with_bbox,
                        f"Matches: {best_match['match_count']} (Conf: {best_match['confidence']:.2f})",
                        (best_match['center'][0], best_match['center'][1] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # 保存结果
            if isinstance(image2, str):
                base_name = image2.rsplit('.', 1)[0]
                ext = image2.rsplit('.', 1)[1] if '.' in image2 else 'jpg'
                cv2.imwrite(f"{base_name}_optimized_match.{ext}", img2_with_bbox)

        return best_match, img_matches, img2_with_bbox

    def _get_feature_detector(self, method: str) -> cv2.Feature2D:
        """
        获取特征检测器（增加参数调优，提升特征鲁棒性）
        """
        method = method.lower()
        try:
            if method == 'sift':
                return cv2.SIFT_create(
                    nfeatures=1000,  # 增加特征点数量
                    contrastThreshold=0.02,  # 降低对比度阈值，检测更多特征
                    edgeThreshold=10  # 降低边缘阈值
                )
            elif method == 'surf':
                return cv2.xfeatures2d.SURF_create(hessianThreshold=100)
            elif method == 'akaze':
                return cv2.AKAZE_create(
                    descriptor_type=cv2.AKAZE_DESCRIPTOR_MLDB,
                    descriptor_size=0,
                    descriptor_channels=3,
                    threshold=0.001  # 降低阈值，检测更多特征
                )
            else:  # ORB
                return cv2.ORB_create(
                    nfeatures=2000,  # 增加特征点数量
                    scaleFactor=1.2,
                    patchSize=31,
                    edgeThreshold=31
                )
        except Exception as e:
            self.logger.warning(f"初始化{method}检测器失败: {e}")
            return None

    def _get_matcher(self, method: str, use_flann: bool, des1_len: int, des2_len: int) -> cv2.DescriptorMatcher:
        """
        获取匹配器：小数据量用BFMatcher（精准），大数据量用FLANN（快速）
        """
        if use_flann and des1_len > 1000 and des2_len > 1000:
            # FLANN匹配器（适合大数据量）
            FLANN_INDEX_KDTREE = 1
            index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
            search_params = dict(checks=50)
            return cv2.FlannBasedMatcher(index_params, search_params)
        else:
            # BFMatcher（精准，适合小数据量）
            if method in ['sift', 'surf']:
                return cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
            else:
                return cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    def _validate_homography_matrix(self, M: np.ndarray) -> bool:
        """
        验证单应性矩阵的合理性，过滤错误匹配
        """
        # 检查矩阵是否为3x3
        if M.shape != (3, 3):
            return False

        # 检查矩阵元素是否为有限值
        if not np.all(np.isfinite(M)):
            return False

        # 检查变换的尺度和旋转是否合理
        # 提取旋转和平移分量
        scale_x = np.sqrt(M[0, 0] ** 2 + M[1, 0] ** 2)
        scale_y = np.sqrt(M[0, 1] ** 2 + M[1, 1] ** 2)

        # 尺度变化应在合理范围内（0.5~2倍）
        if scale_x < 0.5 or scale_x > 2.0 or scale_y < 0.5 or scale_y > 2.0:
            self.logger.warning(f"单应性矩阵尺度异常: scale_x={scale_x}, scale_y={scale_y}")
            return False

        return True

    def _get_homography_stability(self, M: np.ndarray) -> float:
        """
        计算单应性矩阵的稳定性得分（0~1）
        """
        # 计算矩阵的条件数（越小越稳定）
        try:
            cond = np.linalg.cond(M[:2, :2])
            # 归一化到0~1
            return 1.0 / (1.0 + np.log10(max(1, cond)))
        except:
            return 0.5

    def _non_max_suppression(self, matches: List[Dict], overlap_threshold: float) -> List[Dict]:
        """
        非极大值抑制，去除重叠的匹配结果（原有逻辑保留并优化）
        """
        if not matches:
            return []

        # 按置信度排序
        matches_sorted = sorted(matches, key=lambda x: x['confidence'], reverse=True)
        filtered_matches = []

        while matches_sorted:
            best_match = matches_sorted.pop(0)
            filtered_matches.append(best_match)

            remaining_matches = []
            for match in matches_sorted:
                overlap = self._calculate_overlap(best_match['bbox'], match['bbox'])
                if overlap < overlap_threshold:
                    remaining_matches.append(match)

            matches_sorted = remaining_matches

        return filtered_matches

    def _calculate_overlap(self, bbox1: Tuple[int, int, int, int], bbox2: Tuple[int, int, int, int]) -> float:
        """
        计算两个边界框的重叠比例（原有逻辑）
        """
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2

        inter_x1 = max(x1_1, x1_2)
        inter_y1 = max(y1_1, y1_2)
        inter_x2 = min(x2_1, x2_2)
        inter_y2 = min(y2_1, y2_2)

        if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
            return 0.0

        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)

        min_area = min(area1, area2)
        return inter_area / min_area if min_area > 0 else 0.0

    # 保留原有其他方法（如recognize_text_in_region、search_text等）
    # ...（此处省略原有未修改的方法，保持类的完整性）


# 优化后的使用示例
if __name__ == "__main__":
    # 初始化OCR工具
    ocr_tool = EasyOCRTool(lang=['ch_sim', 'en'], gpu=False)

    # 优化后的特征匹配调用
    result, matches_img, bbox_img = ocr_tool.feature_match(
        image1="template.png",  # 模板图像（小目标）
        image2="background.jpg",  # 背景图像（含干扰）
        method="akaze",  # 优先使用AKAZE（抗干扰更强）
        match_ratio=0.7,  # 更严格的匹配比例
        min_matches=8,  # 适度提高最小匹配数
        enhance_contrast=True,  # 增强对比度
        denoise=True,  # 降噪
        scale_ratios=[0.8, 1.0, 1.2]  # 多尺度匹配
    )

    if result:
        print(f"匹配成功！中心坐标: {result['center']}, 置信度: {result['confidence']:.3f}")
    else:
        print("匹配失败，未找到有效特征点")