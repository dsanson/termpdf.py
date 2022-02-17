#!/usr/bin/env python3
# vim:fileencoding=utf-8
"""\
Usage:
    termpdf.py [options] example.pdf

Options:
    -p n, --page-number n : open to page n
    -f n, --first-page n : set logical page number for page 1 to n
    --citekey key : associate file with bibtex citekey
    -o, --open citekey : open file associated with bibtex entry with citekey
    --nvim-listen-address path : path to nvim msgpack server
    --ignore-cache : ignore saved settings for files
    -v, --version
    -h, --help
"""

__version__ = "0.1.1"
__license__ = "MIT"
__copyright__ = "Copyright (c) 2019"
__author__ = "David Sanson"
__url__ = "https://github.com/dsanson/termpdf.py"

__viewer_shortcuts__ = """\
Keys:
    j, down, space: forward [count] pages
    k, up:          back [count] pages
    l, right:       forward [count] sections
    h, left:        back [count] sections
    gg:             go to beginning of document
    G:              go to end of document
    [count]G:       go to page [count]
    b:		    cycle through open documents
    s:              visual mode
    t:              table of contents 
    M:              show metadata
    f:              show links on page
    r:              rotate [count] quarter turns clockwise
    R:              rotate [count] quarter turns counterclockwise
    c:              toggle autocropping of margins
    a:              toggle alpha transparency
    i:              invert colors
    d:              darken using TINT_COLOR
    [count]P:       Set logical page number of current page to count
    -:              zoom out (reflowable only)
    +:              zoom in (reflowable only)
    ctrl-r:         refresh
    q:              quit
"""


import re
import array
import curses
import fcntl
import fitz
import os
import sys
import logging
import termios
import threading
import subprocess
import zlib
import shutil
import select
import hashlib
import string
import json
import roman
import pyperclip
from time import sleep, monotonic
from base64 import standard_b64encode
from operator import attrgetter
from collections import namedtuple
from math import ceil
from tempfile import NamedTemporaryFile


# Class Definitions

class Config:
    def __init__(self):
        self.BIBTEX = ''
        #self.KITTYCMD = 'kitty --single-instance --instance-group=1' # open notes in a new OS window
        self.KITTYCMD = 'kitty @ new-window' # open notes in split kitty window
        self.TINT_COLOR = 'antiquewhite2'
        self.URL_BROWSER_LIST = [
            'gnome-open',
            'gvfs-open',
            'xdg-open',
            'kde-open',
            'firefox',
            'w3m',
            'elinks',
            'lynx'
        ]
        self.URL_BROWSER = None
        self.GUI_VIEWER = 'preview'
        self.NOTE_PATH = os.path.join(os.getenv("HOME"), 'inbox.org')

    def browser_detect(self):
        if sys.platform == 'darwin':
            self.URL_BROWSER = 'open'
        else:
            for i in self.URL_BROWSER_LIST:
                if shutil.which(i) is not None:
                    self.URL_BROWSER = i
                    break
    
    def load_config_file(self):
        config_file = os.path.expanduser(os.path.join(os.getenv("XDG_CONFIG_HOME", "~/.config"), 'termpdf.py', 'config'))
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                prefs = json.load(f)
            for key in prefs:
                setattr(self, key, prefs[key])

class Buffers:
    def __init__(self):
        self.docs = []
        self.current = 0

    def goto_buffer(self,n):
        l = len(self.docs) - 1
        if n > l:
            n = l
        elif n < 0:
            n = 0
        self.current = n

    def cycle(self, count):
        self.current = (self.current + count) % len(self.docs)

    def close_buffer(self,n):
        del self.docs[n]
        if self.current == n:
            self.current = max(0,n-1)
        if len(self.docs) == 0:
            clean_exit()

class Screen:

    def __init__(self):
        self.rows = 0
        self.cols = 0
        self.width = 0
        self.height = 0
        self.cell_width = 0
        self.cell_height = 0
        self.stdscr = None

    def get_size(self):
        fd = sys.stdout
        buf = array.array('H', [0, 0, 0, 0])
        fcntl.ioctl(fd, termios.TIOCGWINSZ, buf)
        r,c,w,h = tuple(buf)
        cw = w // (c or 1)
        ch = h // (r or 1)
        self.rows = r
        self.cols = c
        self.width = w
        self.height = h
        self.cell_width = cw
        self.cell_height = ch

    def init_curses(self):
        os.environ.setdefault('ESCDELAY', '25')
        self.stdscr = curses.initscr()
        self.stdscr.clear()
        curses.noecho()
        curses.curs_set(0) 
        curses.mousemask(curses.REPORT_MOUSE_POSITION
            | curses.BUTTON1_PRESSED | curses.BUTTON1_RELEASED
            | curses.BUTTON2_PRESSED | curses.BUTTON2_RELEASED
            | curses.BUTTON3_PRESSED | curses.BUTTON3_RELEASED
            | curses.BUTTON4_PRESSED | curses.BUTTON4_RELEASED
            | curses.BUTTON1_CLICKED | curses.BUTTON3_CLICKED
            | curses.BUTTON1_DOUBLE_CLICKED 
            | curses.BUTTON1_TRIPLE_CLICKED
            | curses.BUTTON2_DOUBLE_CLICKED 
            | curses.BUTTON2_TRIPLE_CLICKED
            | curses.BUTTON3_DOUBLE_CLICKED 
            | curses.BUTTON3_TRIPLE_CLICKED
            | curses.BUTTON4_DOUBLE_CLICKED 
            | curses.BUTTON4_TRIPLE_CLICKED
            | curses.BUTTON_SHIFT | curses.BUTTON_ALT
            | curses.BUTTON_CTRL)
        self.stdscr.keypad(True) # Handle our own escape codes for now

        # The first call to getch seems to clobber the statusbar.
        # So we make a dummy first call.
        self.stdscr.nodelay(True)
        self.stdscr.getch()
        self.stdscr.nodelay(False)

    def create_text_win(self, length, header):
        # calculate dimensions
        w = max(self.cols - 4, 60)
        h = self.rows - 2
        x = int(self.cols / 2 - w / 2)
        y = 1

        win = curses.newwin(h,w,y,x)
        win.box()
        win.addstr(1,2, '{:^{l}}'.format(header, l=(w-3)))
        
        self.stdscr.clear()
        self.stdscr.refresh()
        win.refresh()
        pad = curses.newpad(length,1000)
        pad.keypad(True)
        
        return win, pad

    def swallow_keys(self):
        self.stdscr.nodelay(True)
        k = self.stdscr.getch()
        end = monotonic() + 0.1
        while monotonic() < end:
            self.stdscr.getch()
        self.stdscr.nodelay(False)

    def clear(self):
        sys.stdout.buffer.write('\033[2J'.encode('ascii'))

    def set_cursor(self,c,r):
        if c > self.cols:
            c = self.cols
        elif c < 0:
            c = 0
        if r > self.rows:
            r = self.rows
        elif r < 0:
            r = 0
        sys.stdout.buffer.write('\033[{};{}f'.format(r, c).encode('ascii'))

    def place_string(self,c,r,string):
        self.set_cursor(c,r)
        sys.stdout.write(string)
        sys.stdout.flush()


def get_filehash(path):
    blocksize = 65536
    hasher = hashlib.md5()
    with open(path, 'rb') as afile:
        buf = afile.read(blocksize)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(blocksize)
    return hasher.hexdigest()

def get_cachefile(path):
    filehash = get_filehash(path)
    cachedir = os.path.expanduser(os.path.join(os.getenv("XDG_CACHE_HOME", "~/.cache"), 'termpdf.py'))
    os.makedirs(cachedir, exist_ok=True)
    cachefile = os.path.join(cachedir, filehash)
    return cachefile

class Document(fitz.Document):
    """
    An extension of the fitz.Document class, with extra attributes
    """
    def __init__(self, filename=None, filetype=None, rect=None, width=0, height=0, fontsize=12):
        fitz.Document.__init__(self, filename, None, filetype, rect, width, height, fontsize)
        self.filename = filename
        self.citekey = None
        self.papersize = 3
        self.layout(rect=fitz.paper_rect('A6'),fontsize=fontsize)
        self.page = 0
        self.logicalpage = 1
        self.prevpage = 0
        self.pages = self.page_count - 1
        self.first_page_offset = 1
        self.logical_pages = list(range(0 + self.first_page_offset, self.pages + self.first_page_offset))
        self.chapter = 0
        self.rotation = 0
        self.fontsize = fontsize
        self.width = width
        self.height = height
        self.autocrop = False
        self.manualcrop = False
        self.manualcroprect = [None,None]
        self.alpha = False
        self.invert = False
        self.tint = False
        self.tint_color = config.TINT_COLOR
        self.nvim = None
        self.nvim_listen_address = '/tmp/termpdf_nvim_bridge'
        self.page_states = [ Page_State(i) for i in range(0,self.pages + 1) ]

    def write_state(self):
        cachefile = get_cachefile(self.filename)
        state = {'citekey': self.citekey,
                 'papersize': self.papersize,
                 'page': self.page,
                 'logicalpage': self.logicalpage,
                 'first_page_offset': self.first_page_offset,
                 'chapter': self.chapter,
                 'rotation': self.rotation,
                 'autocrop': self.autocrop,
                 'manualcrop': self.manualcrop,
                 'manualcroprect': self.manualcroprect,
                 'alpha': self.alpha,
                 'invert': self.invert,
                 'tint': self.tint}
        with open(cachefile, 'w') as f:
            json.dump(state, f)

    def goto_page(self, p):
        # store prevpage 
        self.prevpage = self.page
        # delete prevpage
        # self.clear_page(self.prevpage)
        # set new page
        if p > self.pages:
            self.page = self.pages
        elif p < 0:
            self.page = 0
        else:
            self.page = p
        self.logicalpage = self.page_to_logical(self.page)
    
    def goto_logical_page(self, p):
        p = self.logical_to_page(p)
        self.goto_page(p)

    def next_page(self, count=1):
        self.goto_page(self.page + count)

    def prev_page(self, count=1):
        self.goto_page(self.page - count)

    def goto_chap(self, n):
        toc = self.get_toc()
        if n > len(toc):
            n = len(toc)
        elif n < 0:
            n = 0
        self.chapter = n
        try:
            self.goto_page(toc[n][2] - 1)
        except:
            self.goto_page(0)

    def current_chap(self):
        toc = self.get_toc()
        p = self.page
        for i,ch in enumerate(toc):
           cp = ch[2] - 1
           if cp > p:
               return i - 1
        return len(toc)

    def next_chap(self, count=1):
        self.goto_chap(self.chapter + count)

    def prev_chap(self, count=1):
        self.goto_chap(self.chapter - count)

    def parse_pagelabels(self):
        if self.is_pdf:
            from pdfrw import PdfReader
            from pagelabels import PageLabels, PageLabelScheme
            try:
                reader = PdfReader(self.filename)
                labels = PageLabels.from_pdf(reader)
                labels = sorted(labels, key=attrgetter('startpage'))
            except:
                labels = []
        else:
            labels = []
        return labels

    def set_pagelabel(self,count,style="arabic"):
        if self.is_pdf:
            from pdfrw import PdfReader, PdfWriter
            from pagelabels import PageLabels, PageLabelScheme
            reader = PdfReader(self.filename)
            labels = PageLabels.from_pdf(reader)
            newlabels = PageLabels()
            for label in labels:
                if label.startpage != self.page:
                    newlabels.append(label)

            newlabel = PageLabelScheme(startpage=self.page, 
                                       style=style,
                                       prefix="",
                                       firstpagenum=count) 
            newlabels.append(newlabel) 
            newlabels.write(reader)

            writer = PdfWriter()
            writer.trailer = reader
            logging.debug("writing new pagelabels...")
            writer.write(self.filename)

    # unused; using pdfrw instead
    def parse_pagelabels_pure(self):
        cat = self._getPDFroot()

        cat_str = self._getXrefString(cat)
        lines = cat_str.split('\n')
        labels = []
        for line in lines:
            match = re.search('/PageLabels',line)
            if re.match(r'.*/PageLabels.*', line):
                labels += [line]
        logging.debug(labels)
        raise SystemExit

    def pages_to_logical_pages(self):
        labels = self.parse_pagelabels()
        self.logical_pages = list(range(0,self.pages + 1))

        def divmod_alphabetic(n):
            a, b = divmod(n, 26)
            if b == 0:
                return a - 1, b + 26
            return a, b

        def to_alphabetic(n):
            chars = []
            while n > 0:
                n, d = divmod_alphabetic(n)
                chars.append(string.ascii_uppercase[d - 1])
            return ''.join(reversed(chars))

        if labels == []:
            for p in range(0,self.pages + 1):
                self.logical_pages[p] = str(p + self.first_page_offset)
        else:
            for p in range(0,self.pages + 1):
                for label in labels:
                    if p >= label.startpage:
                        lp = (p - label.startpage) + label.firstpagenum
                        style = label.style
                        prefix = label.prefix
                if style == 'roman uppercase':
                    lp = prefix + roman.toRoman(lp)
                    lp = lp.upper()
                elif style == 'roman lowercase':
                    lp = prefix + roman.toRoman(lp)
                    lp = lp.lower()
                elif style == 'alphabetic uppercase':
                    lp = prefix + to_alphabetic(lp) 
                elif style == 'alphabetic lowercase':
                    lp = prefix + to_alphabetic(lp)
                    lp = lp.lower()
                else:
                    lp = prefix + str(lp)
                self.logical_pages[p] = lp 

    def page_to_logical(self, p=None):
        if not p:
            p = self.page
        return self.logical_pages[p]

    def logical_to_page(self, lp=None):
        if not lp:
            lp = self.logicalpage
        try:
            p = self.logical_pages.index(str(lp))
        except:
            # no such logical page in document
            p = 0
        return p

    def make_link(self):
        p = self.page_to_logical(self.page)
        if self.citekey: 
            return '[@{}, {}]'.format(self.citekey, p)
        else:
            return '({}, {}, {})'.format(self.metadata['author'],self.metadata['title'], p)

    def find_target(self, target, target_text):
        # since our pct calculation is at best an estimate
        # of the correct target page, we search for the first 
        # few words of the original page on the surrounding pages
        # until we find a match
        for i in [0,1,-1,2,-2,3,-3,4,-4,5,-5,6,-6]:
            f = target + i
            match_text = self[f].get_text().split()
            match_text = ' '.join(match_text)
            if target_text in match_text:
                return f
        return target


    def set_layout(self,papersize, adjustpage=True):
        # save a snippet of text from current page
        target_text = self[self.page].get_text().split()
        if len(target_text) > 6:
            target_text = ' '.join(target_text[:6])
        elif len(target_text) > 0:
            target_text = ' '.join(target_text)
        else:
            target_text = ''

        pct = (self.page + 1) / (self.pages + 1)
        sizes = ['a7','c7','b7','a6','c6','b6','a5','c5','b5','a4']
        if papersize > len(sizes) - 1:
            papersize = len(sizes) - 1
        elif papersize < 0:
            papersize = 0
        p = sizes[papersize]
        self.layout(fitz.paper_rect(p))
        self.pages = self.page_count - 1
        if adjustpage:
            target = int((self.pages + 1) * pct) - 1
            target = self.find_target(target, target_text)
            self.goto_page(target)
        self.papersize = papersize 
        self.pages_to_logical_pages()

    def mark_all_pages_stale(self):
        self.page_states = [ Page_State(i) for i in range(0,self.pages + 1) ]

    def clear_page(self, p):
        cmd = {'a': 'd', 'd': 'a', 'i': p + 1}
        write_gr_cmd(cmd)

    def cells_to_pixels(self, *coords):
        factor = self.page_states[self.page].factor
        l,t,_,_ = self.page_states[self.page].place
        pix_coords = []
        for coord in coords:
            col = coord[0]
            row = coord[1]
            x = (col - l) * scr.cell_width / factor
            y = (row - t) * scr.cell_height  / factor
            pix_coords.append((x,y))
        return pix_coords

    def pixels_to_cells(self, *coords):
        factor = self.page_states[self.page].factor
        l,t,_,_ = self.page_states[self.page].place
        cell_coords = []
        for coord in coords:
            x = coord[0]
            y = coord[1]
            col = (x * factor + l * scr.cell_width) / scr.cell_width
            row = (y * factor + t * scr.cell_height) / scr.cell_height
            col = int(col)
            row = int(row)
            cell_coords.append((col,row))
        return cell_coords

    # get text that is inside a Rect
    def get_text_in_Rect(self, rect):
        from operator import itemgetter
        from itertools import groupby
        page = self.load_page(self.page)
        words = page.get_text_words()
        mywords = [w for w in words if fitz.Rect(w[:4]) in rect]
        mywords.sort(key=itemgetter(3, 0))  # sort by y1, x0 of the word rect
        group = groupby(mywords, key=itemgetter(3))
        text = [] 
        for y1, gwords in group:
            text = text + [" ".join(w[4] for w in gwords)]
        return text

    # get text that intersects a Rect
    def get_text_intersecting_Rect(self, rect):
        from operator import itemgetter
        from itertools import groupby
        page = self.load_page(self.page)
        words = page.get_text_words()
        mywords = [w for w in words if fitz.Rect(w[:4]).intersects(rect)]
        mywords.sort(key=itemgetter(3, 0))  # sort by y1, x0 of the word rect
        group = groupby(mywords, key=itemgetter(3))
        text = [] 
        for y1, gwords in group:
            text = text + [" ".join(w[4] for w in gwords)]
        return text

    def search_text(self,string):
        for p in range(self.page,self.pages):
            page_text = self.get_page_text(p, 'text')
            if re.search(string,page_text):
                self.goto_page(p)
                return "match on page"
        return "no matches"

    def auto_crop(self,page):
        blocks = page.get_text_blocks()

        if len(blocks) > 0:
            crop = fitz.Rect(blocks[0][:4])
        else:
            # don't try to crop empty pages
            crop = fitz.Rect(0,0,0,0)
        for block in blocks:
            b = fitz.Rect(block[:4])
            crop = crop | b

        return crop

    def display_page(self, bar, p, display=True):

        page = self.load_page(p)
        page_state = self.page_states[p]

        if self.manualcrop and self.manualcroprect != [None,None] and self.is_pdf:
            page.set_cropbox(fitz.Rect(self.manualcroprect[0],self.manualcroprect[1]))

        elif self.autocrop and self.is_pdf:
            page.set_cropbox(page.mediabox)
            crop = self.auto_crop(page)
            page.set_cropbox(crop)

        elif self.is_pdf:
            page.set_cropbox(page.mediabox)

        dw = scr.width
        dh = scr.height - scr.cell_height

        if self.rotation in [0,180]:
            pw = page.bound().width
            ph = page.bound().height
        else:
            pw = page.bound().height
            ph = page.bound().width
        
        # calculate zoom factor
        fx = dw / pw
        fy = dh / ph
        factor = min(fx,fy)
        self.page_states[p].factor = factor
    
        # calculate zoomed dimensions
        zw = factor * pw
        zh = factor * ph

        # calculate place in pixels, convert to cells
        pix_x = (dw / 2) - (zw / 2)
        pix_y = (dh / 2) - (zh / 2)
        l_col = int(pix_x / scr.cell_width) + 1
        t_row = int(pix_y / scr.cell_height)
        r_col = l_col + int(zw / scr.cell_width)
        b_row = t_row + int(zh / scr.cell_height)
        place = (l_col, t_row, r_col, b_row)
        self.page_states[p].place = place

        # move cursor to place
        scr.set_cursor(l_col,t_row)

        # clear previous page
        # display image
        cmd = {'a': 'p', 'i': p + 1, 'z': -1}
        if page_state.stale: #or (display and not write_gr_cmd_with_response(cmd)):
            # get zoomed and rotated pixmap
            mat = fitz.Matrix(factor, factor)
            mat = mat.prerotate(self.rotation)
            pix = page.get_pixmap(matrix = mat, alpha=self.alpha)

            if self.invert:
                pix.invert_irect()

            if self.tint:
                tint = fitz.utils.getColor(self.tint_color)
                red = int(tint[0] * 256)
                blue = int(tint[1] * 256)
                green = int(tint[2] * 256)
                # pix.tint_with(red, blue, green)
                # tinting disabled due to unresolved bug

            # build cmd to send to kitty
            cmd = {'i': p + 1, 't': 'd', 's': pix.width, 'v': pix.height}

            if self.alpha:
                cmd['f'] = 32
            else:
                cmd['f'] = 24

            # transfer the image
            write_chunked(cmd, pix.samples)

        if display:  
            # clear prevpage
            self.clear_page(self.prevpage)
            # display the image
            cmd = {'a': 'p', 'i': p + 1, 'z': -1}
            success = write_gr_cmd_with_response(cmd)
            if not success:
                self.page_states[p].stale = True
                bar.message = 'failed to load page ' + str(p+1)
                bar.update(self)

        self.page_states[p].stale = False 

        scr.swallow_keys()

    def show_toc(self, bar):

        toc = self.get_toc()

        if not toc:
            bar.message = "No ToC available"
            return

        self.page_states[self.page ].stale = True
        self.clear_page(self.page)
        scr.clear()
        
        def init_pad(toc):
            win, pad = scr.create_text_win(len(toc), 'Table of Contents')
            y,x = win.getbegyx()
            h,w = win.getmaxyx()
            span = []
            for i, ch in enumerate(toc):
                text = '{}{}'.format('  ' * (ch[0] - 1), ch[1])
                pad.addstr(i,0,text)
                span.append(len(text))
            return win,pad,y,x,h,w,span

        win,pad,y,x,h,w,span = init_pad(toc)

        keys = shortcuts()
        index = self.current_chap()
        j = 0
       
        while True:
            for i, ch in enumerate(toc):
                attr = curses.A_REVERSE if index == i else curses.A_NORMAL
                pad.chgat(i, 0, span[i], attr)
            pad.refresh(j, 0, y + 3, x + 2, y + h - 2, x + w - 3)
            key = scr.stdscr.getch()
            
            if key in keys.REFRESH:
                scr.clear()
                scr.get_size()
                scr.init_curses()
                self.set_layout(self.papersize)
                self.mark_all_pages_stale()
                init_pad(toc)
            elif key in keys.QUIT:
                clean_exit()
            elif key == 27 or key in keys.SHOW_TOC:
                scr.clear()
                return
            elif key in keys.NEXT_PAGE:
                index = min(len(toc) - 1, index + 1)
            elif key in keys.PREV_PAGE:
                index = max(0, index - 1)
            elif key in keys.OPEN:
                scr.clear()
                self.goto_page(toc[index][2] - 1)
                return
            
            if index > j + (h - 5):
                j += 1
            if index < j:
                j -= 1
   
    def update_metadata_from_bibtex(self):
        if not self.citekey:
            return
        
        bib = bib_from_key([self.citekey])
        bib_entry = bib.entries[self.citekey]

        metadata = self.metadata
        title = bib_entry.fields['title']
        title = title.replace('{','')
        title = title.replace('}','')
        metadata['title'] = title

        authors = [author for author in bib_entry.persons['author']]
        if len(authors) == 0:
            authors = [author for author in bib_entry.persons['editor']]
        authorNames = ''
        for author in authors:
            if authorNames != '':
                authorNames += ' & '
            if author.first_names:
                authorNames += ' '.join(author.first_names) + ' '
            if author.last_names:
                authorNames +=  ' '.join(author.last_names)

        metadata['author'] = authorNames
       
        if 'Keywords' in bib_entry.fields:
            metadata['keywords'] = bib_entry.fields['Keywords']

        self.set_metadata(metadata)
        try:
            self.saveIncr()
        except:
            pass

    def show_meta(self, bar):

        meta = self.metadata
        
        if not meta:
            bar.message = "No metadata available"
            return

        self.page_states[self.page].stale = True
        self.clear_page(self.page)
        scr.clear()
        
        def init_pad(metadata):
            win, pad = scr.create_text_win(len(meta), 'Metadata')
            y,x = win.getbegyx()
            h,w = win.getmaxyx()
            span = []
            for i, mkey in enumerate(meta):
                text = '{}: {}'.format(mkey,meta[mkey])
                pad.addstr(i,0,text)
                span.append(len(text))
            return win,pad,y,x,h,w,span

        win,pad,y,x,h,w,span = init_pad(meta)

        keys = shortcuts()
        index = 0
        j = 0
       
        while True:
            for i, mkey in enumerate(meta):
                attr = curses.A_REVERSE if index == i else curses.A_NORMAL
                pad.chgat(i, 0, span[i], attr)
            pad.refresh(j, 0, y + 3, x + 2, y + h - 2, x + w - 3)
            key = scr.stdscr.getch()
            
            if key in keys.REFRESH:
                scr.clear()
                scr.get_size()
                scr.init_curses()
                self.set_layout(self.papersize)
                self.mark_all_pages_stale()
                init_pad(meta)
            elif key in keys.QUIT:
                clean_exit()
            elif key == 27 or key in keys.SHOW_META:
                scr.clear()
                return
            elif key in keys.NEXT_PAGE:
                index = min(len(meta) - 1, index + 1)
            elif key in keys.PREV_PAGE:
                index = max(0, index - 1)
            elif key in keys.UPDATE_FROM_BIB:
                self.update_metadata_from_bibtex()
                meta = self.metadata
                win,pad,y,x,h,w,span = init_pad(meta)
            elif key in keys.OPEN:
                # TODO edit metadata 
                pass
            
            if index > j + (h - 5):
                j += 1
            if index < j:
                j -= 1
   
    def goto_link(self,link):
        kind = link['kind']
        # 0 == no destination
        # 1 == internal link
        # 2 == uri
        # 3 == launch link
        # 5 == external pdf link
        if kind == 0:
            pass
        elif kind == 1:
            self.goto_page(link['page'])
        elif kind == 2:
            subprocess.run([config.URL_BROWSER, link['uri']], check=True)
        elif kind == 3:
            # not sure what these are
            pass
        elif kind == 5:
            path = link['fileSpec']
            opts = {'page': link['page']}
            #load_doc(path,opts)
            pass

    def show_links(self, bar):

        links = self[self.page].get_links()

        urls = [link for link in links if 0 < link['kind'] < 3]

        if not urls:
            bar.message = "No links on page"
            return

        self.page_states[self.page].stale = True
        self.clear_page(self.page)
        scr.clear()
        
        def init_pad(urls):
            win, pad = scr.create_text_win(len(urls), 'URLs')
            y,x = win.getbegyx()
            h,w = win.getmaxyx()
            span = []
            for i, url in enumerate(urls):
                anchor_text = self.get_text_intersecting_Rect(url['from'])
                if len(anchor_text) > 0:
                    anchor_text = anchor_text[0]
                else:
                    anchor_text = ''
                if url['kind'] == 2:
                    link_text = url['uri']
                else:
                    link_text = url['page']

                text = '{}: {}'.format(anchor_text, link_text)
                pad.addstr(i,0,text)
                span.append(len(text))
            return win,pad,y,x,h,w,span

        win,pad,y,x,h,w,span = init_pad(urls)

        keys = shortcuts()
        index = 0
        j = 0
       
        while True:
            for i, url in enumerate(urls):
                attr = curses.A_REVERSE if index == i else curses.A_NORMAL
                pad.chgat(i, 0, span[i], attr)
            pad.refresh(j, 0, y + 3, x + 2, y + h - 2, x + w - 3)
            key = scr.stdscr.getch()
            
            if key in keys.REFRESH:
                scr.clear()
                scr.get_size()
                scr.init_curses()
                self.set_layout(self.papersize)
                self.mark_all_pages_stale()
                init_pad(urls)
            elif key in keys.QUIT:
                clean_exit()
            elif key == 27 or key in keys.SHOW_LINKS:
                scr.clear()
                return
            elif key in keys.NEXT_PAGE:
                index = min(len(urls) - 1, index + 1)
            elif key in keys.PREV_PAGE:
                index = max(0, index - 1)
            elif key in keys.OPEN:
                self.goto_link(urls[index])
                scr.clear()
                return
                 
            if index > j + (h - 5):
                j += 1
            if index < j:
                j -= 1
    
    def view_text(self):
        pass

    def init_neovim_bridge(self):
        try:
            from pynvim import attach
        except:
            raise SystemExit('pynvim unavailable')
        try:
            self.nvim = attach('socket', path=self.nvim_listen_address)
        except:
            ncmd = 'env NVIM_LISTEN_ADDRESS={} nvim {}'.format(self.nvim_listen_address, config.NOTE_PATH)
            try:
                os.system('{} {}'.format(config.KITTYCMD,ncmd))
            except:
                raise SystemExit('unable to open new kitty window')

            end = monotonic() + 5 # 5 second time out 
            while monotonic() < end:
                try:
                    self.nvim = attach('socket', path=self.nvim_listen_address)
                    break
                except:
                    # keep trying every tenth of a second
                    sleep(0.1)

    def send_to_neovim(self,text,append=False):
        try:
            self.nvim.api.strwidth('testing')
        except: 
            self.init_neovim_bridge()
        if not self.nvim:
            return 
        if append:
            line = self.nvim.funcs.line('$')
            self.nvim.funcs.append(line, text)
            self.nvim.funcs.cursor(self.nvim.funcs.line('$'),0)
        else:
            line = self.nvim.funcs.line('.')
            self.nvim.funcs.append(line, text)
            self.nvim.funcs.cursor(line + len(text), 0)


class Page_State:
    def __init__(self, p):
        self.number = p
        self.stale = True
        self.factor = (1,1)
        self.place = (0,0,40,40)
        self.crop = None

class status_bar:

    def __init__(self):
        self.cols = 40
        self.rows = 1
        self.cmd = ' '
        self.message = ' '
        self.counter = ' '
        self.format = '{} {:^{me_w}} {}'
        self.bar = ''

    def update(self, doc):
        p = doc.page_to_logical()
        pc = doc.page_to_logical(doc.pages)
        self.counter = '[{}/{}]'.format(p, pc)
        w = self.cols = scr.cols
        cm_w = len(self.cmd)
        co_w = len(self.counter)
        me_w = w - cm_w - co_w - 2
        if len(self.message) > me_w:
            self.message = self.message[:me_w - 1] + '…' 
        self.bar = self.format.format(self.cmd, self.message, self.counter, me_w=me_w)
        scr.place_string(1,scr.rows,self.bar)

class shortcuts:

    def __init__(self):
        self.GOTO_PAGE        = [ord('G')]
        self.GOTO             = [ord('g')]
        self.NEXT_PAGE        = [ord('j'), curses.KEY_DOWN, ord(' ')]
        self.PREV_PAGE        = [ord('k'), curses.KEY_UP]
        self.GO_BACK          = [ord('p')]
        self.NEXT_CHAP        = [ord('l'), curses.KEY_RIGHT]
        self.PREV_CHAP        = [ord('h'), curses.KEY_LEFT]
        self.BUFFER_CYCLE     = [ord('b')]
        self.BUFFER_CYCLE_REV = [ord('B')]
        self.HINTS            = [ord('f')]
        self.OPEN             = [curses.KEY_ENTER, curses.KEY_RIGHT, 10]
        self.SHOW_TOC         = [ord('t')]
        self.SHOW_META        = [ord('M')]
        self.UPDATE_FROM_BIB  = [ord('b')]
        self.SHOW_LINKS       = [ord('f')]
        self.TOGGLE_TEXT_MODE = [ord('T')]
        self.ROTATE_CW        = [ord('r')]
        self.ROTATE_CCW       = [ord('R')]
        self.VISUAL_MODE      = [ord('s')]
        self.SELECT           = [ord('v')]
        self.YANK             = [ord('y')]
        self.INSERT_NOTE      = [ord('n')]
        self.APPEND_NOTE      = [ord('a')]
        self.TOGGLE_AUTOCROP  = [ord('c')]
        self.TOGGLE_ALPHA     = [ord('A')]
        self.TOGGLE_INVERT    = [ord('i')]
        self.TOGGLE_TINT      = [ord('d')]
        self.SET_PAGE_LABEL   = [ord('P')]
        self.SET_PAGE_ALT     = [ord('I')]
        self.INC_FONT         = [ord('=')]
        self.DEC_FONT         = [ord('-')]
        self.OPEN_GUI         = [ord('X')]
        self.REFRESH          = [18, curses.KEY_RESIZE]            # CTRL-R
        self.QUIT             = [3, ord('q')]
        self.DEBUG            = [ord('D')]

# Kitty graphics functions

def detect_support():
    return write_gr_cmd_with_response(dict(a='q', s=1, v=1, i=1), standard_b64encode(b'abcd'))

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
    # rewrite using swallow keys to be nonblocking
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

# bibtex functions

def bib_from_field(field,regex):

    if shutil.which('bibtool') is not None:
        from pybtex.database import parse_string 
        select = "select {" + field + " "
        select = select + '\"{}\"'.format(regex)
        select = select + "}"
        text = subprocess.run(["bibtool", "-r", "biblatex", "--", select, config.BIBTEX], stdout=subprocess.PIPE, universal_newlines = True)
        if text.returncode != 0:
            return None
        bib = parse_string(text.stdout,'bibtex')
        if len(bib.entries) == 0:
            return None
    else:   
        from pybtex.database import parse_file
        bib = parse_file(config.BIBTEX,'bibtex')

    return bib

def bib_from_key(citekeys):
    
    field = '$key'
    regex = '\|'.join(citekeys)
    regex = '^' + regex + '$'
    return bib_from_field(field,regex)

def citekey_from_path(path):
    
    path = os.path.basename(path)
    bib = bib_from_field('File',path)

    if bib and len(bib.entries) == 1:
        citekey = list(bib.entries)[0]
        return citekey

def path_from_citekey(citekey):
    bib = bib_from_key([citekey])
    if bib == None:
        raise SystemExit('Cannot find file associated with ' + citekey)
    if len(bib.entries) == 1:
        try:
            paths = bib.entries[citekey].fields["File"]
        except:
            raise SystemExit('No file for ' + citekey)
        paths = paths.split(';')
        exts = ['.pdf', '.xps', '.cbz', '.fb2' ]
        extsf = ['.epub', '.oxps']
        extsl = ['.html']
        best = [path for path in paths if path[-4:] in exts]
        okay = [path for path in paths if path[-5:] in extsf]
        worst = [path for path in paths if path[-5:] in extsl]
        if len(best) != 0:
            return best[0]
        elif len(okay) != 0:
            return okay[0]
        elif len(worst) != 0:
            return worst[0]
    return None

# Command line helper functions

def print_version():
    print(__version__)
    print(__license__, 'License')
    print(__copyright__, __author__)
    print(__url__)
    raise SystemExit


def print_help():
    print(__doc__.rstrip())
    print()
    print(__viewer_shortcuts__)
    raise SystemExit()

def parse_args(args):
    files = []
    opts = {'ignore_cache': False} 
    if len(args) == 1:
        args = args + ['-h']

    args = args[1:]

    if len({'-h', '--help'} & set(args)) != 0:
        print_help()
    elif len({'-v', '--version'} & set(args)) != 0:
        print_version()
    
    skip = False
    for i,arg in enumerate(args):
        if skip:
            skip = not skip
        elif arg in {'-p', '--page-number'}:
            try:
                opts['logicalpage'] = int(args[i + 1])
                skip = True
            except:
                raise SystemExit('No valid page number specified')
        elif arg in {'-f', '--first-page'}:
            try:
                opts['first_page_offset'] = int(args[i + 1])
                skip = True
            except:
                raise SystemExit('No valid first page specified')
        elif arg in {'--nvim-listen-address'}:
            try:
                opts['nvim_listen_address'] = args[i + 1]
                skip = True
            except:
                raise SystemExit('No address specified')
        elif arg in {'--citekey'}:
            try:
                opts['citekey'] = args[i + 1]
                skip = True
            except:
                raise SystemExit('No citekey specified')
        elif arg in {'-o', '--open'}:
            try:
                citekey = args[i+1]
            except:
                raise SystemExit('No citekey specified')
            opts['citekey'] = citekey
            path = path_from_citekey(citekey)
            if path:
                if path[-5:] == '.html':
                    subprocess.run([config.URL_BROWSER, path], check=True)
                    print("Opening html file in browser")
                elif path[-5:] == '.docx':
                    # TODO: support for docx files
                    raise SystemExit('Cannot open ' + path)
                else:
                    files += [path]
            else:
                raise SystemExit('No file for ' + citekey) 
            skip = True
        elif arg in {'--ignore-cache'}:
            opts['ignore_cache'] = True
        elif os.path.isfile(arg):
            files = files + [arg]
        elif os.path.isfile(arg.strip('\"')):
            files = files + [arg.strip('\"')]
        elif os.path.isfile(arg.strip('\'')):
            files = files + [arg.strip('\'')]
        elif re.match('^-', arg):
            raise SystemExit('Unknown option: ' + arg)
        else:
            raise SystemExit('Can\'t open file: ' + arg)

    if len(files) == 0:
        raise SystemExit('No file to open')

    return files, opts

def clean_exit(message=''):
    
    scr.create_text_win(1, ' ')

    for doc in bufs.docs:
        # save current state
        doc.write_state()
        # close the document
        doc.close()

    # close curses
    scr.stdscr.keypad(False)
    curses.echo()
    curses.curs_set(1)
    curses.endwin()

    raise SystemExit(message)

def get_text_in_rows(doc,left,right, selection):
    l,t,r,b = doc.page_states[doc.page].place
    top = (l + left,t + selection[0] - 1)
    bottom = (l + right,t + selection[1])
    top_pix, bottom_pix = doc.cells_to_pixels(top,bottom)
    rect = fitz.Rect(top_pix, bottom_pix)
    select_text = doc.get_text_in_Rect(rect)
    link = doc.make_link()
    select_text = select_text + [link]
    return (' '.join(select_text))

def crop_to_selection(doc,left,right,selection):
    l,t,r,b = doc.page_states[doc.page].place
    top = (l + left,t + selection[0] - 1)
    bottom = (l + right,t + selection[1])
    top_pix, bottom_pix = doc.cells_to_pixels(top,bottom)
    doc.manualcrop = True
    doc.manualcroprect = [top_pix, bottom_pix]

# Viewer functions

def visual_mode(doc,bar):
    l,t,r,b = doc.page_states[doc.page].place
    
    width = (r - l) + 1

    def highlight_row(row,left,right, fill='▒', color='yellow'):
        if color == 'yellow':
            cc = 33
        elif color == 'blue':
            cc = 34
        elif color == 'none':
            cc = 0

        fill = fill[0] * (right - left)

        scr.set_cursor(l + left,row)
        sys.stdout.buffer.write('\033[{}m'.format(cc).encode('ascii'))
        #sys.stdout.buffer.write('\033[{}m'.format(cc + 10).encode('ascii'))
        sys.stdout.write(fill)
        sys.stdout.flush()
        sys.stdout.buffer.write(b'\033[0m')
        sys.stdout.flush()

    def unhighlight_row(row):
        # scr.set_cursor(l,row)
        # sys.stdout.write(' ' * width)
        # sys.stdout.flush()
        highlight_row(row,0,width,fill=' ',color='none')

    def highlight_selection(selection,left,right, fill='▒', color='blue'):
        a = min(selection)
        b = max(selection)
        for r in range(a,b+1):
            highlight_row(r,left,right,fill,color)

    def unhighlight_selection(selection):
        highlight_selection(selection,0,width,fill=' ',color='none')

    current_row = t
    left = 0
    right = width
    select = False
    selection = [current_row,current_row]
    count_string = '' 

    while True:
       
        bar.cmd = count_string
        bar.update(doc)
        unhighlight_selection([t,b])
        if select:
            highlight_selection(selection,left,right,color='blue')
        else:
            highlight_selection(selection,left,right,color='yellow')

        if count_string == '':
            count = 1
        else:
            count = int(count_string)

        keys = shortcuts() 
        key = scr.stdscr.getch()
      
        if key in range(48,58): #numerals
            count_string = count_string + chr(key)

        elif key in keys.QUIT:
            clean_exit()

        elif key == 27 or key in keys.VISUAL_MODE:
            unhighlight_selection([t,b])
            return

        elif key in keys.SELECT:
            if select:
                select = False
            else:
                select = True
            selection = [current_row, current_row]
            count_string = ''

        elif key in keys.NEXT_PAGE:
            current_row += count 
            current_row = min(current_row,b)
            if select:
                selection[1] = current_row
            else:
                selection = [current_row,current_row]
            count_string = ''

        elif key in keys.PREV_PAGE:
            current_row -= count 
            current_row = max(current_row,t)
            if select:
                selection[1] = current_row
            else:
                selection = [current_row,current_row]
            count_string = ''
        
        elif key in keys.NEXT_CHAP:
            right = min(width,right + count)
            count_string = ''

        elif key in { ord('L'), curses.KEY_SRIGHT }:
            right = max(left + 1,right - count)
            count_string = ''

        elif key in keys.PREV_CHAP:
            left = max(0,left - count)
            count_string = ''

        elif key  in { ord('H'), curses.KEY_SLEFT }:
            left = min(left + count,right - 1)
            count_string = ''

        elif key in keys.GOTO_PAGE:
            current_row = b
            if select:
                selection[1] = current_row
            else:
                selection = [current_row,current_row]
            count_string = ''

        elif key in keys.GOTO:
            current_row = t
            if select:
                selection[1] = current_row
            else:
                selection = [current_row,current_row]
            count_string = ''

        elif key in keys.YANK:
            if selection == [None,None]:
                selection = [current_row, current_row]
            selection.sort()
            select_text = get_text_in_rows(doc,left,right,selection)
            select_text = '> ' + select_text
            pyperclip.copy(select_text)
            unhighlight_selection([t,b])
            bar.message = 'copied'
            return

        elif key in keys.INSERT_NOTE:
            if selection == [None,None]:
                selection = [current_row, current_row]
            selection.sort()
            select_text = ['']
            select_text = ['#+BEGIN_QUOTE']
            select_text += [get_text_in_rows(doc,left,right,selection)]
            select_text += ['#+END_QUOTE']
            select_text += ['']
            doc.send_to_neovim(select_text, append=False)
            unhighlight_selection([t,b])
            return

        elif key in keys.APPEND_NOTE:
            if selection == [None,None]:
                selection = [current_row, current_row]
            selection.sort()
            note_header = ' Notes on {}, {}'.format(doc.metadata['author'], doc.metadata['title'])
            if doc.citekey:
                note_header = doc.citekey + note_header
            select_text = ['** ' + note_header] 
            select_text += ['']
            select_text = ['#+BEGIN_QUOTE']
            select_text += [get_text_in_rows(doc,left,right,selection)]
            select_text += ['#+END_QUOTE']
            select_text += ['']
            doc.send_to_neovim(select_text,append=True)
            unhighlight_selection([t,b])
            return
        
        elif key in keys.TOGGLE_AUTOCROP and selection != [None,None]:
            crop_to_selection(doc,left,right,selection)
            unhighlight_selection([t,b])
            doc.mark_all_pages_stale()
            return

def watch_for_file_change(file_change,path):
    timestamp = os.path.getmtime(path)
    while True:
        sleep(.5)
        nts = os.path.getmtime(path)
        if nts != timestamp:
            timestamp = nts
            logging.debug('file changed')
            file_change.set() 

def view(file_change,doc):

    scr.get_size()
    scr.init_curses()

    if not detect_support():
        raise SystemExit(
            'Terminal does not support kitty graphics protocol'
            )
    scr.swallow_keys()

    bar = status_bar()
    if doc.citekey:
        bar.message = doc.citekey

    count_string = ""
    stack = [0]
    keys = shortcuts() 

    while True:

        bar.cmd = ''.join(map(chr,stack[::-1]))
        bar.update(doc )
        doc.display_page(bar,doc.page)

        if count_string == "":
            count = 1
        else:
            count = int(count_string)
        
        scr.stdscr.nodelay(True)
        key = scr.stdscr.getch()
        while key == -1 and not file_change.is_set():
            key = scr.stdscr.getch()
        scr.stdscr.nodelay(False)

        if file_change.is_set():
            logging.debug('view thread sees that file has changed')
            key = keys.REFRESH[0]
            file_change.clear()

        if key == -1:
            pass

        elif key in keys.REFRESH: 
            scr.clear()
            scr.get_size()
            scr.init_curses()
            current_doc = bufs.docs[bufs.current]
            current_doc.write_state()
            doc = Document(current_doc.filename)
            cachefile = get_cachefile(doc.filename)
            if os.path.exists(cachefile):
                with open(cachefile, 'r') as f:
                    state = json.load(f)
                for key in state:
                    setattr(doc, key, state[key])
            bufs.docs[bufs.current] = doc
            if not doc.citekey:
                doc.citekey = citekey_from_path(doc.filename)
            doc.pages_to_logical_pages()
            doc.goto_logical_page(doc.logicalpage)
            doc.set_layout(doc.papersize,adjustpage=False)

        elif key == 27:
            # quash stray escape codes
            scr.swallow_keys()
            count_string = ""
            stack = [0]

        elif stack[0] in keys.BUFFER_CYCLE and key in range(48,58):
            bufs.goto_buffer(int(chr(key)) - 1)
            doc = bufs.docs[bufs.current]
            doc.goto_logical_page(doc.logicalpage)
            doc.set_layout(doc.papersize,adjustpage=False)
            doc.mark_all_pages_stale()
            if doc.citekey:
                bar.message = doc.citekey
            count_string = ""
            stack = [0]

        elif stack[0] in keys.BUFFER_CYCLE and key == ord('d'):
            bufs.close_buffer(bufs.current)
            doc = bufs.docs[bufs.current]
            doc.goto_logical_page(doc.logicalpage)
            doc.set_layout(doc.papersize,adjustpage=False)
            doc.mark_all_pages_stale()
            if doc.citekey:
                bar.message = doc.citekey
            count_string = ""
            stack = [0]

        elif stack[0] in keys.BUFFER_CYCLE and key in keys.BUFFER_CYCLE:
            bufs.cycle(count)
            doc = bufs.docs[bufs.current]
            doc.goto_logical_page(doc.logicalpage)
            doc.set_layout(doc.papersize,adjustpage=False)
            doc.mark_all_pages_stale()
            if doc.citekey:
                bar.message = doc.citekey
            count_string = ""
            stack = [0]

        elif key in keys.BUFFER_CYCLE_REV:
            bufs.cycle(-count)
            doc = bufs.docs[bufs.current]
            doc.goto_logical_page(doc.logicalpage)
            doc.set_layout(doc.papersize,adjustpage=False)
            doc.mark_all_pages_stale()
            if doc.citekey:
                bar.message = doc.citekey
            count_string = ""
            stack = [0]

        elif key in range(48,58): #numerals
            stack = [key] + stack
            count_string = count_string + chr(key)

        elif key in keys.QUIT:
            clean_exit()

        elif key in keys.GOTO_PAGE:
            if count_string == "":
                p = doc.page_to_logical(doc.pages)
            else:
                p = count
            doc.goto_logical_page(p)
            count_string = ""
            stack = [0]

        elif key in keys.NEXT_PAGE:
            doc.next_page(count)
            count_string = ""
            stack = [0]

        elif key in keys.PREV_PAGE:
            doc.prev_page(count)
            count_string = ""
            stack = [0]

        elif key in keys.GO_BACK:
            doc.goto_page(doc.prevpage)
            count_string = ""
            stack = [0]

        elif key in keys.NEXT_CHAP:
            doc.next_chap(count)
            count_string = ""
            stack = [0]

        elif key in keys.PREV_CHAP:
            doc.prev_chap(count)
            count_string = ""
            stack = [0]

        elif stack[0] in keys.GOTO and key in keys.GOTO:
            doc.goto_page(0)
            count_string = ""
            stack = [0]

        elif key in keys.ROTATE_CW:
            doc.rotation = (doc.rotation + 90 * count) % 360
            doc.mark_all_pages_stale()
            count_string = ''
            stack = [0]

        elif key in keys.ROTATE_CCW:
            doc.rotation = (doc.rotation - 90 * count) % 360
            doc.mark_all_pages_stale()
            count_string = ""
            stack = [0]

        elif key in keys.TOGGLE_AUTOCROP:
            # cycle through no crop, autocrop, and manualcrop
            if doc.manualcroprect != [None,None]:
                if doc.autocrop:
                    doc.autocrop = False
                    doc.manualcrop = True
                elif doc.manualcrop:
                    doc.autocrop = False
                    doc.manualcrop = False
                else:
                    doc.autocrop = True
            # just toggle autocrop
            else:
                doc.autocrop = not doc.autocrop
            doc.mark_all_pages_stale()
            count_string = ""
            stack = [0]

        elif key in keys.TOGGLE_ALPHA:
            doc.alpha = not doc.alpha
            doc.mark_all_pages_stale()
            count_string = ""
            stack = [0]

        elif key in keys.TOGGLE_INVERT:
            doc.invert = not doc.invert
            doc.mark_all_pages_stale()
            count_string = ""
            stack = [0]
        
        elif key in keys.TOGGLE_TINT:
            doc.tint = not doc.tint
            doc.mark_all_pages_stale()
            count_string = ""
            stack = [0]

        elif key in keys.SHOW_TOC:
            doc.show_toc(bar)
            count_string = ""
            stack = [0]

        elif key in keys.SHOW_META:
            doc.show_meta(bar)
            count_string = ""
            stack = [0]
        
        elif key in keys.SHOW_LINKS:
            doc.show_links(bar)
            count_string = ""
            stack = [0]

        elif key in keys.TOGGLE_TEXT_MODE:
            doc.view_text()
            count_string = ""
            stack = [0]
       
        elif key in keys.INC_FONT:
            doc.set_layout(doc.papersize - count)
            doc.mark_all_pages_stale()
            count_string = ""
            stack = [0]
        
        elif key in keys.DEC_FONT:
            doc.set_layout(doc.papersize + count)
            doc.mark_all_pages_stale()
            count_string = ""
            stack = [0]

        elif key in keys.VISUAL_MODE:
            visual_mode(doc,bar)
            count_string = ""
            stack = [0]

        elif key in keys.INSERT_NOTE:
            text = doc.make_link()
            doc.send_to_neovim(text,append=False)
            count_string = ""
            stack = [0]
        
        elif key in keys.APPEND_NOTE:
            text = doc.make_link()
            doc.send_to_neovim(text,append=True)
            count_string = ""
            stack = [0]

        elif key in keys.SET_PAGE_LABEL:
            if doc.is_pdf:
                doc.set_pagelabel(count,'arabic')
            else:
                doc.first_page_offset = count - doc.page
            doc.pages_to_logical_pages()
            count_string = ""
            stack = [0]

        elif key in keys.SET_PAGE_ALT:
            if doc.is_pdf:
                doc.set_pagelabel(count,'roman lowercase')
            else:
                doc.first_page_offset = count - doc.page
            doc.pages_to_logical_pages()
            count_string = ""
        
        elif key == ord('/'):
            scr.place_string(1,scr.rows,"/")
            curses.echo()
            scr.set_cursor(2,scr.rows)
            s = scr.stdscr.getstr()
            search_text = s.decode('utf-8')
            curses.noecho()
            bar.message = doc.search_text(search_text)

        elif key in keys.OPEN_GUI:
            subprocess.run([config.GUI_VIEWER, doc.filename], check=True)

        elif key in keys.DEBUG:
            pass

        elif key in range(48,257): #printable characters
            stack = [key] + stack


# config is global
config = Config()
config.load_config_file()
if not config.URL_BROWSER:
    config.browser_detect()
# buffers list is global
bufs = Buffers()
# screen is global
scr = Screen()

def main(args=sys.argv):

    if not sys.stdin.isatty():
        raise SystemExit('Not an interactive tty')

    scr.get_size()

    if scr.width == 0:
        raise SystemExit(
            'Terminal does not support reporting screen sizes via the TIOCGWINSZ ioctl'
        )

    if scr.width == 65535:
        raise SystemExit('Screen size is not being reported properly.\nThis problem might be caused by the fish shell.')

    paths, opts = parse_args(args)

    for path in paths:
        try:
            doc = Document(path)
        except:
            raise SystemExit('Unable to open ' + files[0])

        # load saved file state
        cachefile = get_cachefile(doc.filename)
        if os.path.exists(cachefile) and not opts['ignore_cache']:
            with open(cachefile, 'r') as f:
                state = json.load(f)
            for key in state:
                setattr(doc, key, state[key])
        bufs.docs += [doc]

    for doc in bufs.docs:
        if not doc.citekey:
            doc.citekey = citekey_from_path(doc.filename)

    doc = bufs.docs[bufs.current]

    # load cli settings
    for key in opts:
        setattr(doc, key, opts[key])

    # generate logical pages
    doc.pages_to_logical_pages()

    # normalize page number
    doc.goto_logical_page(doc.logicalpage)

    # apply layout settings
    doc.set_layout(doc.papersize,adjustpage=False)

    # set up thread to watch for file changes
    file_change = threading.Event()
    file_watch = threading.Thread(target=watch_for_file_change, args=(file_change, doc.filename))
    file_watch.daemon = True
    file_watch.start()

    doc_viewer = threading.Thread(target=view, args=(file_change, doc))
    doc_viewer.start()

if __name__ == '__main__':
    #logging.basicConfig(filename='termpdf.log',level=logging.DEBUG)
    logging.basicConfig(filename='termpdf.log',level=logging.WARNING)
    main()

