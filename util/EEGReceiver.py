import socket
import threading


class EEGReceiverUDP:
    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.ip, self.port))
        self.running = False

    def receiving_data(self, _):
        while self.running:
            data, address = self.socket.recvfrom(1024)
            _(data)

    def start_receiving(self, callback_function):
        self.running = True
        threading.Thread(target=self.receiving_data, args=(callback_function,)).start()

    def stop_receiving(self):
        self.running = False
        self.socket.close()


class EEGReceiverTCP:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind((self.ip, self.port))
        self.socket.listen(1)  # 只监听一个连接

        self.client_socket = None   # client_socket 用于与该客户端通信
        self.running = False
        self.listening_thread = None

    def start_receiving(self, callback_function):
        self.running = True
        self.listening_thread = threading.Thread(target=self._listening_connection, args=(callback_function,))
        self.listening_thread.start()

    # thread_1
    def _listening_connection(self, callback_function):
        print("\tThread 1 start: Listening for connection...")
        while self.running:

            self.client_socket, _ = self.socket.accept()  # block until a client connects
            print(f"\tThread 1: Connected with {_}")

            threading.Thread(target=self._receiving_data, args=(callback_function,)).start()
        print("\tThread 1 end.")

    # thread_2
    def _receiving_data(self, _):
        print("\t\tThread 2 start: Receiving data...")
        while self.running:
            try:
                data = self.client_socket.recv(1024)  # 一个阻塞操作，直到接收到数据或连接关闭才会继续
                if not data:  # 如果接收到空数据，like b""，说明连接已经关闭
                    break
                _(data)
            except ConnectionResetError:
                print("\t\tConnection closed.")
                break
        print("\t\tThread 2 end.")

    def stop_receiving(self):
        self.running = False
        if self.listening_thread:
            print('join+')
            self.listening_thread.join()  # block until the listening thread ends

        if self.client_socket:
            self.client_socket.close()
        self.socket.close()

if __name__ == '__main__':
    def process_data(_):
        print('\t\t'+str(_))

    print("Main Thread: Main thread running...")
    receiver = EEGReceiverTCP('127.0.0.1', 12345)
    receiver.start_receiving(process_data)

    try:
        while True:
            pass # keep the main thread running
    except KeyboardInterrupt:
        print("KeyboardInterrupt")
        receiver.stop_receiving()
        print("Mian Thread: Receiver stopped.")






