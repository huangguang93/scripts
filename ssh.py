#!/usr/bin/python3
# -*- coding: UTF-8 -*-
from __future__ import print_function, unicode_literals, division, absolute_import

import sys
import os
import stat
import re
import time
import paramiko
import getpass
import datetime
import fcntl
import signal
import socket
import select
import logging
import logging.handlers
import multiprocessing
from paramiko.py3compat import u

try:
    import termios
    import tty
except ImportError:
    print('\033[1;31m仅支持类Unix系统 Only unix like supported.\033[0m')
    time.sleep(3)
    sys.exit()


class SshTty(object):
    """
    A virtual tty class
    一个虚拟终端类，实现连接ssh和记录日志
    """
    def __init__(self, user, ip, port=22):
        self.ip = ip
        self.port = port
        self.ssh = None
        self.channel = None
        self.user = user
        self.remote_ip = ''
        self.vim_flag = False
        self.ps1_pattern = re.compile('\[.*@.*\][\$#]')
        self.vim_data = ''

    def get_logger(self):
        """
        初始化日志对象
        """
        bash_dir = "/var/log/qssh"
        data = datetime.datetime.today().strftime('%Y-%m-%d')
        log_dir = os.path.join(bash_dir, data)
        if os.path.exists(log_dir) is False:
            try:
                os.makedirs(log_dir)
                os.chmod(log_dir, stat.S_IRWXO + stat.S_IRWXG + stat.S_IRWXU)  # 设置权限为777
            except Exception as error:
                print("Unable to create log file, error message: ", error)
                sys.exit(1)
        elif os.path.isdir(log_dir) is False:
            try:
                os.remove(log_dir)
                os.makedirs(log_dir)
                os.chmod(log_dir, stat.S_IRWXO + stat.S_IRWXG + stat.S_IRWXU)
            except Exception as error:
                print("Unable to create log file, error message: ", error)
                sys.exit(1)

        if os.access(log_dir, os.R_OK) and os.access(log_dir, os.W_OK) and os.access(log_dir, os.X_OK):
            log_file_path = os.path.join(log_dir, '%s.his' % (getpass.getuser(), ))
        else:
            print("Log folder permission error")
            sys.exit(1)

        log = logging.getLogger(__name__)
        log.setLevel(logging.DEBUG)
        fh = logging.FileHandler(log_file_path)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
        log.addHandler(fh)
        return log

    @staticmethod
    def is_output(strings):
        """
        对标准输出做换行处理
        """
        newline_char = ['\n', '\r', '\r\n']
        for char in newline_char:
            if char in strings:
                return True
        return False

    @staticmethod
    def remove_obstruct_char(cmd_str):
        """删除一些干扰的特殊符号"""
        control_char = re.compile(r'\x07 | \x1b\[1P | \r ', re.X)
        cmd_str = control_char.sub('', cmd_str.strip())
        patch_char = re.compile('\x08\x1b\[C')      # 删除方向左右一起的按键
        while patch_char.search(cmd_str):
            cmd_str = patch_char.sub('', cmd_str.rstrip())
        return cmd_str

    @staticmethod
    def deal_backspace(match_str, result_command, pattern_str, backspace_num):
        """
        处理删除确认键
        """
        if backspace_num > 0:
            if backspace_num > len(result_command):
                result_command += pattern_str
                result_command = result_command[0:-backspace_num]
            else:
                result_command = result_command[0:-backspace_num]
                result_command += pattern_str
        del_len = len(match_str)-3
        if del_len > 0:
            result_command = result_command[0:-del_len]
        return result_command, len(match_str)

    @staticmethod
    def deal_replace_char(match_str, result_command, backspace_num):
        """
        处理替换命令
        """
        str_lists = re.findall(r'(?<=\x1b\[1@)\w', match_str)
        tmp_str = ''.join(str_lists)
        result_command_list = list(result_command)
        if len(tmp_str) > 1:
            result_command_list[-backspace_num:-(backspace_num-len(tmp_str))] = tmp_str
        elif len(tmp_str) > 0:
            if result_command_list[-backspace_num] == ' ':
                result_command_list.insert(-backspace_num, tmp_str)
            else:
                result_command_list[-backspace_num] = tmp_str
        result_command = ''.join(result_command_list)
        return result_command, len(match_str)

    def remove_control_char(self, result_command):
        """
        处理日志特殊字符
        """
        control_char = re.compile(r"""
                \x1b[ #%()*+\-.\/]. |
                \r |                                               #匹配 回车符(CR)
                (?:\x1b\[|\x9b) [ -?]* [@-~] |                     #匹配 控制顺序描述符(CSI)... Cmd
                (?:\x1b\]|\x9d) .*? (?:\x1b\\|[\a\x9c]) | \x07 |   #匹配 操作系统指令(OSC)...终止符或振铃符(ST|BEL)
                (?:\x1b[P^_]|[\x90\x9e\x9f]) .*? (?:\x1b\\|\x9c) | #匹配 设备控制串或私讯或应用程序命令(DCS|PM|APC)...终止符(ST)
                \x1b.                                              #匹配 转义过后的字符
                [\x80-\x9f] | (?:\x1b\]0.*) | \[.*@.*\][\$#] | (.*mysql>.*)      #匹配 所有控制字符
                """, re.X)
        result_command = control_char.sub('', result_command.strip())

        if not self.vim_flag:
            if result_command.startswith('vi') or result_command.startswith('fg'):
                self.vim_flag = True
            # return result_command.decode('utf8', "ignore")
            return result_command
        else:
            return ''

    def deal_command(self, str_r):
        """
            处理命令中特殊字符
        """
        str_r = self.remove_obstruct_char(str_r)

        result_command = ''             # 最后的结果
        backspace_num = 0               # 光标移动的个数
        reach_backspace_flag = False    # 没有检测到光标键则为true
        pattern_str = ''
        while str_r:
            tmp = re.match(r'\s*\w+\s*', str_r)
            if tmp:
                str_r = str_r[len(str(tmp.group(0))):]
                if reach_backspace_flag:
                    pattern_str += str(tmp.group(0))
                    continue
                else:
                    result_command += str(tmp.group(0))
                    continue

            tmp = re.match(r'\x1b\[K[\x08]*', str_r)
            if tmp:
                result_command, del_len = self.deal_backspace(str(tmp.group(0)), result_command, pattern_str, backspace_num)
                reach_backspace_flag = False
                backspace_num = 0
                pattern_str = ''
                str_r = str_r[del_len:]
                continue

            tmp = re.match(r'\x08+', str_r)
            if tmp:
                str_r = str_r[len(str(tmp.group(0))):]
                if len(str_r) != 0:
                    if reach_backspace_flag:
                        result_command = result_command[0:-backspace_num] + pattern_str
                        pattern_str = ''
                    else:
                        reach_backspace_flag = True
                    backspace_num = len(str(tmp.group(0)))
                    continue
                else:
                    break

            tmp = re.match(r'(\x1b\[1@\w)+', str_r)                           # 处理替换的命令
            if tmp:
                result_command, del_len = self.deal_replace_char(str(tmp.group(0)), result_command, backspace_num)
                str_r = str_r[del_len:]
                backspace_num = 0
                continue

            if reach_backspace_flag:
                pattern_str += str_r[0]
            else:
                result_command += str_r[0]
            str_r = str_r[1:]

        if backspace_num > 0:
            result_command = result_command[0:-backspace_num] + pattern_str

        result_command = self.remove_control_char(result_command)
        return result_command

    def get_connection(self):
        """
        获取连接成功后的ssh
        """
        # 发起ssh连接请求 Make a ssh connection
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # 允许连接不在know_hosts文件中的主机

        # TODO 此处写死的密钥地址，不合理
        USER_HOME = os.environ['HOME']
        private_key_file = os.path.join(USER_HOME, ".ssh/id_rsa")
        private_key = paramiko.RSAKey.from_private_key_file(private_key_file)
        try:
            ssh.connect(hostname=self.ip,
                        port=self.port,
                        username=self.user,
                        pkey=private_key,
                        look_for_keys=False,  # 设置为False为禁用在~/.ssh/中搜索可用的私钥文件
                        timeout=3,
                        )
            return ssh
        except paramiko.ssh_exception.BadHostKeyException:
            print("Check Host key Error")
            return None
        except (paramiko.ssh_exception.AuthenticationException, paramiko.ssh_exception.SSHException):
            print('Security keys Authentication failed.')
            password = getpass.getpass('Enter password: ')
            try:
                ssh.connect(hostname=self.ip,
                            port=self.port,
                            username=self.user,
                            password=password,
                            allow_agent=False,
                            look_for_keys=False)
                return ssh
            except (paramiko.ssh_exception.AuthenticationException, paramiko.ssh_exception.SSHException):
                print('Password Authentication failed.')
                return None
        except socket.error:
            print('Connect to host %s timed out' % self.ip)
            return None

    @staticmethod
    def get_win_size():
        """
        获得terminal窗口大小
        """
        width = os.get_terminal_size().columns
        height = os.get_terminal_size().lines
        return height, width

    def set_win_size(self):
        """
        This function use to set the window size of the terminal!
        设置terminal窗口大小
        """
        try:
            win_size = self.get_win_size()
            self.channel.resize_pty(height=win_size[0], width=win_size[1])
        except Exception:
            pass

#    def posix_shell(self):
#        """
#        使用paramiko模块的channel，连接后端，进入交互式
#        """
#        unsupport_cmd_list = ['reboot', 'shutdown', "init"]
#        logger = self.get_logger()
#        old_tty = termios.tcgetattr(sys.stdin)
#        try:
#            tty.setraw(sys.stdin.fileno())
#            tty.setcbreak(sys.stdin.fileno())
#            self.channel.settimeout(0.0)
#            cmd = ""
#            tab_input_flag = False
#            while True:
#                r, w, e = select.select([self.channel, sys.stdin], [], [])
#
#                if self.channel in r:
#                    try:
#                        x = u(self.channel.recv(10240))
#                        if tab_input_flag:
#                            if x.startswith('\r\n'):
#                                pass
#                            else:
#                                cmd += x
#                            # cmd += ''.join(x[:10])
#                            tab_input_flag = False
#                        if len(x) == 0:
#                            sys.stdout.write('\r\n\033[32;1m*** Session Closed ***\033[0m\r\n')
#                            break
#
#                        sys.stdout.write(x)
#                        sys.stdout.flush()
#
#                    except socket.timeout:
#                        pass
#                    except UnicodeDecodeError:
#                        pass
#
#
#                if sys.stdin in r:
#                    x = sys.stdin.read(1)
#                    if len(x) == 0:
#                        break
#                    if not x == '\r':
#                        cmd += x
#                    else:
#                        if len(cmd.strip()) > 0:
#                            history = "%s %s %s" % (self.user, self.ip, cmd)
#                            logger.info(history)
#                        if cmd in unsupport_cmd_list:
#                            x = "\r\nOperation is not supported!\r\n"
#                        cmd = ''
#
#                    if x == '\t':
#                        tab_input_flag = True
#                    self.channel.send(x)
#
#        finally:
#            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)

    def posix_shell(self):
        """
        使用paramiko模块的channel，连接后端，进入交互式
        """
        logger = self.get_logger()
        unsupport_cmd_list = ['reboot', 'shutdown', "init"]
        old_tty = termios.tcgetattr(sys.stdin)
        cmd = ''
        input_mode = False
        try:
            tty.setraw(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
            self.channel.settimeout(0.0)

            while True:
                try:
                    r, w, e = select.select([self.channel, sys.stdin], [], [])
                    #flag = fcntl.fcntl(sys.stdin, fcntl.F_GETFL, 0)
                    #fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, flag | os.O_NONBLOCK)
                except Exception:
                    pass

                if self.channel in r:
                    try:
                        x = u(self.channel.recv(10240))
                        if len(x) == 0:
                            sys.stdout.write('\r\n\033[32;1m*** Session Closed ***\033[0m\r\n')
                            break
                        if self.vim_flag:
                            self.vim_data += x
                        index = 0
                        while index < len(x):
                            n = os.write(sys.stdout.fileno(), bytes(x[index:], encoding='utf-8'))
                            sys.stdout.flush()
                            index += n

                        if input_mode and not self.is_output(x):
                            cmd += x

                    except socket.timeout:
                        print("socket timeout")
                    except UnicodeDecodeError:
                        print("decode error")

                if sys.stdin in r:
                    try:
                        x = u(os.read(sys.stdin.fileno(), 4096))
                        input_mode = True

                        if x in ['\r', '\n', '\r\n']:
                            if self.vim_flag:
                                match = self.ps1_pattern.search(self.vim_data)
                                if match:
                                    self.vim_flag = False

                            cmd = self.deal_command(cmd)[0:200]
                            # 记录用户操作日志
                            if len(cmd) > 0:
                                history = "%s %s %s" % (self.user, self.ip, cmd)
                                logger.info(history)
                            # 命令限制
                            if cmd in unsupport_cmd_list:
                                x = "\rOperation is not supported!\r\n"
                            cmd = ''
                            self.vim_data = ''
                            input_mode = False

                        if len(x) == 0:
                            break
                        self.channel.send(x)

                    except socket.timeout:
                        print("socket timeout")
                    except UnicodeDecodeError:
                        print("decode error")
        finally:
            # 恢复之前的 tty
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)

    def connect(self):
        """
        连接服务器
        """
        # 发起ssh连接请求 Make a ssh connection
        ssh = self.get_connection()
        if ssh is None:
            return None
        transport = ssh.get_transport()
        transport.set_keepalive(30)
        transport.use_compression(True)

        # 获取连接的隧道并设置窗口大小 Make a channel and set windows size
        global channel
        win_size = self.get_win_size()
        self.channel = channel = transport.open_session()
        channel.get_pty(term='xterm', height=win_size[0], width=win_size[1])
        channel.invoke_shell()
        try:
            signal.signal(signal.SIGWINCH, self.set_win_size)
        except:
            pass
        
        self.posix_shell()
        # Shutdown channel socket
        channel.close()
        ssh.close()

    def exec_cmd(self, cmd):
        """
        连接服务器
        """
        # 发起ssh连接请求 Make a ssh connection
        ssh = self.get_connection()
        if ssh is None:
            return None

        stdin, stdout, stderr = ssh.exec_command(cmd)  # 分别保存，标准输入，标准输出，错误输出
        stdout_content = stdout.read().decode('utf8')
        stderr_content = stderr.read().decode('utf8')

        if stdout.channel.recv_exit_status() == 0:  # 根据返回状态码判断是否成功
            print('\033[1;32m%s\033[0m' % '%s   |    SUCCESS :\n%s' % (self.ip, stdout_content))
            if stderr_content:
                print('\033[1;32m%s\033[0m' % stderr_content)
        else:
            if stderr_content:
                print('\033[1;31m%s\033[0m' % '%s   |    FAILED :\n%s' % (self.ip, stderr_content))
            else:
                print('\033[1;31m%s\033[0m' % '%s   |    FAILED :\n%s' % (self.ip, "non-zero return code"))
        ssh.close()


def login(ip, user=None):
    """"""
    if user is None:
        user = getpass.getuser()  # 获取终端登录用户名
        if user != "devops":
            user = "root"
    sshtty = SshTty(user, ip)
    sshtty.connect()


def run_cmd(ip_list, cmd, user=None, port=22):
    ip_list = list(set(ip_list))
    if user is None:
        user = getpass.getuser()  # 获取终端登录用户名
        if user != "devops":
            user = "root"

    max_thread = 2
    current_location = 0
    while True:
        pool = multiprocessing.Pool(processes=max_thread)
        for i in range(max_thread):
            try:
                ip = ip_list[current_location]
            except IndexError:
                break
            pool.apply_async(handler, (ip, user, port, cmd, ))
            if current_location == len(ip_list):
                break
            current_location += 1
        pool.close()
        pool.join()
        pool.terminate()
        if current_location == len(ip_list):
            break


def handler(ip, user, port, cmd):
    ssh_tty = SshTty(user=user, ip=ip, port=port)
    ssh_tty.exec_cmd(cmd)


if __name__ == '__main__':
    while True:
        ip = input("请输入想登陆的ip: ")
        login(ip=ip)

