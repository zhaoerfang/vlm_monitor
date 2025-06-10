import cv2
import socket
import numpy as np  
import time 
import struct
  
def recvall(sock, count):  
    buf = b''  
    while count:  
        newbuf = sock.recv(count)  
        if not newbuf:  
            return None  
        buf += newbuf  
        count -= len(newbuf)  
    return buf  
  
# 创建一个新的socket对象  
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  

sock.connect(('172.20.10.4', 1234))  # 连接到服务器  
     
while True:  
    # 接收图像数据的长度  
    length_bytes = recvall(sock, 8)  
    
    if not length_bytes:
        print("server is not ready now, wait please !!!")
        # 关闭旧的socket  
        sock.close()  
          
        # 创建一个新的socket  
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  
        sock.connect(('127.0.0.1', 1234))  # 连接到服务器  
        # 等待一段时间然后再次尝试连接   
        time.sleep(2)
        continue
    # 解析为一个无符号长整数  
    length = struct.unpack('<Q', length_bytes)[0]  
    stringData = recvall(sock, int(length))  
    data = np.frombuffer(stringData, dtype='uint8')  
  
    # 将数据解码为图像  
    img = cv2.imdecode(data, 1) 
    h, w = img.shape[:2]
    img = cv2.resize(img,(w//2, h//2)) 
  
    # 显示图像  
    cv2.imshow('ImageWindow', img)  
    cv2.waitKey(1)  
  
    # 可选择添加退出条件，比如检测到特定的键被按下  
    if cv2.waitKey(1) & 0xFF == ord('q'):  
        break  
  
sock.close()  
cv2.destroyAllWindows()