import os
import time
import logging
import hashlib
import threading
from pyftpdlib.authorizers import DummyAuthorizer, AuthenticationFailed
from pyftpdlib.handlers import FTPHandler, ThrottledDTPHandler
from pyftpdlib.servers import FTPServer, ThreadedFTPServer, MultiprocessFTPServer
from pyftpdlib.log import LogFormatter


def hash_md5(string):
    md5_handler = hashlib.md5()
    byte_str = string.encode(encoding='utf-8')
    md5_handler.update(byte_str)
    return md5_handler.hexdigest()


class MyFTPHandler(FTPHandler):

    def on_connect(self):
        print("[event]: connected server, [remote_ip]: {}, [remote_port]: {}".format(self.remote_ip, self.remote_port))

    def on_disconnect(self):
        print("[event]: client disconnects server, [remote_ip]: {}, [remote_port]: {}".format(self.remote_ip, self.remote_port))
        # do something when client disconnects
        pass

    def on_login(self, username):
        # do something when user login
        print("[event]: user login, [username]: {}".format(username))
        pass

    def on_logout(self, username):
        # do something when user logs out
        print("[event]: user logout, [username]: {}".format(username))
        pass

    def on_login_failed(self, username, password):
        print("[event]: login failed, [username]: {}, [password]: {}".format(username, password))

    def on_file_sent(self, file):
        # 每次成功发送文件时调用。file: 文件的绝对路径。（下载成功）
        # do something when a file has been sent
        print("[event]: file sent, [file]: {}".format(file))
        pass

    def on_file_received(self, file):
        # 每次成功接受文件时调用。file: 文件的绝对路径。(上传成功)
        # do something when a file has been received
        print("[event]: file received, [file]: {}".format(file))
        def blocking_task():
            # time.sleep(5)
            print("******    this is blocking task     ******")
            self.add_channel()
        self.del_channel()
        blocking_task()
        # threading.Thread(target=blocking_task).start()

    def on_incomplete_file_sent(self, file):
        # 每次文件发送失败时调用（例如，客户端中止传输）
        # do something when a file is partially sent
        print("[event]: incomplete file sent, [file]: {}".format(file))
        pass

    def on_incomplete_file_received(self, file):
        # 每次文件接受失败时调用（例如，客户端中止传输）
        print("[event]: incomplete file received, [file]: {}".format(file))
        # remove partially uploaded files
        import os
        os.remove(file)


class DummyMD5Authorizer(DummyAuthorizer):

    def validate_authentication(self, username, password, handler):
        hash_password = hash_md5(password)
        try:
            if self.user_table[username]['pwd'] != hash_password:
                raise KeyError
        except KeyError:
            raise AuthenticationFailed


def run(host='0.0.0.0', port=21, mode="single"):
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)  # Log等级总开关
    fh = logging.FileHandler(filename="ftpserver.log", encoding='utf-8')
    logger.addHandler(fh)

    ftp_authorizers = DummyMD5Authorizer()
    # 添加用户权限和路径，括号内的参数是(用户名，密码，用户目录，权限)
    """
    读取权限：
    "e" =更改目录（CWD，CDUP命令）
    "l" =列表文件（LIST，NLST，STAT，MLSD，MLST，SIZE命令）
    "r" =从服务器检索文件（RETR命令）
    写入权限：
    "a" =将数据附加到现有文件（APPE命令）
    "d" =删除文件或目录（DELE，RMD命令）
    "f" =重命名文件或目录（RNFR，RNTO命令）
    "m" =创建目录（MKD命令）
    "w" =将文件存储到服务器（STOR，STOU命令）
    "M"=更改文件模式/权限（SITE CHMOD命令）0.7.0中的新增功能
    "T"=更改文件修改时间（SITE MFMT命令）1.5.3中的新增功能
    """
    hash_password = hash_md5("12345")
    home_dir = os.getcwd()
    ftp_authorizers.add_user(username='user', password=hash_password, homedir=home_dir, perm="elradfmwMT")
    # 添加匿名用户只需要指定路径
    ftp_authorizers.add_anonymous('/tmp/')

    # 初始化ftp句柄
    ftp_handler = MyFTPHandler
    ftp_handler.authorizer = ftp_authorizers

    # Define a customized banner (string returned when client connects)
    ftp_handler.banner = "pyftpdlib based ftpd ready."


    # 添加被动端口范围
    ftp_handler.passive_ports = range(30000, 30100)

    # 下载上传速度设置, 0为无限制
    dtp_handler = ThrottledDTPHandler
    dtp_handler.read_limit = 300 * 1024  # 300kb/s
    dtp_handler.write_limit = 300 * 1024  # 300kb/s
    ftp_handler.dtp_handler = dtp_handler

    # 设置监听ip和端口，多线程模式
    if mode == "default":
        server = FTPServer((host, port), ftp_handler)
    elif mode == "threaded":
        server = ThreadedFTPServer((host, port), ftp_handler)
    elif mode == "multiprocess":
        server = MultiprocessFTPServer((host, port), ftp_handler)
    else:
        server = FTPServer((host, port), ftp_handler)

    # 设置最大连接数
    server.max_cons = 150
    server.max_cons_per_ip = 15

    # 开始服务，打印日志
    server.serve_forever()


if __name__ == "__main__":
    run(host="0.0.0.0", port=2121, mode="threaded")
