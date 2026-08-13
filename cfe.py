#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件管理器 - 中文不挤压版
解决 EXE 后中文挤压问题：每个中文字符后强制加空格
依赖: pip install windows-curses
运行: python wjgll.py
"""

import os
import sys
import stat
import time
import curses
import subprocess
import ctypes

# ============ Windows 控制台初始化 ============
def init_windows_console():
    """设置 Windows 控制台为 UTF-8 + 等宽字体"""
    if sys.platform != 'win32':
        return
    # UTF-8 代码页
    try:
        os.system('chcp 65001 >nul')
    except:
        pass
    # SetConsoleOutputCP
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except:
        pass
    # 设置 Consolas 字体 (注册表)
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Console",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "FaceName", 0, winreg.REG_SZ, "Consolas")
        winreg.SetValueEx(key, "FontFamily", 0, winreg.REG_DWORD, 54)
        winreg.SetValueEx(key, "FontSize", 0, winreg.REG_DWORD, 0x00100000)  # 16pt
        winreg.CloseKey(key)
    except:
        pass
    # 标准流 UTF-8
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
        sys.stdin.reconfigure(encoding='utf-8')
    except:
        try:
            sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
            sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)
        except:
            pass


# ============ 中文空格核心逻辑 ============

def is_chinese_char(ch):
    """判断一个字符是否是中文字符（CJK 统一汉字范围）"""
    code = ord(ch)
    # CJK Unified Ideographs
    if 0x4E00 <= code <= 0x9FFF:
        return True
    # CJK Unified Ideographs Extension A
    if 0x3400 <= code <= 0x4DBF:
        return True
    # 全角字符区
    if 0xFF00 <= code <= 0xFFEF:
        return True
    # CJK Symbols and Punctuation
    if 0x3000 <= code <= 0x303F:
        return True
    return False


def is_wide_char(ch):
    """判断是否是宽字符（占2列）"""
    if is_chinese_char(ch):
        return True
    code = ord(ch)
    # 韩文
    if 0xAC00 <= code <= 0xD7AF:
        return True
    # 日文假名
    if 0x3040 <= code <= 0x30FF:
        return True
    return False


def add_spaces(name):
    """
    在中文字符后面加一个空格，让显示不挤。
    规则：每个中文字符后面无条件加一个空格。
    多个中文连在一起也会每个后面都有空格。
    """
    result = []
    for i, ch in enumerate(name):
        result.append(ch)
        # 如果当前是宽字符，后面加一个空格
        if is_wide_char(ch):
            result.append(' ')
    return ''.join(result)


def visible_len(s):
    """计算字符串的可见宽度（宽字符算2，ASCII算1）"""
    width = 0
    for ch in s:
        if is_wide_char(ch):
            width += 2
        else:
            width += 1
    return width


def pad_to_width(s, target_width):
    """
    将字符串填充/截断到目标宽度。
    先对原始字符串加空格处理，再按宽度截断。
    """
    # 加空格后的版本
    processed = add_spaces(s)
    # 按可见宽度截断
    if visible_len(processed) <= target_width:
        # 不够宽就补空格
        pad_needed = target_width - visible_len(processed)
        return processed + ' ' * pad_needed
    else:
        # 需要截断
        result = []
        w = 0
        for ch in processed:
            cw = 2 if is_wide_char(ch) else 1
            if w + cw > target_width:
                break
            result.append(ch)
            w += cw
        # 补空格到目标宽度
        while w < target_width:
            result.append(' ')
            w += 1
        return ''.join(result)


# ============ 盘符获取 ============
def get_drives():
    """获取所有可用盘符，返回 [(letter, label, free_gb)]"""
    drives = []
    if sys.platform == 'win32':
        try:
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if mask & (1 << i):
                    letter = chr(ord('A') + i) + ':\\'
                    label = ''
                    free = 0
                    try:
                        import shutil
                        usage = shutil.disk_usage(letter)
                        free = usage.free / (1024**3)
                        # 拿卷标
                        buf = ctypes.create_unicode_buffer(256)
                        if ctypes.windll.kernel32.GetVolumeInformationW(
                            ctypes.c_wchar_p(letter),
                            buf, 256, None, None, None, None, 0
                        ):
                            label = buf.value
                    except:
                        pass
                    drives.append((letter, label, free))
        except:
            for d in 'CDEFGH':
                p = d + ':\\'
                if os.path.exists(p):
                    drives.append((p, '', 0))
    else:
        drives.append(('/', 'root', 0))
        for mp in ['/mnt', '/media', '/home']:
            if os.path.exists(mp):
                try:
                    for entry in os.listdir(mp):
                        fp = os.path.join(mp, entry)
                        if os.path.ismount(fp) or os.path.isdir(fp):
                            drives.append((fp, entry, 0))
                except:
                    pass
    return drives


# ============ 文件类型分类 ============
def classify(name):
    ext = os.path.splitext(name)[1].lower()
    if ext in ('.exe','.bat','.com','.sh'): return 'exec'
    if ext in ('.zip','.rar','.7z','.tar','.gz','.bz2'): return 'archive'
    if ext in ('.png','.jpg','.jpeg','.gif','.bmp','.ico'): return 'img'
    if ext in ('.py','.js','.html','.css','.cpp','.c','.java','.go','.rs','.ts','.php','.rb'): return 'code'
    return 'file'


# ============ 安全绘制 ============
def safe_addstr(win, y, x, text, attr=0, max_width=None):
    """安全绘制文本，自动截断到 max_width"""
    if max_width is not None:
        text = pad_to_width(text, max_width)
    else:
        # 默认按窗口宽度
        try:
            _, w = win.getmaxyx()
            text = pad_to_width(text, w - x - 1)
        except:
            pass
    try:
        win.addstr(y, x, text, attr)
    except:
        try:
            win.addstr(y, x, text.encode('ascii', errors='replace').decode(), attr)
        except:
            pass


# ============ 主程序 ============
class FM:
    MODE_NORMAL = 0
    MODE_DRIVE = 1

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.cwd = os.getcwd()
        self.items = []
        self.idx = 0
        self.scroll = 0
        self.show_hidden = False
        self.detail = False
        self.preview = False
        self.preview_txt = ""
        self.msg = ""
        self.running = True
        self.mode = self.MODE_NORMAL
        self.drives = []
        self.load_dir()

    def load_dir(self):
        try:
            names = os.listdir(self.cwd)
        except PermissionError:
            self.msg = "Permission denied"
            self.items = []
            return
        lst = []
        for n in names:
            if not self.show_hidden and n.startswith('.'):
                continue
            fp = os.path.join(self.cwd, n)
            try:
                st = os.stat(fp)
                is_dir = stat.S_ISDIR(st.st_mode)
                sz = st.st_size
                mt = st.st_mtime
            except:
                is_dir = False
                sz = 0
                mt = 0
            lst.append({
                'name': n,
                'path': fp,
                'is_dir': is_dir,
                'size': sz,
                'mtime': mt,
                'type': 'dir' if is_dir else classify(n),
            })
        lst.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        self.items = lst
        self.idx = 0
        self.scroll = 0
        self.msg = f"{len(lst)} items"

    def enter_drive_view(self):
        self.mode = self.MODE_DRIVE
        self.drives = get_drives()
        self.idx = 0
        self.scroll = 0
        # 高亮当前盘符
        cur = (self.cwd[:2] + ':\\').upper()
        for i, (d, _, _) in enumerate(self.drives):
            if d.upper() == cur:
                self.idx = i
                break
        self.msg = "Drive select - Enter to enter, Esc to cancel"

    def load_drives_view(self):
        self.enter_drive_view()

    def go_up(self):
        if self.mode == self.MODE_DRIVE:
            self.mode = self.MODE_NORMAL
            self.msg = "Cancelled"
            return
        # Windows 根目录判断
        c = self.cwd.upper().rstrip('\\/')
        if len(c) <= 2 and c.endswith(':'):
            # 已经在根目录，进盘符视图
            self.enter_drive_view()
            return
        parent = os.path.dirname(self.cwd)
        if parent and parent != self.cwd:
            self.cwd = parent
            self.load_dir()
            self.msg = f"Up: {parent}"

    def open_item(self):
        if not self.items:
            return
        it = self.items[self.idx]
        if it['is_dir']:
            self.cwd = it['path']
            self.load_dir()
            self.msg = f"Opened: {it['name']}"
        else:
            ext = os.path.splitext(it['name'])[1].lower()
            text_exts = {'.txt','.py','.md','.json','.xml','.html','.css','.js','.log','.ini','.cfg','.yml','.yaml','.csv','.conf'}
            if ext in text_exts:
                try:
                    with open(it['path'], 'r', encoding='utf-8') as f:
                        self.preview_txt = f.read(2000)
                except:
                    try:
                        with open(it['path'], 'r', encoding='gbk') as f:
                            self.preview_txt = f.read(2000)
                    except:
                        self.preview_txt = "(Cannot read)"
                self.preview = True
                self.msg = f"Preview: {it['name']}"
            else:
                try:
                    if sys.platform == 'win32':
                        os.startfile(it['path'])
                    else:
                        subprocess.run(['xdg-open', it['path']], check=True)
                    self.msg = f"Opened: {it['name']}"
                except:
                    self.msg = "Cannot open"

    def open_drive(self):
        if not self.drives or self.idx >= len(self.drives):
            return
        letter, _, _ = self.drives[self.idx]
        try:
            os.chdir(letter)
            self.cwd = os.getcwd()
            self.mode = self.MODE_NORMAL
            self.load_dir()
            self.msg = f"Entered {letter}"
        except:
            self.msg = f"Cannot access {letter}"

    def fmt_size(self, s):
        if s < 1024: return f"{s}B"
        elif s < 1048576: return f"{s/1024:.1f}K"
        elif s < 1073741824: return f"{s/1048576:.1f}M"
        else: return f"{s/1073741824:.1f}G"

    def draw(self):
        self.stdscr.clear()
        maxy, maxx = self.stdscr.getmaxyx()
        ch = maxy - 4  # 内容区高度

        # ---- 标题栏 ----
        safe_addstr(self.stdscr, 0, 0, "File Manager - D:Drive H:Help Q:Quit",
                    curses.A_REVERSE | curses.A_BOLD, maxx)

        # ---- 路径栏 ----
        if self.mode == self.MODE_DRIVE:
            path_str = "[DRIVE SELECT]"
        else:
            path_str = self.cwd
        safe_addstr(self.stdscr, 1, 0, path_str, curses.A_REVERSE, maxx)

        # ---- 内容区 ----
        if self.mode == self.MODE_DRIVE:
            self._draw_drives(ch, maxx)
        else:
            self._draw_files(ch, maxx)

        # ---- 滚动条 ----
        items = self.drives if self.mode == self.MODE_DRIVE else self.items
        if len(items) > ch:
            barh = max(1, ch * ch // len(items))
            ratio = self.scroll / max(1, len(items) - ch)
            pos = int(ratio * (ch - barh))
            for i in range(ch):
                yy = 2 + i
                if pos <= i < pos + barh:
                    try:
                        self.stdscr.addch(yy, maxx - 1, '#', curses.A_REVERSE)
                    except:
                        pass
                else:
                    try:
                        self.stdscr.addch(yy, maxx - 1, '-', curses.A_DIM)
                    except:
                        pass

        # ---- 底栏 ----
        if self.mode == self.MODE_DRIVE:
            dc = len(self.drives)
            foot = f" Drive mode - {dc} drives - Enter:select Esc:back "
        else:
            dc = sum(1 for it in self.items if it['is_dir'])
            fc = len(self.items) - dc
            foot = f" Up/Dn:move Enter:open Bksp:up D:drives H:help Q:quit | Dirs:{dc} Files:{fc} "
        safe_addstr(self.stdscr, maxy - 2, 0, foot, curses.A_REVERSE, maxx)

        # ---- 消息行 ----
        safe_addstr(self.stdscr, maxy - 1, 0, self.msg, curses.A_BOLD, maxx)

        self.stdscr.refresh()

    def _draw_drives(self, ch, maxx):
        for i in range(ch):
            y = 2 + i
            real = self.scroll + i
            if real >= len(self.drives):
                safe_addstr(self.stdscr, y, 0, "", 0, maxx)
                continue
            letter, label, free = self.drives[real]
            sel = (real == self.idx)
            attr = curses.A_REVERSE if sel else 0
            # 盘符名（去反斜杠显示更干净）
            display = letter.replace('\\', '')
            if label:
                display += f" [{label}]"
            if free > 0:
                display += f" ({free:.0f}GB free)"
            safe_addstr(self.stdscr, y, 0, display, attr, maxx - 1)

    def _draw_files(self, ch, maxx):
        vis = self.items[self.scroll:self.scroll + ch]
        for i, it in enumerate(vis):
            y = 2 + i
            real = self.scroll + i
            sel = (real == self.idx)
            attr = curses.A_REVERSE if sel else 0

            # 图标
            if it['is_dir']:
                icon = "[DIR] "
            else:
                icon = "      "

            name = it['name']

            if self.detail:
                sz = self.fmt_size(it['size'])
                tm = time.strftime("%Y-%m-%d %H:%M", time.localtime(it['mtime']))
                # 名字区域留给约 40 个"位置"（中文占2，英文占1）
                name_field = pad_to_width(name, 38)
                line = f"{icon}{name_field} {sz:>8} {tm}"
            else:
                line = f"{icon}{name}"

            safe_addstr(self.stdscr, y, 0, line, attr, maxx - 1)

        # 清掉剩余行
        for y in range(2 + len(vis), ch + 2):
            safe_addstr(self.stdscr, y, 0, "", 0, maxx)

    def draw_help(self):
        maxy, maxx = self.stdscr.getmaxyx()
        lines = [
            "Help",
            "-----",
            "Up/Dn or J/K : Move",
            "Enter        : Open / Enter drive",
            "Left/Bksp    : Parent dir / Drive list",
            "F5 or R      : Refresh",
            "V            : Toggle detail view",
            "P            : Toggle preview",
            "D            : Drive selector",
            ".            : Toggle hidden files",
            "H            : This help",
            "Q            : Quit",
            "",
            "Press any key...",
        ]
        h = len(lines) + 2
        w = 44
        y = (maxy - h) // 2
        x = (maxx - w) // 2
        try:
            win = curses.newwin(h, w, y, x)
            win.border()
            for i, l in enumerate(lines):
                safe_addstr(win, i + 1, 2, l, 0, w - 4)
            win.refresh()
            win.getch()
            del win
        except:
            pass

    def run(self):
        while self.running:
            self.draw()
            key = self.stdscr.getch()
            maxy, maxx = self.stdscr.getmaxyx()
            ch = maxy - 4

            # ---- 全局按键 ----
            if key in (ord('q'), ord('Q')):
                self.running = False
                continue
            if key in (ord('h'), ord('H')):
                self.draw_help()
                continue

            # ---- 盘符视图 ----
            if self.mode == self.MODE_DRIVE:
                if key in (27, ord('e'), ord('E')):  # ESC or E
                    self.mode = self.MODE_NORMAL
                    self.msg = "Cancelled"
                elif key in (curses.KEY_UP, ord('k')):
                    if self.idx > 0:
                        self.idx -= 1
                        if self.idx < self.scroll:
                            self.scroll = self.idx
                elif key in (curses.KEY_DOWN, ord('j')):
                    if self.idx < len(self.drives) - 1:
                        self.idx += 1
                        if self.idx >= self.scroll + ch:
                            self.scroll = self.idx - ch + 1
                elif key in (ord('\n'), ord('\r'), 10, 13):
                    self.open_drive()
                continue

            # ---- 正常模式按键 ----
            if key in (ord('d'), ord('D')):
                self.enter_drive_view()
            elif key in (curses.KEY_UP, ord('k')):
                if self.idx > 0:
                    self.idx -= 1
                    if self.idx < self.scroll:
                        self.scroll = self.idx
            elif key in (curses.KEY_DOWN, ord('j')):
                if self.idx < len(self.items) - 1:
                    self.idx += 1
                    if self.idx >= self.scroll + ch:
                        self.scroll = self.idx - ch + 1
            elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127, 8):
                self.go_up()
            elif key in (ord('\n'), ord('\r'), 10, 13):
                self.open_item()
            elif key in (curses.KEY_F5, ord('r'), ord('R')):
                self.load_dir()
                self.msg = "Refreshed"
            elif key == ord('v'):
                self.detail = not self.detail
                self.msg = "Detail: " + ("ON" if self.detail else "OFF")
            elif key == ord('p'):
                self.preview = not self.preview
                if not self.preview:
                    self.preview_txt = ""
                self.msg = "Preview: " + ("ON" if self.preview else "OFF")
            elif key == ord('.'):
                self.show_hidden = not self.show_hidden
                self.load_dir()
                self.msg = "Hidden: " + ("SHOW" if self.show_hidden else "HIDE")


def main(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    # 尝试开启彩色（不用也行，这里主要用反色）
    try:
        curses.start_color()
        curses.use_default_colors()
    except:
        pass
    app = FM(stdscr)
    app.run()


if __name__ == '__main__':
    init_windows_console()
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\nError: {e}")
        input("Press Enter to exit...")
