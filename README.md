# `termpdf.py`

A graphical pdf (and epub and cbz) viewer, written in python, that works inside
[kitty](https://sw.kovidgoyal.net/kitty/). 

I wrote this to replace [termpdf](https://github.com/dsanson/termpdf), which
was a ridiculous hack of a bash script written around a bunch of command line
tools.

This is alpha software. Expect bugs. Expect changes. The
goal is feature parity with [pdf-tools](https://github.com/politza/pdf-tools).

# Screenshot

![Screenshot](screenshot.png)

Note the alpha transparency. You can toggle this on or off by pressing `a`.

# Dependencies

-   Python 3
-   Kitty (unless other terminal emulators implement the same graphics protocol.)
-   [PyMuPDF](https://pypi.org/project/PyMuPDF/)
    -   PyMuPDF in turn depends on MuPDF. On OSX, `brew install mupdf-tools`.
-   [bibtool](http://gerd-neugebauer.de/software/TeX/BibTool/en/) (optional) for faster
	bibtex parsing than pybtex.

# Installation

    git clone https://github.com/dsanson/termpdf.py
    cd termpdf.py
    pip install -r requirements.txt

(You might need to use `pip3` if `pip` is Python 2 on your system.)

Now you can run the script in place:

    ./termpdf.py <file.pdf>

Or copy it somewhere in your path.

Or you can install it with pip:

    pip install .

# Simple Usage

This is evolving. Here is the simplest example:

	termpdf.py example.pdf

If you want to open to a specific page,

	termpdf.py -p 10 example.pdf

If you want to specify the "logical page number" of the first page,

	termpdf.py -f 132 example.pdf

You can open several files at once:

	termpdf.py example.pdf example2.pdf example3.pdf

# Keyboard Shortcuts

Within termpdf, key mappings are meant to be vim-style. For simple
navigation:

    j, down, space: forward [count] pages
    k, up:          back [count] pages
    l, right:       forward [count] sections
    h, left:        back [count] sections
    gg:             go to beginning of document
    G:              go to end of document
    [count]G:       go to page [count]

Note that these take counts, so `10j` moves forward 10 pages. 

If you opened several documents at once, you can cycle through these documents by pressing `b`:

	b				cycle through documents in buffer

By default, the first page of a document will be displayed as page 1. But often, the "real" page number is something else. From any page, type in its "real" page number and hit `P`:

    [count]P:       Set logical page number of current page to count

This setting will persist between sessions, and affects your navigation and
display, as well as the page numbers embedded in automatically generated
citations. (Note that termpdf.py does not yet have the ability to read or
write logical page information from pdfs, so this setting will only work
within termpdf.py.)

You can view the table of contents, metadata, or any links (internal or
external) on the current page:

    t:              table of contents 
    f:              show links on page
    M:              show metadata

While viewing the table of contents, use `j` and `k` to navigate, and <enter> to jump to a new section.

While viewing links, use `j` and `k` to navigate, and <enter> to open the link. For internal links, this will jump to the appropriate page. External links will be opened in your browser (see URL_BROWSER for more info). External links to PDFs will be opened in termpdf.py (not yet implemented).

While viewing metadata, press `b` to update the metadata from an associated
bibtex file (see below for how to set this up).

You can also adjust the display of the document in a variety of ways:

    r:              rotate [count] quarter turns clockwise
    R:              rotate [count] quarter turns counterclockwise
    c:              toggle autocropping of margins
    a:              toggle alpha transparency
    i:              invert colors
    d:              darken using TINT_COLOR
    -:              zoom out (reflowable only)
    +:              zoom in (reflowable only)
    ctrl-r:         refresh

(Zooming is currently only implemented for reflowable formats, like `epub`.)

The refresh command is helpful if the page fails to display, or displays
funny: try hitting `ctrl-r` to see if that fixes the problem.

If you want to send a citation to the current page to an attached nvim session
(more below), use `n` (to insert at current cursor location) or `a` (to append
to end of buffer). If you want to select some text and send that to nvim, you
need to enter "visual select mode":
    
    v:              visual select mode
    n:              insert note in nvim
    a:              append note in nvim

While in visual select mode, use `j` and `k` (with counts) to move up and
down. Use `s` to toggle between selecting and not. Use `y` to copy all the
text within the selection to the clipboard, `n` to insert the text at the cursor point of an attached nvim session  or `a` to append it to the end of an attached nvim session.

If your document has an associated bibtex citekey (see below), yanked text will include a pandoc-style citation:

	[@author2015, p. 205]

(Other citation formats are not yet implemented.) Otherwise, it will construct a citation from the metadata:

	(Author, Title, p. 205)

Note that visual select mode is implemented using curses, and the smallest block you can select is a terminal cell. If you want higher 'resolution', adjust kitty's font size in the window.

Finally, to quit, just press `q`:

    q:              quit

# Config file

termpdf.py looks for a config file at `$HOME/.config/termpdf.py/config`. The
config file is a json file. Here is mine:

```
{
  "TINT_COLOR": "antiquewhite2",
  "BIBTEX": "/Users/desanso/d/research/zotero.bib",
  "NOTE_PATH": "/Users/desanso/org/inbox.org",
  "KITTYCMD": "kitty --single-instance --instance-group=1"
}
```

TINT_COLOR can be set to any color in pymupdf's [color database](https://pymupdf.readthedocs.io/en/latest/colors/). 

BIBTEX can be set to the path of a bibtex file with information about your documents. 

NOTE_PATH can be set to the path of a default notes file. The default is `$HOME/inbox.org`.

KITTYCMD is the command used to open new windows in kitty. My preferred setting is for kitty to open a new os window. If you'd prefer to have kitty open a new kitty window, replace KITTYCMD with something like:

   "KITTYCMD": "kitty @ new-window"

You can also set "URL_BROWSER". If this is not set, termpdf.py will use `open` on OSX, and otherwise, the first browser it finds from this list:

	'gnome-open', 'gvfs-open', 'xdg-open', 'kde-open', 'firefox', 'w3m',
	'elinks', 'lynx'

# citekeys and bibtex integration

If you use bibtex, you can associate a bibtex citekey with a document by using the `--citekey` cli option:

	termpdf.py --citekey author2015 example.pdf 

This information will be saved, so you don't need to specify the citekey every time you open the document. (Note that processing of cli options is dumb right now. If you try to open several documents and specify several citekeys, the last citeky specified will be applied to the first document, and the others will be ignored.)

If you have specified a bibtex file by setting BIBTEX in your config, and your bibtex includes a `File` field containing the path to your document, termpdf.py will attempt to discover the citekey automatically by matching the path, so you don't need to use the `--citekey` option. Likewise, if your bibtex includes a `File` field, you can open the document by specifying its key instead of its path:

	termpdf.py --open author2015

This works for several documents as well:

	termpdf.py --open author2015 --open author2016

Both of these features rely on pybtex, but it take awhile for pybtex to parse a large bibtex database. So, if `bibtool` is available, termpdf.py will use it to speed things up.

# nvim interaction

If you attempt to send a note to nvim, using `n` or `a`, and nothing has been
set up, termpdf.py will open a new window in kitty (using KITTYCMD), open nvim
in that window, and attach itself to that window, so that future notes will be
sent there as well.

Alternatively, you can specify an nvim_listen_address on the command line:

    termpdf.py --nvim-listen-address '/var/folders/tn/fjvms9ln3nvg8tztwcl31q1c0000gp/T/nvims23DfE/0'

You can find the address for your current nvim session, either as the value of
NVIM_LISTEN_ADDRESS, or as the value of `v:servername`:

    :echo $NVIM_LISTEN_ADDRESS
    :echo v:servername

You can set the address when launching nvim:

    nvim --listen '/tmp/termpdf_nvim_bridge'

But perhaps it is simplest to define a function in your nvimrc, to open
termpdf from within nvim. Here is the somewhat clunky function I am currently
using:

```
function! OpenPDFCitekey()
   let kcmd = 'kitty --single-instance --instance-group=1 '
   let kcmd = kcmd . 'termpdf.py --nvim-listen-address '
   let kcmd = kcmd . $NVIM_LISTEN_ADDRESS . ' '
   let key=expand('<cword>')
   keepjumps normal! ww
   let page=expand('<cword>')
   if page ==? 'p'
       keepjumps normal! ww
       let page=expand('<cword>')
   endif
   keepjumps normal! bbb
   let kcmd = kcmd . '--open ' . key . ' '
   if page
       let kcmd = kcmd . '-p ' . page 
   endif
   exe "!" . kcmd
endfunction
```

When called, this function treats the current word as a citekey, and attempts
to open the document associated with that citekey in termpdf.py, jumping to
the cited page if there is one. Notes will now be sent back to this document
in nvim.

# Features

## Document Formats

-   [x] supports the formats supported by mupdf. Tested with:
    -   [x] PDF
    -   [x] ePub
    -   [x] Html
    -   [x] CBZ
    -   [x] JPEG
-   [ ] add additional format support using other tools
    -   [ ] DJVU
    -   [ ] CBR
    -   [ ] DOCX
    -   [ ] ODT
    -   [ ] PPTX
    -   [ ] formats from which pandoc can generate html?
-   [ ] Support for encrypted documents (should be trivial to add with
    pymupdf)

## Commands and Interaction

-   [ ] support command line arguments
    -   [x] --help
    -   [x] --version
    -   [x] --page-number 
    -   [x] --first-page
	-   [x] --citekey
	-   [x] --open (by citekey)
-   [x] remember last-viewed page and document state
-   [ ] vim-style ex-mode
-   [ ] configuration file
    -   [ ] configurable key mappings
    -   [x] basic configuration
-   [x] Open multiple documents at once ("buffers")
-   [ ] Remote control from other apps
    -   [x] msgpack-rpc for interaction with nvim
        -   [x] send selected text to nvim buffer
        -   [x] send page number to buffer
        -   [ ] configurable format for sent text 
        -   [x] jump back from nvim to page in text
            (see the clunky vimscript function above)
    -   [ ] SyncTeX support
    -   [ ] jump to page, chapter, annotation, bookmark
    -   [ ] Note-taking integration ala org-noter

## Navigation

-   [x] vim-style navigation
    -   [x] next-page, prev-page (with counts)
    -   [x] next-chapter, prev-chapter (with counts)
    -   [x] jump to page number
    -   [x] jump to beginning, end of document
-   [ ] logical page numbers
    -   [ ] read/write to PDF
    -   [x] simple persistent page-offset setting
-   [x] navigate via table of contents
    -   [ ] outline folding support
-   [ ] Thumbnail mode
    -   [ ] Navigation
    -   [ ] Deleting pages
    -   [ ] Adding pages
    -   [ ] Moving pages within document
    -   [ ] Creating new document from selected pages
-   [x] Follow/fetch urls and internal links on page
-   [x] view document metadata
    -   [ ] edit metadata
    -   [x] update metadata from bibtex (requires that you set a citekey
            via the cli (`--citekey key`) and that you configure BIBTEX
            in the config file.

## Image Manipulation

-   [x] page rotation
    -   [ ] save rotation state to PDF
-   [x] toggle transparency
-   [x] invert colors ("dark mode")
-   [x] toggle tinted background
-   [ ] Cropping and zooming
    -   [x] autocrop margins
    -   [ ] fit to width
    -   [ ] fit to height
    -   [ ] arbitrary zooming 
    -   [ ] panning
-   [x] zoom in and out for reflowable documents

## PDF Manipulation

-   [ ] remove page(s) from PDF
-   [ ] combine PDFs
-   [ ] create new PDF from selected pages
-   [ ] move PDF pages
-   [ ] split two-up pages

## Notes, Annotations, Forms

-   [x] Send citation and current page number to nvim
-   [x] Send selected text with citation to nvim
-   [ ] Add and edit annotations
-   [ ] Extract annotations to org/markdown
-   [ ] Apply annotations from org/markdown
-   [ ] Fill out forms
    -   [ ] Document signing?

## Visual Mode 

-   [ ] Keyboard visual mode
    -   [x] Select by row
    -   [ ] Select by word
    -   [ ] Select by rectangle
    -   [x] Copy text selection: use the key 'y'
    -   [x] Insert selection in nvim buffer: use the key 'n'
    -   [x] Append selection to nvim_note file: use 'a'
    -   [ ] Copy selected image
    -   [ ] Crop to selection
    -   [ ] Insert annotation
-   [ ] Mouse mode
    -   [ ] Select by word
    -   [ ] Select by rectangle
    -   [ ] Copy text selection
    -   [ ] Copy image selection
    -   [ ] Insert annotation



