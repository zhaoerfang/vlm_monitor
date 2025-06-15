import time
from .Camera import Camera
# 假设 Camera 类代码已经导入或在同一文件

def time_it(func, *args, **kwargs):
    """通用计时器函数，测量func执行耗时"""
    start = time.time()
    result = func(*args, **kwargs)
    end = time.time()
    print(f"调用 {func.__name__} 耗时: {end - start:.3f} 秒")
    return result

if __name__ == '__main__':
    # 创建摄像头实例，替换成你的摄像头IP、用户名、密码
    cam = Camera(ip='192.168.1.64', admin='admin', password='pw4hkcamera')

    # # 向左转，pan_speed为负数，持续3秒
    # print("摄像头向左转动3秒")
    # cam.pan_tilt_move(pan_speed=-50, tilt_speed=0, second=3)

    # # 停顿1秒
    # time.sleep(1)

    # # 向右转，pan_speed为正数，持续3秒
    # print("摄像头向右转动3秒")
    # cam.pan_tilt_move(pan_speed=50, tilt_speed=0, second=3)

    # # 最后确保停止旋转（pan_speed=0）
    # print("摄像头停止转动")
    # cam.pan_tilt_move(pan_speed=0, tilt_speed=0, second=1)
    cam.goto_preset_point(point_id=1)  # 假设预设点1是中心位置
