import socket
import time

import numpy as np

ip = "127.0.0.1"
port = 12345

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((ip, port))

try:
    # 发送多条数据
    for i in range(100000):
        random_number = np.random.normal(10, 1)
        message = f"{i},{random_number}"
        client_socket.sendall(message.encode('utf-8'))
        print(f"Sent: {message}")
        time.sleep(0.01)  # 发送间隔时间 10ms

finally:
    # 关闭客户端套接字
    client_socket.close()
    print("Client socket closed.")
