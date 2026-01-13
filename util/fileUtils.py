import os


def delete_image_basic(file_path):
    """基本删除图片"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"成功删除: {file_path}")
            return True
        else:
            print(f"文件不存在: {file_path}")
            return False
    except Exception as e:
        print(f"删除失败: {e}")
        return False