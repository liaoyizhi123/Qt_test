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

    # # thread_1
    # def _listening_connection(self, callback_function):
    #     print("\tThread 1 start: Listening for connection...")
    #     self.socket.settimeout(1)  # 设置超时时间，以便能够及时关闭线程
    #     while self.running:
    #         try:
    #             print("\tThread 1: before accept")
    #             self.client_socket, _ = self.socket.accept()  # block until a client connects
    #             threading.Thread(target=self._receiving_data, args=(callback_function,)).start()
    #             print("\tThread 1: after accept")
    #             print(f"\tThread 1: Connected with {_}")
    #         except socket.timeout:
    #             continue
    #     print("\tThread 1 end.")

    # thread_1
    def _listening_connection(self, callback_function):
        thread_name = threading.current_thread().name
        print(f"\t{thread_name}start: Listening for connection...")
        while self.running:
            print(f"\t{thread_name}: before accept")
            self.client_socket, _ = self.socket.accept()  # block until a client connects
            threading.Thread(target=self._receiving_data, args=(callback_function,)).start()
            print(f"\t{thread_name}: after accept")
            print(f"\t{thread_name}: Connected with {_}")
        print(f"\t{thread_name} end.")

    # thread_2
    def _receiving_data(self, _):
        thread_name = threading.current_thread().name
        print(f"\t\t{thread_name} start: Receiving data...")
        while self.running:
            try:
                data = self.client_socket.recv(1024)  # 一个阻塞操作，直到接收到数据或连接关闭才会继续
                if not data:  # 如果接收到空数据，like b""，说明连接已经关闭
                    break
                _(data)
            except ConnectionResetError:
                print(f"\t\t{thread_name} connection closed.")
                break
        print(f"\t\t{thread_name} end.")

    def stop_receiving(self):
        self.running = False

        # ####################################优雅推出
        # if self.listening_thread:
        #
        #     print('join1')
        #     self.listening_thread.join()  # block until the listening thread ends
        #     print('join2')
        # ####################################优雅推出

        if self.client_socket:
            self.client_socket.close()
        self.socket.close()


class EEGReceiverTCPWithUI:
    def __init__(self, ip, port, update_ui_call_back):
        print(f"{threading.current_thread().name}: -------------------------create receiver")
        self.ip = ip
        self.port = port
        self.update_ui_call_back = update_ui_call_back

        self.running = False
        self.socket = None
        self.client_socket = None   # client_socket 用于与该客户端通信
        self.listening_thread = None

    def start_receiving(self, callback_function):
        ## 启动thread1，然后结束本函数的运行
        if self.socket is None:
            print(f"{threading.current_thread().name}: create socket")
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.bind((self.ip, self.port))
                self.socket.listen(1)
            except Exception as e:
                print(f"{threading.current_thread().name}: {e}")
                return False

        if not self.running:  # 防止重复启动
            self.running = True
            self.listening_thread = threading.Thread(target=self._listening_connection, args=(callback_function,))
            self.listening_thread.start()
        return True

    # thread_1
    def _listening_connection(self, callback_function):
        thread_name = threading.current_thread().name
        print(f"\t{thread_name}start: Listening for connection...")
        try:
            print(f"\t{thread_name}: before accept")
            self.client_socket, _ = self.socket.accept()  # block until a client connects
            print(f"\t{thread_name}: after accept")
            print(f"\t{thread_name}: Connected with {_}")

            receiving_thread = threading.Thread(target=self._receiving_data, args=(callback_function,))
            receiving_thread.start()
            receiving_thread.join()

        except Exception as e:
            print(f"\t{thread_name}: {e}")
        finally:
            if self.socket:
                self.socket.close()
            self.running = False
            self.update_ui_call_back(False)
            print(f"\t{thread_name} end.")
            # print(f"\t{self.client_socket}")
            # print(f"\t{self.socket}")

    # thread_2
    def _receiving_data(self, _):
        self.update_ui_call_back(True)
        thread_name = threading.current_thread().name
        print(f"\t\t{thread_name} start: Receiving data...")
        while self.running:
            try:
                data = self.client_socket.recv(1024)  # 一个阻塞操作，直到接收到数据或连接关闭才会继续
                if not data:  # 如果接收到空数据，like b""，说明连接已经关闭
                    break
                _(data)
            except ConnectionResetError:
                print(f"\t\t{thread_name} connection closed.")
                self.running = False
                if self.client_socket:
                    self.client_socket.close()
                break
            except Exception as e:
                print(f"\t\t{thread_name}: {e}")
                self.running = False
                if self.client_socket:
                    self.client_socket.close()
                break
        if self.client_socket:
            self.client_socket.close()
        print(f"\t\t{thread_name} end.")
        # print(f"\t\t{self.client_socket}")
        # print(f"\t\t{self.socket}")

    def stop_receiving(self):
        self.running = False

        if self.client_socket:
            self.client_socket.close()
            self.client_socket = None
        if self.socket:
            self.socket.close()
            self.socket = None
        self.update_ui_call_back(False)

if __name__ == '__main__':
    def process_data(_):
        print(f'\t\t{threading.current_thread().name}'+str(_))

    thread_name = threading.current_thread().name
    print(f"{thread_name}: running...")
    receiver = EEGReceiverTCP('127.0.0.1', 12345)
    receiver.start_receiving(process_data)

    try:
        while True:
            pass # keep the main thread running
    except KeyboardInterrupt:
        print("KeyboardInterrupt")
        receiver.stop_receiving()
        print(f"{thread_name}: Receiver stopped.")





