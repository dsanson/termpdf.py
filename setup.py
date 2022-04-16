#!/usr/bin/python3

from distutils.core import setup

setup(name='termpdf.py',
      version='0.1.0',
      description='Graphical pdf reader that works inside the kitty terminal',
      author='David Sanson',
      author_email='dsanson@gmail.com',
      url='https://github.com/dsanson/termpdf.py',
      scripts=['termpdf.py'],
      install_requires=[
          'PyMuPDF',
          'pyperclip',
          'pdfrw',
          'pybtex',
          'pynvim',
          'roman',
          'pagelabels'
          ]
     )
