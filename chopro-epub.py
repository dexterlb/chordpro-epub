#!python3
# -*- encoding: utf-8 -*-

# Copyright(c) 2019 Paul Ferrand

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files(the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from enum import Enum
import argparse
from ebooklib import epub
import os

import logging
import codecs
import pyparsing as pp

logging.basicConfig(level=logging.INFO, filename="info.log")

parser = argparse.ArgumentParser(
    description="Converts a batch of chordpro files into an epub"
)
parser.add_argument(
    "list", type=str, help="a list of chordpro files, one by line, to gather"
)
parser.add_argument(
    "--wrap-chords", action="store_true", help="wrap chords in square brackets"
)
parser.add_argument("--css", type=str, default="chopro-epub.css", help="CSS file to embed")
parser.add_argument(
    "--output", type=str, help="output file name", default="songbook.epub"
)
parser.add_argument("--book-title", type=str, help="book title", default="Songbook")
parser.add_argument(
    "--book-id", type=str, help="book identifier", default="songbook31415926535"
)
parser.add_argument("--book-author", type=str, help="songbook author")
args = parser.parse_args()

song_skeleton = """<h3>{0} ({1})</h3>{2}"""


def chordpro2html(song):
    title = "Unknown Title"
    artist = "Unknown Artist"
    output = ""

    SongState = Enum("SongState", "NONE VERSE CHORUS TAB BRIDGE")
    song_state = SongState.NONE
    text_buffer = ""

    # pyparsing parse-action handler

    def handle_empty_line(t):  # switch-bak songState
        nonlocal song_state
        if song_state == SongState.VERSE:  # reset from default state
            song_state = SongState.NONE
            return "</div>\n<br>"
        else:
            return "<br>"

    def handle_song_line(t):  # postponed handling of total line
        nonlocal text_buffer, song_state
        line_has_text = len(text_buffer.strip()) > 0
        text_buffer = ""  # not needed any longer
        line = ""  # prepare output-line

        if song_state == SongState.NONE:  # default state!
            song_state = SongState.VERSE
            line += '<div class="verse">'

        line += '<div class="songline">'
        for item in t:
            line += '<div class="chordbox">'

            # chord+text box ---------------------------------------
            if len(item) == 2:
                if args.wrap_chords:
                    line += '<div class="chord">' + item.chord + "</div>"
                else:
                    line += '<div class="chord">' + item.chord[1:-1] + "</div>"
                if line_has_text:
                    line += (
                        '<div class="text">'
                        + item.text.replace(" ", "&nbsp;")
                        + "</div>"
                    )

            # single chord box ---------------------------------------
            elif len(item) == 1 and len(item.chord) > 0:
                if args.wrap_chords:
                    line += '<div class="chord">' + item.chord + "</div>"
                else:
                    line += '<div class="chord">' + item.chord[1:-1] + "</div>"
                if line_has_text:
                    line += '<div class="text">&nbsp;</div>'

            # single text box ---------------------------------------
            elif len(item) == 1 and len(item.text) > 0:
                line += (
                    '<div class="text">' + item.text.replace(" ", "&nbsp;") + "</div>"
                )

            # unhandled...
            else:
                logging.info(item.dump())

            line += "</div>"  # ...chordbox
        line += "</div>"  # ...songLine
        return line

    def handle_text(t):  # store text in shadow buffer for later analysis
        nonlocal text_buffer
        text_buffer += t[0]
        return t

    def handle_env_directive(t):  # switch songState
        nonlocal song_state
        token = t[0].strip().lower()
        str_return = ""

        if song_state != SongState.NONE:  # force switching!
            song_state = SongState.NONE
            str_return += "</div>"

        if token in ["start_of_chorus", "soc"]:
            song_state = SongState.CHORUS
            str_return += '<div class="chorus">'
        elif token in ["start_of_tab", "sot"]:
            song_state = SongState.TAB
            str_return += '<div class="tab">'

        return str_return

    def handle_form_directive(t):  # only comments so far....
        token = t[0].strip().lower()
        arg = t[1]
        str_return = ""
        if token in ["comment", "c"]:
            arg = arg.replace("\n", "<br>")
            str_return += '<div class="comment">' + arg + "</div>"
        elif token in ["comment_box", "cb"]:
            arg = arg.replace("\n", "<br>")
            str_return += '<div class="commentbox">' + arg + "</div>"
        else:  # unhandled...
            logging.info(t.dump())
        return str_return

    def handle_meta_directive(t):
        nonlocal title, artist
        token = t[0].strip().lower()
        arg = t[1]
        str_return = ""
        if token in ["title", "t"]:
            title = arg
            str_return += '<div class="title">' + arg + "</div>"
        elif token in ["artist", "a"]:
            artist = arg
            str_return += '<div class="artist">' + arg + "</div>"
        else:  # unhandled...
            logging.info(t.dump())
        return str_return

    # pyparsing grammar definition: directives
    pp.ParserElement.setDefaultWhitespaceChars("")

    # lyricCharSet = pp.alphanums+pp.alphas8bit+",-_:;.!?#+*^°§$%&/|()='`´\\\"\t " # everything but "{}[]"
    lyric_char_set = pp.pyparsing_unicode.Latin1.printables + "\t "
    chord_char_set = pp.alphanums + " -#(%)/='`´."

    cmd = pp.oneOf("title t artist a")
    arg = pp.SkipTo("}")
    meta_directive = pp.Suppress("{") + cmd + pp.Suppress(":") + arg
    meta_directive.setParseAction(handle_meta_directive)

    cmd = pp.oneOf("comment c comment_box cb")
    arg = pp.SkipTo("}")
    form_directive = pp.Suppress("{") + cmd + pp.Suppress(":") + arg
    form_directive.setParseAction(handle_form_directive)

    cmd = pp.oneOf(
        "start_of_chorus soc end_of_chorus eoc start_of_tab sot end_of_tab eot"
    )
    env_directive = pp.Suppress("{") + cmd + pp.Suppress("}")
    env_directive.setParseAction(handle_env_directive)

    directives = meta_directive | form_directive | env_directive

    # pyparsing grammar definition: chordlines

    white_spaces = pp.Word(" \t")
    empty_line = (
        pp.LineStart() + pp.Optional(white_spaces) + pp.LineEnd()
    )  # incl. whiteSpaces
    empty_line.setParseAction(handle_empty_line)

    line_start = pp.LineStart()
    line_end = pp.Suppress(
        pp.LineEnd()
    )  ####### needs Unix type line-endings (at the moment...)

    chord = pp.Combine(
        "[" + pp.Word(chord_char_set) + "]"
    )  # leave square brackets there....
    text = pp.Word(lyric_char_set, excludeChars="[]{}")
    text.setParseAction(handle_text)

    chord_box = pp.Group(
        (chord("chord") + white_spaces("text"))
        | (  # whiteSpaces after chord seperates the chord from further text \
            chord("chord") + text("text")
        )
        | chord("chord")  # standard chordbox with chord AND text \
        | text("text")  # single chord w/o text \
    )  # single text w/o chord

    song_line = line_start + pp.OneOrMore(chord_box) + line_end
    song_line.setParseAction(handle_song_line)

    markup = (
        empty_line | song_line | directives
    )  # >emptyLine< MUST be bofore >songLine< to catch emptyLine-action

    for result in markup.searchString(song):
        output += result[0] + "\n"

    # logging.info(output)
    return output, title, artist


remove_punctuation_map = dict((ord(char), None) for char in r'\/*?:"<>|')

### Starting script per say

book = epub.EpubBook()

# Add metadata
book.set_identifier(args.book_id)
book.set_title(args.book_title)

if args.book_author is not None:
    book.add_author(args.book_author)

# Read the list
assert os.path.exists(args.list), "Nonexistent list file"
with open(args.list) as input_file:
    file_list = input_file.readlines()

# Parse chordpro files and fill the epub structure
for f in file_list:
    file_name = f.strip()
    if not os.path.exists(file_name):
        print(f"Could not open {file_name}, skipping")
        continue

    with codecs.open(file_name, "r", "utf-8") as file:
        body, title, artist = chordpro2html(file.read())

    song_title = f"{title} ({artist})"
    song_filename = f"{title}_{artist}.xhtml".translate(remove_punctuation_map)
    chapter = epub.EpubHtml(
        title=song_title,
        file_name=song_filename,
        lang="en",
    )
    chapter.add_link(href="style.css", rel="stylesheet", type="text/css")
    chapter.content = song_skeleton.format(title, artist, body)
    book.add_item(chapter)

# Setup TOC
chapter_list = list(book.get_items())
book.toc = tuple(chapter_list)

# Add style with default if none is specified
if (args.css is not None) and (os.path.exists(args.css)):
    with open(args.css) as css_file:
        style_css = epub.EpubItem(
            uid="style",
            file_name="style.css",
            media_type="text/css",
            content=css_file.read(),
        )
else:
    style_css = epub.EpubItem(
        uid="style", file_name="style.css", media_type="text/css", content=""
    )
book.add_item(style_css)

# add navigation files
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())

# create spine
book.spine = ["nav"] + chapter_list

epub.write_epub(args.output, book)
