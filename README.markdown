# `kitty-pdf`

A PDF viewer, written in python, that works inside
[kitty](https://sw.kovidgoyal.net/kitty/). Hopefully a faster, less buggy,
more powerful---but less portable---replacement for
[termpdf](https://github.com/dsanson/termpdf).

-   Less portable because I have no plans of supporting graphics protocols other
than [the terminal graphics
protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol.html) implemented
by kitty.

-   More powerful because [PyMuPDF](https://pymupdf.readthedocs.io/) offers
    fast image conversion access to lots of PDF features.

-   Less buggy because it won't be a lovable but ridiculous hack of a bash script wrapped
    around a bunch of command line tools.

This is alpha version software. Expect bugs and undocumented dependencies. The
goal is feature parity with [pdf-tools](https://github.com/politza/pdf-tools).

# Features

-   [x] vim-style navigation
    -   [x] next-page, prev-page (with counts)
    -   [x] next-chapter, prev-chapter (with counts)
    -   [x] jump to page number
    -   [x] jump to beginning, end of document
-   [] vim-style ex-mode
-   [x] navigate via table of contents
-   [x] view document metadata
    - [] edit metadata
-   [x] page rotation
-   [x] toggle transparency
-   [x] invert colors ("dark mode")
-   [x] toggle tinted background
-   [] Open multiple documents at once
-   [] Open other document formats
    -   [] epub, cbr, cbz: all "supported" by pymupdf
    -   [] djvu?
-   [] configurable shortcuts, tint color, etc.
-   [] Cropping and zooming
-   [] Add and edit annotations
-   [] Add and navigate with bookmarks
-   [] Follow/fetch links in document
-   [] Fill out forms
    -   [] Document signing?
-   [] Keyboard visual mode
    -   [] Select by word
    -   [] Select by rectangle
    -   [] Copy text selection
    -   [] Copy image selection
    -   [] Insert annotation
    -   [] Splitting pages
-   [] Mouse mode
    -   [] Select by word
    -   [] Select by rectangle
    -   [] Copy text selection
    -   [] Copy image selection
    -   [] Insert annotation
    -   [] Splitting pages
-   [] SyncTeX support
-   [] Thumbnail mode
    -   [] Navigation
    -   [] Deleting pages
    -   [] Adding pages
    -   [] Moving pages within document
    -   [] Creating new document from selected pages
-   [] OCR
-   [] Remote control from other apps
-   [] Note-taking integration ala org-noter
-   [] Support for encrypted documents
-   [] Extract document doi/isbn
    -   [] and add to metadata
    -   [] and pass to external command for fetching reference data 
-   [] Plain text mode (?)

# Dependencies

```
pip install pymupdf
pip install curses
```

...and probably some other stuff. 

