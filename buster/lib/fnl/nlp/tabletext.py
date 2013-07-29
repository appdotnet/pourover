#!/usr/bin/python
# -*- coding: UTF-8 -*-

# Created by  on 2007-02-28.
# Copyright (c) 2008 Florian Leitner.
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

"""Read tabulated text files.

Created by  on 2007-02-28.
Copyright (c) 2007 Florian Leitner. All rights reserved.
"""

__version__ = "2"
__author__ = "Florian Leitner"

from collections import namedtuple

DataRow = namedtuple('DataRow', 'uid text title more')

class BaseReader(object):
    """text -> str.strip()
    
    Allows to read the file object, retrieve the name, set and get the
    offset in the file (seek/tell), and retrieve the file size.
    """
    
    def __init__(self, fileobj):
        """Crete new reader object, setting the offset position to 0.
        """
        assert isinstance(fileobj, file)
        self.handle = fileobj
        self.lineno = None
        self.reset()
    
    def __iter__(self):
        return self
    
    def __repr__(self):
        return '%s("%s")' % (
            self.__class__.__name__, self.handle.name
        )
    
    def __str__(self):
        return "%s @ line %s (offset %s)" % (
            repr(self), str(self.lineno) if self.lineno is not None else "?",
            str(self.tell())
        )
    
    def name(self):
        return str(self.handle.name)
    
    def next(self):
        if self.lineno is not None:
            self.lineno += 1
        
        line = self.handle.readline()
        
        if line == '':
            raise StopIteration
        
        return line.strip()
    
    def reset(self):
        "Set offset position to 0 and reset the line number counter."
        self.seek(0)
        self.lineno = 0
        return self
    
    def seek(self, pos):
        "Go to the specified postion; The line number counter is invalidated."
        self.lineno = None
        
        if self.handle.name == "<stdin>":
            return -1
        
        return self.handle.seek(pos)
    
    def size(self):
        "Return the size of the file object."
        return os.stat(self.handle.name).st_size
    
    def tell(self):
        "Get the position in the file."
        if self.handle.name == "<stdin>":
            return -1
        
        return self.handle.tell()

class _FieldReader(BaseReader):
    """Split lines at filed_separator and return them as list of fields."""
    
    def __init__(self, fileobj, sep='\t'):
        BaseReader.__init__(self, fileobj)
        self.sep = str(sep)
    
    def __repr__(self):
        r = super(_FieldReader, self).__repr__()
        return r[:-1] + ', sep="%s")' % (self.sep)
    
    def next(self, test):
        line = BaseReader.next(self)
        data = map(lambda d: d.strip(), line.split(self.sep))
        assert test(data), "%s: wrong number of fields (%i)" % (
            str(self), len(data)
        )
        return data

class TextReader(_FieldReader):
    """id \\t text"""
    
    def next(self):
        data = super(TextReader, self).next(lambda d: len(d) == 2)
        return DataRow(data[0], data[1], None, None)

class MoreTextReader(_FieldReader):
    """id \\t text [\\t more...]"""
    
    def next(self):
        data = super(MoreTextReader, self).next(lambda d: len(d) > 1)
        
        if len(data) > 2:
            return DataRow(data[0], data[1], None, tuple(data[2:]))
        else:
            return DataRow(data[0], data[1], None, None)

class PositionalTextReader(_FieldReader):
    """id [\\t more...] \\t text [\\t more... ]"""
    
    def __init__(self, fileobj, colnum, field_separator='\t'):
        super(PositionalReader, self).__init__(fileobj, field_separator)
        self.colnum = int(colnum)
        assert self.colnum > 0, "first position reserved for UID"
    
    def __repr__(self):
        r = super(PositionalReader, self).__repr__()
        return r[:-1] + ', colnum=%i)' % (self.colnum)
    
    def next(self):
        data = super(PositionalReader, self).next(lambda d: len(d) > 1)
        text = data.pop(self.pos)
        uid = data.pop(0)
        
        if len(data):
            return DataRow(uid, text, None, tuple(data))
        else:
            return DataRow(uid, text, None, None)

class ArticleReader(_FieldReader):
    """id \\t title [\\t text]"""

    def next(self):
        data = super(ArticleReader, self).next(lambda d: len(d) in (2,3))
        text = "N/A" if  len(data) == 2 else data[2]
        return DataRow(data[0], text, data[1], None)

class MoreArticleReader(_FieldReader):
    """id \t title \t text [\t more...]"""

    def next(self):
        data = super(MoreArticleReader, self).next(lambda d: len(d) > 2)
        
        if len(data) > 3:
            return DataRow(data[0], data[2], data[1], tuple(data[3:]))
        else:
            return DataRow(data[0], data[2], data[1], None)

def write(data_rows, fileobj):
    """Write DataRow objects to an open file object."""
    for row in data_rows:
        if row.title is not None:
            if row.more is not None:
                print >> fileobj, "%s\t%s\t%s\t%s" % (
                    row.uid, row.title, row.text, '\t'.join(row.more)
                )
            else:
                print >> fileobj, "%s\t%s\t%s" % (
                    row.uid, row.title, row.text
                )
        elif row.more is not None:
            print >> fileobj, "%s\t%s\t%s" % (
                row.uid, row.text, '\t'.join(row.more)
            )
        else:
            print >> fileobj, "%s\t%s" % (row.uid, row.text)
