#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, unicode_literals, division, absolute_import

import os
import curses
import random
import time


class Snake:
    def __init__(self):
        self.stdscr = curses.initscr()
        curses.start_color()
        curses.cbreak()
        curses.curs_set(0)
        self.init_colors()
        self.width = os.get_terminal_size().columns  # 获取终端的宽
        self.height = os.get_terminal_size().lines   # 获取终端的高

        self.win_snake_width = int(self.width * 0.6)  # 代表窗口总宽度
        self.win_snake_heigth = self.height - 6  # 代表窗口总高度
        self.win_snake_start_x = 3   # 窗口开始的x轴位置
        self.win_snake_start_y = 4   # 窗口开始的x轴位置

        self.side_win_width = int(self.width * 0.2)
        self.side_win_heigth = self.height - 6  # 代表窗口总高度
        self.side_win_start_x = self.win_snake_start_x + self.win_snake_width + 2  # 窗口开始的x轴位置
        self.side_win_start_y = 4   # 窗口开始的x轴位置

        #self.snake_filling_symbol = "⊙"
        self.snake_filling_symbol = "+"
        self.food_filling_symbol = "★"

        self.score = 0
        self.hi_score = self.record_score("read")
        self.food_pos = None
        self.welcome_player()
        self.snake_win = self.init_snake_win()
        self.side_window = self.init_side_window()

    def welcome_player(self):
        """Welcome the player to the game with a countdown to start"""
        num = 2
        while num > 0:
            self.stdscr.addstr(int(self.height / 2 - 4), int(self.width / 2 - 8), "Starting in...{}s".format(num))
            self.stdscr.refresh()
            time.sleep(1)
            num -= 1

    def init_colors(self):
        """Initialize colors"""
        curses.init_pair(8, curses.COLOR_BLUE, curses.COLOR_WHITE)
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_WHITE)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLUE)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_MAGENTA)
        curses.init_pair(4, curses.COLOR_RED, curses.COLOR_CYAN)
        curses.init_pair(5, curses.COLOR_RED, curses.COLOR_RED)
        curses.init_pair(6, curses.COLOR_RED, curses.COLOR_GREEN)
        curses.init_pair(7, curses.COLOR_RED, curses.COLOR_YELLOW)

    def init_snake_win(self):
        """初始化蛇活动窗口"""
        snake_win = curses.newwin(self.win_snake_heigth,
                                  self.win_snake_width,
                                  self.win_snake_start_y,
                                  self.win_snake_start_x)
        snake_win.border()  # 设置窗口边框
        snake_win.keypad(1)
        snake_win.timeout(100)
        return snake_win

    def init_side_window(self):
        """Initalize side_window that shows the current level, score, and next brick"""
        side_window = curses.newwin(self.side_win_heigth,
                                    self.side_win_width,
                                    self.side_win_start_y,
                                    self.side_win_start_x)
        side_window.border()
        side_window.addstr(2, 2, "Snake 1.0")
        score = "Score     {}  ".format(self.score)
        hi_score = "Hi Score  {}  ".format(self.hi_score)
        side_window.addstr(5, 3, score)  # y, x
        side_window.addstr(6, 3, hi_score)  # y, x
        side_window.addstr(9, 3, "Controls:")  # y, x
        side_window.addstr(10, 4, "方向键 - 控制蛇移动方向")  # y, x
        side_window.addstr(11, 4, "其他键 - 退出游戏")  # y, x
        side_window.refresh()
        return side_window

    def generate_food(self, snake):
        """随机生产食物坐标"""
        while True:
            new_food = [random.randint(1, self.win_snake_heigth - 2), random.randint(1, self.win_snake_width - 2)]
            if new_food not in snake:
                self.food_pos = new_food
                break
        self.snake_win.addch(self.food_pos[0], self.food_pos[1], self.food_filling_symbol, curses.color_pair(5))

    def update_side_win(self):
        """更新侧边框中的数据"""
        self.score += 1
        if self.score > self.hi_score:
            self.hi_score = self.score
            self.record_score("write", self.score)
        score = "Score     {}  ".format(self.score)
        self.side_window.addstr(5, 3, score)
        self.side_window.refresh()

    def record_score(self, method, new_score=None):
        """记录和查询历史最高分"""
        score_file = os.path.join(os.environ["HOME"], ".snake.score")
        try:
            if method == "read":
                with open(score_file, "r") as f:
                    record = f.read()
                return int(record.strip())
            elif method == "write":
                with open(score_file, "w") as f:
                    f.write(str(new_score))
        except Exception as err:
            print(err)
            return 0

    def get_input(self, key):
        """获取用户的输入"""
        try:
            next_key = self.snake_win.getch()  # getch()返回一个整数 ，在0到255之间，表示输入字符的ASCII值
            if next_key != -1:
                if next_key == ord("p"):     # 112 is the int value for "p"
                    self.stdscr.addstr(int(self.height / 2), int(self.width / 2 - 10), "PAUSED! press p to continue.")
                    self.snake_win.nodelay(False)
                    ch = self.stdscr.getch()
                    self.snake_win.nodelay(True)
                elif next_key == ord("q"):
                    self.stdscr.keypad(0)
                    curses.echo()
                    curses.nocbreak()
                    curses.curs_set(1)
                    curses.endwin()
                elif key == curses.KEY_RIGHT and next_key != curses.KEY_LEFT \
                    or key == curses.KEY_LEFT and next_key != curses.KEY_RIGHT \
                    or key == curses.KEY_DOWN and next_key != curses.KEY_UP \
                    or key == curses.KEY_UP and next_key != curses.KEY_DOWN:
                    key = next_key
                else:
                    pass
        except Exception as err:
            print(err)
        finally:
            return key

    def run(self):
        try:
            # 初始化贪吃蛇的位置
            sn_x = int(self.win_snake_width / 4)
            sn_y = int(self.win_snake_heigth / 2)
            snake = [[sn_y, sn_x], [sn_y, sn_x - 1], [sn_y, sn_x - 2]]

            # 初始化食物
            self.generate_food(snake)

            key = curses.KEY_RIGHT  # 设置蛇默认的行走方向，默认输入"右键", 蛇往右走

            while True:
                key = self.get_input(key)

                # 蛇的死亡判断, snake[0]代表蛇头
                if snake[0][0] in [0, self.win_snake_heigth - 1] or snake[0][1] in [0, self.win_snake_width - 1]:  # 撞墙
                    break      # 退出循环，结束游戏
                elif snake[0] in snake[1:]:  # 蛇头碰蛇身的情况
                    break

                # 根据用户的输入更新蛇的移动方向
                temp = snake[0][0]
                temp2 = snake[0][1]
                new_head = [temp, temp2]
                if key == curses.KEY_RIGHT:
                    new_head[1] += 1
                if key == curses.KEY_LEFT:
                    new_head[1] -= 1
                if key == curses.KEY_DOWN:
                    new_head[0] += 1
                if key == curses.KEY_UP:
                    new_head[0] -= 1
                snake.insert(0, new_head)

                # 更新食物的坐标
                if snake[0] == self.food_pos:
                    self.update_side_win()
                    self.generate_food(snake)
                else:
                    # 未吃到食物的情况: 蛇头加１,蛇尾减１
                    tail = snake.pop()
                    self.snake_win.addch(tail[0], tail[1], ' ')    # remove the tail

                # 屏幕刷新新的蛇头
                self.snake_win.addch(snake[0][0], snake[0][1], self.snake_filling_symbol)

        except Exception as err:
            print("error: %s" % err)
        finally:
            self.stdscr.keypad(0)
            curses.echo()
            curses.nocbreak()
            curses.curs_set(1)
            curses.endwin()


if __name__ == '__main__':
    sn = Snake()
    sn.run()
    print("game over!")

