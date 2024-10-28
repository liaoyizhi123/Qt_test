import socket
import time

ip = "127.0.0.1"
port = 12345

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.connect((ip, port))

try:
    # 发送多条数据
    for i in range(5):
        message = f"Test message {i}"
        client_socket.sendall(message.encode('utf-8'))
        print(f"Sent: {message}")
        time.sleep(1)  # 发送间隔时间

finally:
    # 关闭客户端套接字
    client_socket.close()
    print("Client socket closed.")
