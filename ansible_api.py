#!/usr/bin/env python
# python3.6 + ansible==2.7.12

import json
import shutil
import unittest
import logging
from collections import namedtuple
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.playbook.play import Play
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.plugins.callback import CallbackBase
import ansible.constants as C
from ansible.utils.display import Display


# 创建logger, 存储playbook的输出日志
logger = logging.getLogger()
logfile = "/root/test.log"
fh = logging.FileHandler(logfile)
fh.setFormatter(logging.Formatter("%(asctime)s: %(message)s"))
logger.addHandler(fh)



class ResultCallback(CallbackBase):
    """
    ansible执行回调类
    """
    def __init__(self, *args, **kwargs):
        super(ResultCallback, self).__init__(*args, **kwargs)
        self.host_ok = {}
        self.host_unreachable = {}
        self.host_failed = {}

    def v2_runner_on_ok(self, result, **kwargs):
        """成功"""
        self.host_ok[result._host.name] = result._result["stdout"]

    def v2_runner_on_unreachable(self, result, **kwargs):
        """不可达"""
        self.host_unreachable[result._host.get_name()] = result
        # self.host_unreachable[result._host.name] = result._result["msg"]

    def v2_runner_on_failed(self, result, ignore_errors=False, **kwargs):
        """失败"""
        self.host_failed[result._host.name] = result._result["stderr"]


class AnsibleApi(object):
    def __init__(self, private_key_file="~/.ssh/id_rsa", results_callback=None):
        self.private_key_file = private_key_file

        # 实例化回调插件对象
        self.results_callback = results_callback if results_callback else ResultCallback()

    def runner(self, inventory, hosts="localhost", module="ping", args=""):
        """
        类似Ad-Hoc命令
        :param inventory: 一个清单文件，一行一个ip就行
        :param hosts
        :param module:
        :param args:
        :return:
        """
        Options = namedtuple(
            "Options",
            [
                "connection",
                "module_path",
                "forks",
                "private_key_file",
                "remote_user",
                "become",
                "become_method",
                "become_user",
                "check",
                "diff",
            ],
        )
        options = Options(
            connection="smart",
            module_path=None,
            forks=10,
            private_key_file=self.private_key_file,  # 你的私钥
            remote_user="root",  # 远程用户
            become=True,
            become_method="sudo",
            become_user="root",
            check=False,
            diff=False,
        )
        # 主要加载设置的变量
        loader = DataLoader()
        # 一个密码参数，可以设置为None，默认即可，没什么影响，我用的是秘钥登录
        passwords = dict(vault_pass="secret")

        # 设置传入的机器清单
        inventory_obj = InventoryManager(loader=loader, sources=inventory)

        # 加载之前的变量
        variable_manager = VariableManager(loader=loader, inventory=inventory_obj)

        play_source = dict(
            name="Ansible Ad-Hoc",
            hosts=hosts,
            gather_facts="no",
            tasks=[dict(action=dict(module=module, args=args), register="shell_out"),],
        )
        play = Play().load(
            play_source, variable_manager=variable_manager, loader=loader
        )

        tqm = None
        try:
            tqm = TaskQueueManager(
                inventory=inventory_obj,
                variable_manager=variable_manager,
                loader=loader,
                options=options,
                passwords=passwords,
                stdout_callback=self.results_callback,
            )
            result_code = tqm.run(play)
        finally:
            if tqm is not None:
                tqm.cleanup()
            shutil.rmtree(C.DEFAULT_LOCAL_TMP, True)

        result_raw = {"success": {}, "failed": {}, "unreachable": {}}

        for host, result in self.results_callback.host_ok.items():
            result_raw["success"][host] = json.dumps(result._result)
        for host, result in self.results_callback.host_unreachable.items():
            result_raw["unreachable"][host] = result._result['msg']
        for host, result in self.results_callback.host_failed.items():
            result_raw["failed"][host] = result._result['msg']


        # result_code 等于0代表任务全部运行成功
        return result_code, result_raw


    def runner_playbook(self, playbooks, inventory):
        """
        运行playbook
        :param playbooks: playbook的路径
        :param inventory:
        :return:
        """
        if isinstance(playbooks, str):
            playbooks = [playbooks]
        Options = namedtuple(
            "Options",
            [
                "connection",
                "module_path",
                "forks",
                "private_key_file",
                "become",
                "become_method",
                "become_user",
                "check",
                "diff",
                "listhosts",
                "listtasks",
                "listtags",
                "syntax",
                "verbosity",
            ],
        )
        options = Options(
            connection="smart",
            module_path=None,
            forks=10,
            private_key_file=self.private_key_file,  # 你的私钥
            become=True,
            become_method="sudo",
            become_user="root",
            check=False,
            diff=False,
            listhosts=None,
            listtasks=None,
            listtags=None,
            syntax=None,
            verbosity=1,  # >= 4 时展示详细调试信息

        )

        loader = DataLoader()
        passwords = dict(vault_pass="secret")
        inventory_obj = InventoryManager(loader=loader, sources=inventory)
        variable_manager = VariableManager(loader=loader, inventory=inventory_obj)

        executor = PlaybookExecutor(
            playbooks=playbooks,
            inventory=inventory_obj,
            variable_manager=variable_manager,
            loader=loader,
            options=options,
            passwords=passwords,
        )

        if self.results_callback:
            executor._tqm._callback_plugins.append(self.results_callback)

        executor._tqm._gather_facts = False

        result_code = executor.run()

        result_raw = {"success": {}, "failed": {}, "unreachable": {}}

        for host, result in self.results_callback.host_ok.items():
            result_raw['success'][host] = json.dumps(result._result)

        for host, result in self.results_callback.host_failed.items():
            result_raw['failed'][host] = result._result['msg']

        for host, result in self.results_callback.host_unreachable.items():
            result_raw['unreachable'][host] = result._result['msg']

        # result_code 等于0代表任务全部运行成功
        return result_code, result_raw


class TestAnsibleApi(unittest.TestCase):
    """Ansible工具类单元测试"""

    def setUp(self):
        self.factory = AnsibleApi(private_key_file="/root/.ssh/id_rsa")

    def test_ansible_runner(self):
        code, ret = self.factory.runner("/tmp/host", "test-group", "shell", "ls -l /")

        print(ret)
        r = ret['success'] or ret['failed'] or ret['unreachable']
        self.assertTrue(r)
        self.assertEqual(code, 0)

    def test_ansible_playbook(self):
        code, ret = self.factory.runner_playbook("/tmp/repo.yml", "/tmp/host")

        print(ret)
        r = ret['success'] or ret['failed'] or ret['unreachable']
        self.assertTrue(r)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
