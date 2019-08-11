# `kitty-pdf`

A document viewer, written in python, that works inside
[kitty](https://sw.kovidgoyal.net/kitty/). Hopefully a faster, less buggy,
more powerful---but less portable---replacement for
[termpdf](https://github.com/dsanson/termpdf).

-   Less portable because I have no plans of supporting graphics protocols
    other than [the terminal graphics
    protocol](https://sw.kovidgoyal.net/kitty/graphics-protocol.html)
    implemented by kitty.

-   Faster and more powerful because [PyMuPDF](https://pymupdf.readthedocs.io/) offers
    fast image conversion and access to lots of features.

-   Less buggy because it won't be a lovable but ridiculous hack of a bash script wrapped
    around a bunch of command line tools.

This is alpha version software. Expect bugs and undocumented dependencies. The
goal is feature parity with [pdf-tools](https://github.com/politza/pdf-tools).

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
-   [ ] Support for encrypted documents

## Commands and Interaction

-   [ ] support command line arguments
    -   [ ] --help
    -   [ ] --version
    -   [ ] --page-number
-   [ ] open to last-viewed page
-   [ ] vim-style ex-mode
-   [ ] configuration file
-   [ ] Open multiple documents at once ("buffers")
    -   [ ] synced plain text buffer
-   [ ] Remote control from other apps
    -   [ ] SyncTeX support
    -   [ ] jump to page, chapter, annotation, bookmark
    -   [ ] Note-taking integration ala org-noter
-   [ ] OCR
-   [ ] Extract document doi/isbn
    -   [ ] and add to metadata
    -   [ ] and pass to external command for fetching reference data 

## Navigation 

-   [x] vim-style navigation
    -   [x] next-page, prev-page (with counts)
    -   [x] next-chapter, prev-chapter (with counts)
    -   [x] jump to page number
    -   [x] jump to beginning, end of document
-   [x] navigate via table of contents
    -   [ ] outline folding support
-   [ ]  navigate with bookmarks
-   [ ] Thumbnail mode
    -   [ ] Navigation
    -   [ ] Deleting pages
    -   [ ] Adding pages
    -   [ ] Moving pages within document
    -   [ ] Creating new document from selected pages
-   [ ] Follow/fetch links in document

## Image Manipulation

-   [x] view document metadata
    - [ ] edit metadata
-   [x] page rotation
    - [ ] persistent rotation
-   [x] toggle transparency
-   [x] invert colors ("dark mode")
-   [x] toggle tinted background
-   [ ] Cropping and zooming
-   [ ] Reflowing (for ePub and Html)

## Annotations and Editing

-   [ ] Add and edit annotations
-   [ ] Add and navigate with bookmarks
-   [ ] Fill out forms
    -   [ ] Document signing?

## Visual and Mouse modes

-   [ ] Keyboard visual mode
    -   [ ] Select by word
    -   [ ] Select by rectangle
    -   [ ] Copy text selection
    -   [ ] Copy image selection
    -   [ ] Insert annotation
    -   [ ] Splitting pages
-   [ ] Mouse mode
    -   [ ] Select by word
    -   [ ] Select by rectangle
    -   [ ] Copy text selection
    -   [ ] Copy image selection
    -   [ ] Insert annotation
    -   [ ] Splitting pages


# Dependencies

```
pip install pymupdf
pip install curses
```

...and probably other stuff. 

