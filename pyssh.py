#!/usr/bin/python3
# -*- coding: UTF-8 -*-
from __future__ import print_function, unicode_literals, division, absolute_import

import sys
import os
import time
import paramiko
import signal
import socket
import select


try:
    import termios
    import tty
except ImportError:
    print("\033[1;31m仅支持类Unix系统 Only unix like supported.\033[0m")
    time.sleep(3)
    sys.exit()


class SshTty(object):
    """
    A virtual tty class
    一个虚拟终端类，实现连接ssh和记录日志
    """

    def __init__(self, user, ip, port=22, private_key_file="~/.ssh/id_rsa"):
        self.ip = ip
        self.port = port
        self.ssh = None
        self.channel = None
        self.user = user
        self.private_key_file = private_key_file

    def get_connection(self):
        """
        获取连接成功后的ssh
        """
        # 发起ssh连接请求 Make a ssh connection
        ssh = paramiko.SSHClient()
        # 不执行ssh.load_system_host_keys()， 以空白的已知主机密钥列表开始，不过这样不安全。我们在专线情况下可以这么做
        # ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(
            paramiko.AutoAddPolicy()
        )  # 允许连接不在know_hosts文件中的主机

        private_key = paramiko.RSAKey.from_private_key_file(self.private_key_file)
        try:
            ssh.connect(
                hostname=self.ip,
                port=self.port,
                username=self.user,
                pkey=private_key,
                look_for_keys=False,  # 设置为False为禁用在~/.ssh/中搜索可用的私钥文件
                timeout=3,
            )
            return ssh
        except paramiko.ssh_exception.NoValidConnectionsError:
            print("连接失败")
            return None
        except paramiko.ssh_exception.BadHostKeyException:
            print("Check Host key Error")
            return None
        except paramiko.ssh_exception.AuthenticationException:
            print("ssh authentication failed.")
            return None
        except paramiko.ssh_exception.SSHException:
            print("an unknown error occurred")
            return None
        except socket.error:
            print("Connect to host %s timed out" % self.ip)
            return None

    @staticmethod
    def get_win_size():
        """
        获得terminal窗口大小
        """
        width = os.get_terminal_size().columns
        height = os.get_terminal_size().lines
        return height, width

    def set_win_size(self, sig, data, *args, **kwargs):
        """
        This function use to set the window size of the terminal!
        设置terminal窗口大小
        """
        try:
            win_size = self.get_win_size()
            self.channel.resize_pty(height=win_size[0], width=win_size[1])
        except Exception:
            pass

    def u(self, s):
        """cast bytes or unicode to unicode"""
        if isinstance(s, bytes):
            return s.decode(encoding='utf8', errors="ignore")
        elif isinstance(s, str):
            return s
        else:
            raise TypeError("Expected unicode or bytes, got {!r}".format(s))

    def posix_shell(self):
        """
        使用paramiko模块的channel，连接后端，进入交互式
        """
        user_home = os.environ["HOME"]
        log_path = os.path.join(user_home, ".qssh")
        today = time.strftime("%Y%m%d", time.localtime(int(time.time())))
        file_name = f"{today}.his"
        log_file = os.path.join(log_path, file_name)

        if os.path.exists(log_path) is False:
            os.makedirs(log_path)

        write_log = open(log_file, 'a+', encoding='utf-8')

        old_tty = termios.tcgetattr(sys.stdin)

        try:
            tty.setraw(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            self.channel.settimeout(0.0)

            while True:
                r, w, e = [], [], []
                try:
                    r, w, e = select.select([self.channel, sys.stdin], [], [])
                except Exception:
                    pass

                try:
                    if self.channel in r:
                        x = self.u(self.channel.recv(1024))
                        if len(x) == 0:
                            sys.stdout.write(
                                f"\r\n\033[32;1m {self.ip} 已断开连接...\033[0m\r\n"
                            )
                            break

                        sys.stdout.write(x)
                        sys.stdout.flush()

                        # 记录日志
                        write_log.write(x)
                        write_log.flush()

                    if sys.stdin in r:
                        x = self.u(os.read(sys.stdin.fileno(), 4096))
                        if len(x) == 0:
                            break

                        if x in ["\r", "\n", "\r\n"]:
                            # 记录日志
                            write_log.write(x)
                            write_log.flush()

                        self.channel.send(x)

                except socket.timeout:
                    pass
                except UnicodeDecodeError as e:
                    print(f"Unicode decode error, info: {e}")
        finally:
            # 恢复之前的 tty
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)

    def ssh_connect(self):
        """
        ssh连接服务器
        """
        # 发起ssh连接请求 Make a ssh connection
        ssh = self.get_connection()
        if ssh is None:
            return False

        transport = ssh.get_transport()
        transport.set_keepalive(30)
        transport.use_compression(True)

        # 获取连接的隧道并设置窗口大小 Make a channel and set windows size
        # global channel
        win_size = self.get_win_size()

        # 打开一个通道
        self.channel = channel = transport.open_session()
        # 获取一个终端
        channel.get_pty(term="xterm", height=win_size[0], width=win_size[1])
        channel.invoke_shell()
        try:
            signal.signal(signal.SIGWINCH, self.set_win_size)
        except:
            pass

        self.posix_shell()
        # Shutdown channel socket
        channel.close()
        ssh.close()
        return True

    def exec_cmd(self, cmd):
        """
        连接服务器
        """
        # 发起ssh连接请求 Make a ssh connection
        ssh = self.get_connection()
        if ssh is None:
            return None

        stdin, stdout, stderr = ssh.exec_command(cmd)  # 分别保存，标准输入，标准输出，错误输出
        stdout_content = stdout.read().decode("utf8")
        stderr_content = stderr.read().decode("utf8")

        if stdout.channel.recv_exit_status() == 0:  # 根据返回状态码判断是否成功
            print(
                "\033[1;32m%s\033[0m"
                % "%s   |    SUCCESS :\n%s"
                % (self.ip, stdout_content)
            )
            if stderr_content:
                print("\033[1;32m%s\033[0m" % stderr_content)
        else:
            if stderr_content:
                print(
                    "\033[1;31m%s\033[0m"
                    % "%s   |    FAILED :\n%s"
                    % (self.ip, stderr_content)
                )
            else:
                print(
                    "\033[1;31m%s\033[0m"
                    % "%s   |    FAILED :\n%s"
                    % (self.ip, "non-zero return code")
                )
        ssh.close()


def ssh_login(ip, log_name=None, port=22):
    """
    ssh登陆服务器
    """
    user_home = os.environ.get("HOME") or ""
    private_key_file = os.path.join(user_home, ".ssh/id_rsa")

    print(f"正在登陆 {log_name}@{ip}:{port} ...")
    ssh_tty = SshTty(user=log_name, ip=ip, port=port, private_key_file=private_key_file)
    ret = ssh_tty.ssh_connect()
