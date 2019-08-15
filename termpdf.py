#!/usr/bin/env python3
# vim:fileencoding=utf-8
"""\
Usage:
    termpdf.py [options] example.pdf

Options:
    -n n, --page-number n
    -v, --version
    -h, --help
"""

__version__ = "0.1.0"
__license__ = "MIT"
__author__ = "David Sanson"
__url__ = "https://github.com/dsanson/termpdf.py"

__viewer_shortcuts__ = """\
Shortcuts:
    j, down, space: forward [count] pages
    k, up:          back [count] pages
    l, right:       forward [count] sections
    h, left:        back [count] sections
    gg:             go to beginning of document
    G:              go to end of document
    [count]G:       go to page [count]
    t:              display table of contents 
    M:              display metadata
    u:              display URLs
    T:              toggle text mode
    r:              rotate [count] quarter turns clockwise
    R:              rotate [count] quarter turns counterclockwise
    a:              toggle alpha transparency
    i:              invert colors
    d:              darken using TINT_COLOR
    ctrl-r:         refresh
    q:              quit
"""

import array
import curses
import fcntl
import fitz
import os
import sys
import termios
import subprocess
import zlib
import shutil
from base64 import standard_b64encode
from collections import namedtuple
from math import ceil

# Keyboard shortcuts
GOTO_PAGE        = {ord("G")}
GOTO             = {ord("g")}
NEXT_PAGE        = {ord("j"), curses.KEY_DOWN, ord(" ")}
PREV_PAGE        = {ord("k"), curses.KEY_UP}
NEXT_CHAP        = {ord("l"), curses.KEY_RIGHT}
PREV_CHAP        = {ord("h"), curses.KEY_LEFT}
OPEN             = {curses.KEY_ENTER, curses.KEY_RIGHT, 10}
SHOW_TOC         = {ord("t")}
SHOW_META        = {ord("M")}
SHOW_URLS        = {ord("u")}
TOGGLE_TEXT_MODE = {ord("T")}
ROTATE_CW        = {ord("r")}
ROTATE_CCW       = {ord("R")}
TOGGLE_ALPHA     = {ord("a")}
TOGGLE_INVERT    = {ord("i")}
TOGGLE_TINT      = {ord("d")}
REFRESH          = {18, curses.KEY_RESIZE}            # CTRL-R
QUIT             = {3, ord("q")}
DEBUG            = {ord("D")}

# Defaults
TINT_COLOR    = "antiquewhite2"
ZINDEX        = -1

URL_BROWSER_LIST = [
    "gnome-open",
    "gvfs-open",
    "xdg-open",
    "kde-open",
    "firefox",
    "w3m",
    "elinks",
    "lynx"
]

URL_BROWSER = None
if sys.platform == "win32":
    URL_BROWSER = "start"
elif sys.platform == "darwin":
    URL_BROWSER = "open"
else:
    for i in VWR_LIST:
        if shutil.which(i) is not None:
            VWR = i
            break

def screen_size_function(fd=None):
    # ans = getattr(screen_size_function, 'ans', None)
    # if ans is None:
    Size = namedtuple('Size', 'rows cols width height cell_width cell_height')
    if fd is None:
        fd = sys.stdout

    def screen_size():
        if screen_size.changed:
            buf = array.array('H', [0, 0, 0, 0])
            fcntl.ioctl(fd, termios.TIOCGWINSZ, buf)
            rows, cols, width, height = tuple(buf)
            cell_width, cell_height = width // (cols or 1), height // (rows or 1)
            screen_size.ans = Size(rows, cols, width, height, cell_width, cell_height)
            screen_size.changed = False
        return screen_size.ans
    screen_size.changed = True
    screen_size.Size = Size
    ans = screen_size_function.ans = screen_size

    return ans

def serialize_gr_command(cmd, payload=None):
   cmd = ','.join('{}={}'.format(k, v) for k, v in cmd.items())
   ans = []
   w = ans.append
   w(b'\033_G'), w(cmd.encode('ascii'))
   if payload:
      w(b';')
      w(payload)
   w(b'\033\\')
   return b''.join(ans)

def write_gr_cmd(cmd, payload=None):
    sys.stdout.buffer.write(serialize_gr_command(cmd, payload))
    sys.stdout.flush()

def write_gr_cmd_with_response(cmd, payload=None):
    write_gr_cmd(cmd, payload)
    resp = b''
    while resp[-2:] != b'\033\\':
        resp += sys.stdin.buffer.read(1)
    if b'OK' in resp:
        return True
    else:
        return False

def write_chunked(cmd, data):
    if cmd['f'] != 100:
        data = zlib.compress(data)
        cmd['o'] = 'z'
    data = standard_b64encode(data)
    while data:
        chunk, data = data[:4096], data[4096:]
        m = 1 if data else 0
        cmd['m'] = m
        write_gr_cmd(cmd, chunk)
        cmd.clear()

# move the cursor to coordinates c,r
def set_cursor(x_place, y_place):
    sys.stdout.buffer.write('\033[{};{}f'.format(y_place, x_place).encode('ascii'))

def set_image_cursor(display_width, display_height, ss_width, ss_height):
    screen_size = screen_size_function()
    x_place_pixels = (ss_width / 2) - (display_width / 2)
    x_place = int(ceil(x_place_pixels / screen_size().cell_width) - 1)
    x_place = max(0,x_place)
    y_place_pixels = (ss_height / 2) - (display_height / 2)
    y_place = int(ceil(y_place_pixels / screen_size().cell_height) - 1)
    y_place = max(0,y_place)
    set_cursor(x_place, y_place)

# place a string at coordinates c,r
def place_string(c,r,string):
    set_cursor(c,r)
    sys.stdout.write(string)
    sys.stdout.flush()

def clear_screen():
    sys.stdout.buffer.write('\033[2J'.encode('ascii'))
    # subprocess.run('clear')
    # using the key code seems to work the best of the options.

def clear_page(n):
    # this does not delete the page from kitty's memory;
    # it just removes it from the display.
    cmd = {'a': 'd', 'd': 'a', 'i': n + 1}
    write_gr_cmd(cmd)

def display_page(doc, n, opts):
    global is_stale
    page = doc.loadPage(n)

    screen_size = screen_size_function()
    ss_width = screen_size().width
    ss_height = (screen_size().height - screen_size().cell_height)

    # if the image is going to be rotated, swap width and height
    if opts["rotation"] == 0 or opts["rotation"] == 180:
        page_width = page.bound().width
        page_height = page.bound().height
    else:
        page_width = page.bound().height
        page_height = page.bound().width
    
    # calculate the proper zoom factor
    x_factor = ss_width / page_width
    y_factor = ss_height / page_height
    factor = min(x_factor, y_factor)

    # calculate the dimensions of the zoomed image
    display_width = factor * page_width
    display_height = factor * page_height

    # move the cursor to the proper location
    set_image_cursor(display_width, display_height, ss_width, ss_height)

    # If the image is already in memory and not stale, display it.
    # Otherwise, transfer it.
    cmd = {'a': 'p', 'i': n + 1, 'z': ZINDEX}
    if is_stale[n] or not write_gr_cmd_with_response(cmd):
        # Generate a matrix and use it to generate a Pixmap
        mat = fitz.Matrix(factor, factor)
        mat = mat.preRotate(opts["rotation"])
        pix = page.getPixmap(matrix = mat, alpha=opts["alpha"])

        # start building the command for transfering the image
        cmd = {'i': n + 1, 't': 'd', 's': pix.width, 'v': pix.height}
        # if alpha transparency is enabled, the image is 32 bit RGBA,
        # otherwise, 24 bit RGB.
        if opts["alpha"]:
            cmd['f'] = 32
        else:
            cmd['f'] = 24

        # apply tint or color inversion?
        if opts["tint"]:
            tint = fitz.utils.getColor(TINT_COLOR)
            red = int(tint[0] * 256)
            blue = int(tint[1] * 256)
            green = int(tint[2] * 256)
            pix.tintWith(red,blue,green)
        if opts["invert"]:
            pix.invertIRect()

        # transfer the image
        write_chunked(cmd, pix.samples)

        # display the image
        cmd = {'a': 'p', 'i': n + 1, 'z': ZINDEX}
        if write_gr_cmd_with_response(cmd):
            # the image is no longer stale!
            is_stale[n] = False
        else:
            # silently fail
            pass

def clean_quit(stdscr, doc):
    # delete all the images from kitty's memory
    cmd = {'a': 'd', 'd': 'Z', 'z': ZINDEX}
    write_gr_cmd(cmd)

    # close curses
    stdscr.keypad(False)
    curses.echo()
    curses.curs_set(1)
    curses.endwin()
    
    # close the document
    doc.close()

    raise SystemExit()

def update_status_bar(doc, n, cmd, message):
    # pages start from 1, not 0!
    p = str(n + 1)
    t = doc.pageCount

    screen_size = screen_size_function()
    c = screen_size().cols
    r = screen_size().rows

    # echo the command, with some padding to clear old commands
    left_bar = cmd + " " * 10
    place_string(1,r,left_bar)
    # center bar for messages
    center_bar = message
    offset = ceil((c / 2) - (len(message) / 2)) - 1
    place_string(offset,r,center_bar)
    # [current page/total pages]
    right_bar = '     [{}/{}]'.format(p, t)
    offset = c - len(right_bar)
    place_string(offset,r,right_bar)
    # move the cursor back to the left
    set_cursor(len(cmd) + 2,r)
    sys.stdout.flush()

# This is a curses status bar, but it doesn't seem
# to play nice with image drawing, so it isn't used.
def update_status_bar_c(status_bar, doc, n, cmd, message):
    p = str(n + 1)
    t = doc.pageCount
    r, c = status_bar.getmaxyx()
    left_bar = cmd + " " * 10 
    status_bar.addstr(0,5,left_bar)
    right_bar = '     [{}/{}]'.format(p, t)
    offset = c - len(right_bar)
    status_bar.addstr(0,offset,right_bar)
    return status_bar

# Whenever we resize or tint or rotate or whatever,
# we mark all the pages as stale, so that we know
# to regenerate them.
def mark_all_pages_as_stale(pages):
    global is_stale
    is_stale = [True] * (pages + 1)

# Movement functions

def next_chapter(doc, n, count=1):
    toc = doc.getToC()
    if toc:
        for ch in toc:
            ch_page = ch[2] - 1
            if ch_page > n:
                count -= 1
            if count == 0:
                return ch_page 
        return ch_page # go to last chapter 
    else:
        return n

def prev_chapter(doc, n, count=1):
    toc = doc.getToC()
    if toc:
        for ch in reversed(toc):
            ch_page = ch[2] - 1
            if ch_page < n:
                count -= 1
            if count == 0:
                return ch_page 
        return ch_page # go to first chapter 
    else:
        return n

def goto_page(doc, target):
    pages = doc.pageCount - 1
    if target > pages:
        target = pages
    elif target < 0:
        target = 0
    return target

# TODO: Searching
def search_page(doc, current, search):
    results = doc.searchPageFor(current, search)
    clear_screen()
    print(results)
    raise SystemExit

def center_string(string, width):
    return '{:^{width}}'.format(string, width=width)

def show_toc(stdscr,doc,n):

    toc = doc.getToC()

    if not toc:
        return n, "No ToC available."
    else:
        is_stale[n] = True
        clear_page(n)
        clear_screen()

        screen_size = screen_size_function()
        cols = screen_size().cols
        rows = screen_size().rows

        hi, wi = rows - 6, min(cols - 4, 80)
        Y, X = 2, ceil((cols / 2) - (wi / 2))
        toc_win = curses.newwin(hi, wi, Y, X)
        toc_win.box()
        toc_win.keypad(True)
        header = 'Table of Contents'
        toc_win.addstr(1,2, center_string(header, wi - 4))
        toc_win.addstr(2,2, center_string('-' * len(header), wi - 4))

        stdscr.clear()
        stdscr.refresh()
        toc_win.refresh()

        def get_current_chapter(toc, n):
            for i, ch in enumerate(toc):
                ch_page = ch[2] - 1
                if ch_page > n:
                    return i - 1
        current_chapter = get_current_chapter(toc, n)

        toc_pad = curses.newpad(len(toc), 200)
        toc_pad.keypad(True)

        span = []
        for i, ch in enumerate(toc):
            toc_text = '{}{}'.format("  " * ch[0], ch[1])
            toc_pad.addstr(i,0,toc_text)
            span.append(len(toc_text))
      
        index = current_chapter
        while True:
            for i, ch in enumerate(toc):
                att = curses.A_REVERSE if index == i else curses.A_NORMAL
                toc_pad.chgat(i, 0, span[i], att)
            toc_pad.refresh(1, 0, Y + 3, X + 2, hi - 2, wi - 2)
            key = toc_pad.getch()
            if key in QUIT:
                clear_screen()
                return n, ""
            if key in NEXT_PAGE:
                index = min(len(toc) - 1, index + 1)
            if key in PREV_PAGE:
                index = max(0, index - 1)
            if key in OPEN:
                clear_screen()
                return toc[index][2] - 1, ""

def show_metadata(stdscr,doc,n):

    metadata = doc.metadata
    
    if len(metadata) == 0: 
        return n, "No Metadata available."
    else:
        is_stale[n] = True
        clear_page(n)

        screen_size = screen_size_function()
        cols = screen_size().cols
        rows = screen_size().rows

        hi, wi = rows - 6, min(cols - 4, 80)
        Y, X = 2, ceil((cols / 2) - (wi / 2))
        meta_win = curses.newwin(hi, wi, Y, X)
        meta_win.box()
        meta_win.keypad(True)
        header = 'Metadata'
        meta_win.addstr(1,2, center_string(header, wi - 4))
        meta_win.addstr(2,2, center_string('-' * len(header), wi - 4))

        stdscr.clear()
        stdscr.refresh()
        meta_win.refresh()
        

        meta_pad = curses.newpad(len(metadata), 200)
        meta_pad.keypad(True)

        span = []
        for i,key in enumerate(metadata):
            str = '{}: {}'.format(key, metadata[key])
            meta_pad.addstr(i,0,str)
            span.append(len(str))
      
        index = 1
        while True:
            for i, k in enumerate(metadata):
                att = curses.A_REVERSE if index == i else curses.A_NORMAL
                meta_pad.chgat(i, 0, span[i], att)
            meta_pad.refresh(0, 0, Y + 3, X + 2, hi - 2, wi - 2)
            key = meta_pad.getch()
            if key in QUIT:
                clear_screen()
                return
            if key in NEXT_PAGE:
                index = min(len(metadata) - 1, index + 1)
            if key in PREV_PAGE:
                index = max(0, index - 1)
            if key in OPEN:
                #TODO: edit fields
                pass

def show_urls(stdscr, doc, n):

    page = doc.loadPage(n)
    refs = page.getLinks()
    urls = []
    pad_width = 20
    for ref in refs:
        if ref['kind'] == 2:
            u = ref['uri']
            l = len(u)
            urls = urls + [u]
            pad_width = max(pad_width, l + 2)
    if len(urls) == 0:
        return "No URLs on page"
    else:
        is_stale[n] = True
        clear_page(n)
        clear_screen()

        screen_size = screen_size_function()
        cols = screen_size().cols
        rows = screen_size().rows

        hi, wi = rows - 6, min(cols - 4, 80)
        Y, X = 2, ceil((cols / 2) - (wi / 2))
        url_win = curses.newwin(hi, wi, Y, X)
        url_win.box()
        url_win.keypad(True)
        header = 'URLs'
        url_win.addstr(1,2, center_string(header, wi - 4))
        url_win.addstr(2,2, center_string('-' * len(header), wi - 4))

        stdscr.clear()
        stdscr.refresh()
        url_win.refresh()
       
        url_pad = curses.newpad(len(urls), pad_width)
        url_pad.keypad(True)

        span = []
        for i, url in enumerate(urls):
            url_pad.addstr(i,0,url)
            span.append(len(url))
         
        index = 0
        while True:
            for i, url in enumerate(urls):
                att = curses.A_REVERSE if index == i else curses.A_NORMAL
                url_pad.chgat(i, 0, span[i], att)
            url_pad.refresh(0, 0, Y + 3, X + 2, hi - 2, wi - 2)
            key = url_pad.getch()
            if key in QUIT:
                clear_screen()
                return ""
            if key in NEXT_PAGE:
                index = min(len(url) - 1, index + 1)
            if key in PREV_PAGE:
                index = max(0, index - 1)
            if key in OPEN:
                clear_screen()
                subprocess.run([URL_BROWSER, urls[i]], check=True)
                return ""



# TODO: Annotations
# TODO: Bookmarks
# TODO: Open links
# TODO: Fill in Forms
# TODO: Keyboard Visual Mode
# TODO: Mouse Mode
# TODO: Thumbnail Mode
# TODO: OCR

def text_viewer(stdscr,doc,n):

    from textwrap import wrap 
    clear_page(n)

    screen_size = screen_size_function()
    cols = screen_size().cols
    rows = screen_size().rows

    width = min(80, cols - 2)
    height = rows - 2
    x_offset = ceil((cols / 2) - (width / 2))
    y_offset = 0

    pages = doc.pageCount - 1

    while True:
        page_text = doc.getPageText(n,"text")
        page_text = wrap(page_text,width)

        text_pad = curses.newpad(len(page_text), width)
        text_pad.keypad(True)
        
        for i,line in enumerate(page_text):
            text_pad.addstr(i,0,line)
        
        last = int(len(page_text) / height)
       

        message = ""
        key = 0 
        stack = [0]
        count_string = ""
        index = 0
        change_page = False
        while not change_page:
            stdscr.clear()
            stdscr.refresh()
            text_pad.refresh(index * height, 0, y_offset, x_offset, y_offset + height, x_offset + width)
            #update_status_bar(doc, n, count_string + chr(key), message) # echo input
            # set count based on count_string
            if count_string == "":
                count = 1
            else:
                count = int(count_string)

            key = text_pad.getch()

            if key == 27: # ESC
                update_status_bar(doc, n, "", message)
            elif 32 < key < 256: # printable characters
                update_status_bar(doc, n, count_string + chr(key), message) # echo input

            # perform actions based on keyacter commands
            if key == -1:
                pass
            if key in range(48, 57): # increment count_string
                count_string = count_string + chr(key)
            else:
                if key in QUIT:
                    clean_quit(stdscr, doc)
                if key in TOGGLE_TEXT_MODE:
                    clear_screen()
                    return n
                elif key in GOTO_PAGE:
                    if count_string != "":
                       target = count - 1
                    else: 
                       target = pages
                    n = goto_page(doc, target)
                    change_page = True
                    stack = [0]
                    stack = [0] 
                elif key in NEXT_PAGE:
                    index += 1
                    if index > last:
                        target = n + 1
                        n = goto_page(doc, target)
                        change_page = True
                    stack = [0]
                elif key in PREV_PAGE:
                    index -= 1
                    if index < 0:
                        target = n - 1
                        n = goto_page(doc, target)
                        change_page = True
                    stack = [0]
                    stack = [0]
                elif key in NEXT_CHAP:
                    target = next_chapter(doc, n, count)
                    n = goto_page(doc, target)
                    change_page = True
                    stack = [0] 
                elif key in PREV_CHAP:
                    target = prev_chapter(doc, n, count)
                    n = goto_page(doc, target)
                    change_page = True
                    stack = [0] 
                elif stack[0] in GOTO and key in GOTO:
                    n = goto_page(doc, 0)
                    change_page = True
                    stack = [0] 
                elif key in SHOW_TOC:
                    target, message = show_toc(stdscr,doc, n)
                    n = goto_page(doc, target)
                    change_page = True
                    stack = [0] 
                elif key in SHOW_META:
                    show_metadata(stdscr,doc, n) 
                    stack = [0] 
                else:
                    stack = [key] + stack
                count_string = ""


def viewer(doc, n=0):

    stdscr = curses.initscr()
    stdscr.clear()
    curses.noecho()
    curses.curs_set(0) 
    stdscr.keypad(True) # Handle our own escape codes for now
    #stdscr.timeout(-1)
    stdscr.nodelay(True)
    stdscr.getch()
    # status_bar = curses.newwin(0,c - 1,r - 1,1)

    pages = doc.pageCount - 1

    # if n is negative, then open n pages from the end of the doc
    if n < 0:
        n = max(pages + n, 0)

    mark_all_pages_as_stale(pages)
    m = -1
    stack = [0] 
    count_string = ""
    message = ""
    opts = {"rotation": 0, "alpha": False, "invert": False, "tint": False}
   
    
    runs = 0

    while True:

        # reload the after the first time, since getch seems to clobber
        # the image the first time around.
        if runs < 1:
            is_stale[n]
            runs = runs + 1
        else:
            stdscr.nodelay(False)

        # only update image when changed page or image is stale
        if m != n or is_stale[n]:
            display_page(doc, n, opts)

        # only update status bar when page or message changed    
        if m != n or message != old_message:
            update_status_bar(doc, n,"", message)

        # reset change tracking
        m = n
        old_message = message

        # set count based on count_string
        if count_string == "":
            count = 1
        else:
            count = int(count_string)
 
        # get char
        char = stdscr.getch()

        # echo char to status_bar and clobber escape codes
        if char == 27: # ESC
            update_status_bar(doc, n, "", message)
        elif stack[0] == 27 and chr(char) == "_": # clobber ESC code
            message = 'STUCK: Press ESC\\ to resume.'
            update_status_bar(doc, n, "", message)
            r = b''
            while r[-2:] != b'\033\\':
                r += sys.stdin.buffer.read(1)
            update_status_bar(doc, n, '', ' ' * len(message))
            message = ""
            count_string = "" 
            stack = [0] 
        elif 32 < char < 256: # printable characters
            update_status_bar(doc, n, count_string + chr(char), message) # echo input

        # perform actions based on character commands
        if char == -1:
            pass
        if char in range(48, 57): # increment count_string
            count_string = count_string + chr(char)
        else:
            if char in QUIT: 
                clean_quit(stdscr, doc)
            elif char in GOTO_PAGE:
                if count_string != "":
                   target = count - 1
                else: 
                   target = pages
                n = goto_page(doc, target)
                stack = [0] 
            elif char in NEXT_PAGE:
                target = n + count
                n = goto_page(doc, target)
                stack = [0] 
            elif char in PREV_PAGE:
                target = n - count
                n = goto_page(doc, target)
                stack = [0] 
            elif char in NEXT_CHAP:
                target = next_chapter(doc, n, count)
                n = goto_page(doc, target)
                stack = [0] 
            elif char in PREV_CHAP:
                target = prev_chapter(doc, n, count)
                n = goto_page(doc, target)
                stack = [0] 
            elif stack[0] in GOTO and char in GOTO:
                n = goto_page(doc, 0)
                stack = [0] 
            elif char in ROTATE_CW:
                opts["rotation"] = (opts["rotation"] + 90 * count) % 360
                mark_all_pages_as_stale(pages)
                stack = [0] 
            elif char in ROTATE_CCW:
                opts["rotation"] = (opts["rotation"] - 90 * count) % 360
                mark_all_pages_as_stale(pages)
                stack = [0] 
            elif char in TOGGLE_ALPHA:
                opts["alpha"] = not opts["alpha"]
                mark_all_pages_as_stale(pages)
                stack = [0] 
            elif char in TOGGLE_INVERT:
                opts["invert"]  = not opts["invert"]
                mark_all_pages_as_stale(pages)
                stack = [0] 
            elif char in TOGGLE_TINT:
                opts["tint"] = not opts["tint"]
                mark_all_pages_as_stale(pages)
                stack = [0] 
            elif char in SHOW_TOC:
                target, message = show_toc(stdscr,doc, n)
                n = goto_page(doc, target)
                stack = [0] 
            elif char in SHOW_META:
                show_metadata(stdscr,doc, n) 
                stack = [0] 
            elif char in SHOW_URLS:
                message = show_urls(stdscr,doc,n)
                stack = [0]
            elif char in TOGGLE_TEXT_MODE:
                n = text_viewer(stdscr,doc,n)
                is_stale[m] = True
                stack = [0] 
            elif char in REFRESH: # Ctrl-R
                mark_all_pages_as_stale(pages)
            elif char in DEBUG:
                # a spot for messing around with ideas
                # search_page(doc, n, "the")
                pass
            else:
                stack = [char] + stack
            
            if m != n or is_stale[m]:
                clear_page(m)
            count_string = ""

def parse_args(args):
    if len({"-h", "--help"} & set(args)) != 0:
        hlp = __doc__.rstrip()
        print(hlp)
        print()
        print(__viewer_shortcuts__)
        raise SystemExit()
    if len({"-v", "--version", "-V"} & set(args)) != 0:
        print(__version__)
        print(__license__, "License")
        print("Copyright (c) 2019", __author__)
        print(__url__)
        raise SystemExit()

    n = 0 # open first page by default

    items = []
    skip = False
    for i,arg in enumerate(args):
        if skip:
            skip = not skip
        elif arg in {'-n', '--page-number'}:
            try:
                n = int(args[i + 1])
                n = n - 1 # page indexing starts at 0
                skip = True
            except:
                print(args)
                raise SystemExit('no page number specified')
        else:
            items = items + [arg]

    if len(items) > 1:
        print("Warning: only opening the first file...")
                
    return items[0], n


def main(args=sys.argv):
    global is_stale
    is_stale = []

    item, n = parse_args(args[1:])


    screen_size = screen_size_function()
    if screen_size().width == 0:
        raise SystemExit(
            'Terminal does not support reporting screen sizes via the TIOCGWINSZ ioctl'
        )

    try:
        doc = fitz.open(item)
    except:
        raise SystemExit('Unable to open "{}".'.format(item))

    viewer(doc, n)

if __name__ == '__main__':
    main()

