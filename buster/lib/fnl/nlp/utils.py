#!/usr/bin/python
# -*- coding: UTF-8 -*-

# Created by  on 2007-02-26.
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

"""utils module

Created by  on 2007-02-26.
Copyright (c) 2007 Florian Leitner. All rights reserved.
"""

import logging
import re

__version__ = "1"
__author__ = "Florian Leitner"

def __matchHelper(openers, closers):
    """Return the matching close position for the first open position."""
    o = openers.pop(0)
    
    if len(openers) == 0:
        return closers.pop(0)
    
    c = closers[0]
    
    if c < openers[0]:
        c = closers.pop(0)
        __matchHelper(openers, closers)
    else:
        __matchHelper(openers, closers)
        c = closers.pop(0)
    
    if o >= c:
        raise IndexError("open >= close: %i >= %i" % (o, c))
    
    return c

def matchBracket(text, offset, limit=None):
    """Find the matching bracket to the one found at offset in text.
    
    The bracket at offset must be one of the six in '({[]})' - otherwise a
    RuntimeError is raised.
    
    Returns the offset of the other bracket or -1 if no closing bracket could
    be found.
    """
    brackets = (('(', ')'), ('[', ']'), ('{', '}'))
    opening, closing = None, None
    reverse = False
    logger = logging.getLogger("fnl.nlp.utils.matchBracket")
    
    for (o, c) in brackets:
        if text[offset] == o:
            opening, closing = o, c
            break
        elif text[offset] == c:
            opening, closing = o, c
            reverse = True
            break
    
    if opening is None:
        raise RuntimeError("character at %i not a bracket: '%s'" %
                           (offset, text[offset]))
    if reverse:
        end = offset + 1
        start = 0 if limit is None else offset - limit
    else:
        start = offset
        end = None if limit is None else offset + limit
    
    logger.debug(
        "%smatching opening=%s and closing=%s from %i to %s",
        "reverse " if reverse else "", opening, closing, start, str(end)
    )
    openers = offsets(text, opening, start=start, end=end)
    closers = offsets(text, closing, start=start, end=end)
    
    if len(openers) == 0 or len(closers) == 0:
        return -1
    
    if reverse:
        openers.reverse()
        closers.reverse()
        tmp = [i * -1 for i in openers]
        openers = [i * -1 for i in closers]
        closers = tmp
    
    logger.debug("%i openers and %i closers", len(openers), len(closers))
    
    try:
        matching_bracket = __matchHelper(openers, closers)
    except IndexError:
        return -1
    
    if reverse:
        return matching_bracket * -1
    
    return matching_bracket

def ngrams(words, n, joinstr=' '):
    """Create a list of all possible ngrams of length n in the list of words.
    
    joinstr can be used to determine the string used to join the words,
    by default a whitespace character.
    """
    return [joinstr.join(words[i:i + n]) for i in range(len(words) - n + 1)]

def offsets(text, sub, start=0, end=None):
    """Return a list of offsets where sub is found in text.
    
    start and end can limit the search to a certain part of text."""
    if end is None:
        end = len(text)
    
    if start > end:
        raise IndexError("start > end: %i, %i" % (start, end))
    
    pos = text.find(sub, start, end)
    offsets = []
    
    while pos > -1 and pos < end:
        offsets.append(pos)
        pos = text.find(sub, pos + 1, end)
    
    return offsets

def stopWordFilter(text, stopwords, ignore_case=True):
    """Return the text filtered by stopwords.
    
    text - either a string (where each non-alphanumeric symbol is treated as
    word boundary) or a list of tokens
    stopwords - a list (or better: dictionary) of stopwords (in lowercase)
    """
    if type(text) == list:
        tokens = text
    else:
        tokens = re.split("[^\w]+", preprocess)
    if ignore_case:
        swf = lambda word: word.lower() not in stopwords
    else:
        swf = lambda word: word not in stopwords
    result = filter(swf, tokens)
    if tokens == text:
        return result
    return " ".join(result)