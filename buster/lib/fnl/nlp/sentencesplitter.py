#!/usr/bin/python
# -*- coding: UTF-8 -*-

# Created by  on 2007-02-28.
# Copyright (c) 2007 Florian Leitner.
# All rights reserved.
 
# GNU GPL LICENSE
#
# This module is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; latest version thereof,
# available at: <http://www.gnu.org/licenses/gpl.txt>.
#
# This module is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this module; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307, USA

"""sentencesplitter module

Created by  on 2007-02-28.
Copyright (c) 2007-2012 Florian Leitner. All rights reserved.
"""

import logging
import re

from fnl.nlp.utils import matchBracket

__version__ = "1"
__author__ = "Florian Leitner"

__dot_next = re.compile("([\.\?\!\:\;][\'\"]?[\s\n]+[\'\"]?[A-Z0-9])")
__newline = re.compile("[\n\s]+")
__logger = logging.getLogger("fnl.nlp.sentencesplitter")

def simpleSplit(text):
    """Splits at any occasion of ([\.\?\!\:\;][\'\"]?[\s\n]+[\'\"]?[A-Z0-9])
    adding the punctuation mark to the last sentences and the first letter to
    the next - 'greedy' version; newlines are substituted to whitespaces.
    """
    tokens = __dot_next.split(__newline.sub(" ", text))
    sentences = [""]
    for idx in xrange(len(tokens)):
        if idx % 2:
            sentences[-1] += tokens[idx][0]
            sentences.append(tokens[idx][-1])
        else:
            sentences[-1] += tokens[idx]
    return sentences

# basic structure of a sentence end is *<punct> <start sentence>*
# and includes possible quotation marks
__terminals = re.compile(".*?[\.\!\?\:\;][\'\"]?[\s\n]+[\'\"]?[A-Z0-9]")
# basic structure of <start sentence>
__beginnings = re.compile("[\'\"]?[A-Z0-9]")
# basic structure of <abbrev>
__abbreviations = re.compile("[\w\-]+\.[\s\n]+")
# last abbreviation in a sentence is *<abbrev><punct> <start sentence>*
__final_abb = re.compile("[\w\-]+\.[\.\!\?\:\;][\'\"]?[\s\n]+[\'\"]?[A-Z0-9]")
# sentences ending in abbreviations must look like *<abbrev><punct> finally
__final_abb_test = re.compile(".*?\.[\.\!\?\:\;][\'\"]?[\s\n]+$")

def __abbrevs(text, start=0, limit=None):
    match = __abbreviations.match(text, start)
    end = start
    # slurp abbreviations
    while match is not None:
        end += len(match.group())
        match = __abbreviations.match(text, end)
    match = __final_abb.match(text, end)
    # ensure we arrived at the final abbreviation
    if match is not None:
        end += len(match.group()) - 1
        if match.group()[-2] in ("'", '"'): end -= 1
    # Jump over abbreviations within the sentence (ie. we have no beginning
    # after position end) -> a false alarm was triggered
    # NOTE: this is the reason why "Bla bla end. Abbrev. next sentence."
    # is not split by this system! This is more or less impossible to split
    # without deep analysis of the sentence(s).
    if not __beginnings.match(text, end): return __next(text, end, limit)
    # return whatever we slurped in additionally (or not)
    return end

def __brackets(text, start, end, limit):
    # try to find the last valid closing bracket (even beyond end) if there is
    # a  matching opening bracket within text[start:end] and return the
    # position of it
    result = next = start
    while next != -1:
        __logger.debug("__brackets: start=%i, next=%i, end=%i, limit=%s"
                       % (start, next, end, str(limit)))
        next = text.find("(", next, end)
        if next != -1:
            __logger.debug("__brackets: start-next='%s'" % text[start:next])
            try:
                tmp = matchBracket(text, next, limit)
            except RuntimeError, msg:
                part = text
                try:
                    part = text[start:end]
                except IndexError, msg:
                    pass
                raise RuntimeError, \
                    "%s - start=%i, next=%i, end=%i, len=%i, txt='%s'" \
                    % (msg, start, next, end, len(text), part)
            __logger.debug("__brackets: tmp=%i" % tmp)
            if tmp > -1:
                result = next = tmp
            else:
                next = tmp
        __logger.debug("__brackets: next=%i" % next)
    return result

def __next(text, start=0, limit=None):
    match = __terminals.match(text, start)
    # no more terminals: return length of the text as end
    if match is None: return len(text)
    end = start + len(match.group()) - 1
    # see if we can jump over the current end because of brackets
    jump = __brackets(text, start, end, limit)
    # if so, recurse using the closing position of the bracktes as next start
    if jump > end: return __next(text, jump, limit)
    # move end by -1 if we matched quotation marks
    if match.group()[-2] in ("'", '"'): end -= 1
    # done if we are at a final abbreviation
    if __final_abb_test.match(text, start, end): return end
    # make sure any terminal abbreviations are slurped or we continue if this
    # was a false alarm
    return __abbrevs(text, end, limit)

def _sentences(text, start=0, limit=None):
    """Yield the index positions of the sentences in text."""
    length = len(text)
    end = __next(text, start, limit)
    while end != length:
        __logger.debug("yielding %i:%i='%s'" % (start, end, text[start:end]))
        yield start, end
        start = end
        end = __next(text, start, limit)
    __logger.debug("final yielding %i:%i" % (start, length))
    yield start, length

def split(text, limit=None):
    """More advanced version, which can handle strings like 'U. S. A.' or
    'Nat. Proc. Chem. Soc.' correctly (i.e. working 'non-greedy' by rather
    leaving a sentence joined than splitting it when it is not clear);
    newlines are substituted to whitespaces; finally, content in parenthesis
    is ignored and added to the sentence, as it quite often contains special 
    symbols and expressions those are more a hindrance than an advantage to 
    split up
    
    Set limit to a positive integer to define how far the algorithm should
    search for a closing bracket before it decides it is an unbalanced
    bracket. Good numbers are 250, 500 or 1000 characters.
    """
    clean_text = __newline.sub(" ", text)
    __logger.debug("clean_text='%s'" % clean_text)
    return [clean_text[start:end].strip()
            for start, end in _sentences(clean_text, limit=limit)]

if __name__ == '__main__':
    import sys
    if __debug__:
        sentences = [
            "Some normal text. Next sentence, follows up. Third and last.",
            "Test special; Next sentence: 'Third sentence!' This is the last?",
            "Abbreviations are tougher: U. S. A.. Now comes the second sent. Abb-rev. string!",
            "More advanced version, which can handle Nat. Proc. Chem. Soc. correctly.",
            "This does not work. Abb-rev. beginning a sentence are invisible.",
            "We are not chunking (This inner sentence stays undetected.); Only slight help.",
            "Inner Abb-rev. and abbrev. w. s-ig.? Should be just fine!",
            "Inner Abb-rev. and abbrev. w. s-ig.? Shld. not fail here either!",
            "Also special punctuation works... I hope at least...",
            "this kind of text is junk. lowercase and all without an end",
            "Some very (complicated (structure. Of) some. Ackward (inline (paragraphs. Hard) (but not) hartless.) but nice.) Continues (no. Stop) but here. Next has (another) bracket. Did this work?",
            "Some unbalanced (parenthesis (Don't split this.) (complicated (structure. Of) some. Ackward (inline (paragraphs. Hard) (but not) hartless.) but nice.) (complicated (structure. Of) some. Ackward (inline (paragraphs. Hard) (but not) hartless.) but nice.) Continues (no. Stop) but here. (complicated (structure. Of) some. Ackward (inline (paragraphs. Hard) (but not) hartless.) but nice.) Continues (no. Stop) but here. (complicated (structure. Of) some. Ackward (inline (paragraphs. Hard) (but not) hartless.) but nice.) Continues (no. Stop) but here. (complicated (structure. Of) some. Ackward (inline (paragraphs. Hard) (but not) hartless.) but nice.) Continues (no. Stop) but here. (complicated (structure. Of) some. Ackward (inline (paragraphs. Hard) (but not) hartless.) but nice.) Continues (no. Stop) but here. Split (no. Stop) this here. Can we split it?",
            ]
        for line in sentences:
            for sentence in split(line, limit=500): print sentence
        sys.exit(1)
    if len(sys.argv) < 2:
        print >> sys.stderr, "usage: %s textfile(s).." % sys.argv[0]
        sys.exit(1)
    for fn in sys.argv[1:]:
        lines = open(fn, "rT").readlines()
        text = " ".join([l.strip() for l in lines])
        for sentence in split(text, limit=500): print sentence

