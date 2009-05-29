#!/usr/bin/env python

# Copyright 1999 by Ka-Ping Yee.  All rights reserved.
# This file is part of the Udanax Green distribution.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL Ka-Ping Yee OR Udanax.com BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
# THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# Except as contained in this notice, "Udanax", "Udanax.com", and the
# transcluded-U logo shall not be used in advertising or otherwise to
# promote the sale, use or other dealings in this Software without
# prior written authorization from Udanax.com.

import x88, tktrans
import sys, os, string, time

from Tkinter import *

REVISION = "$Revision: 2.3"
VERSION = x88.Address(string.split(REVISION)[1])
PROGRAM = "pyxi v" + str(VERSION)
SMALLFONT = "-*-helvetica-medium-r-normal-*-10-*-75-75-*-*-iso8859-1"
MONOFONT = "-*-courier-medium-r-normal-*-12-*-75-75-*-*-iso8859-1"
PROPFONT = "-*-times-medium-r-normal-*-14-*-75-75-*-*-iso8859-1"
INPUTBG = "#e0c8c0"
SOURCEFG = "#0000c0"
TARGETBG = "#d0a060"
MARKBG = "#b0b0b0"
DEFAULTBG = "#d9d9d9"

# editing states
(NOTEDITING, INSERTING, DELETING) = (1, 2, 3)

def warn(message):
    sys.stderr.write(PROGRAM + ": " + message + "\n")

class Notifier:
    def __init__(self):
        self.listeners = {}

    def listen(self, message, callback):
        if not self.listeners.has_key(message):
            self.listeners[message] = []
        self.listeners[message].append(callback)

    def unlisten(self, message, callback):
        if self.listeners.has_key(message):
            try: self.listeners[message].remove(callback)
            except ValueError: pass

    def send(self, message, data=None):
        if self.listeners.has_key(message):
            for callback in self.listeners[message]:
                callback(self, message, data)

class XuText(Text):
    """XuText - an augmented Text widget that groks Addresses and Spans."""

    def __init__(self, *args, **kwargs):
        self.docid = None
        apply(Text.__init__, (self,) + args, kwargs)

    # conversion among positions, indices, and addresses

    # any integer is considered a position (number of characters from start)
    # any string is considered an index (Tk-style line.char, mark, or tag)
    # any x88.Address is considered local if 2 tumbler digits, global if more

    def position(self, other):
        if type(other) is type(1) or other is None:
            return other
        elif type(other) is type(""):
            return len(self.get("1.0", other))
        elif x88.istype(x88.Address, other):
            if len(other) > 2:
                other = self.docid.localize(other)
            if other[0] != 1:
                raise ValueError, "%s is not in text region" % other
            return other[1] - 1
        else:
            raise TypeError, "%s is not an index, position, or address" % other

    def index(self, other):
        if type(other) is type(""):
            return Text.index(self, other)
        else:
            return "1.0 + %d c" % self.position(other)

    def vaddr(self, other):
        if x88.istype(x88.Address, other):
            return other
        else:
            return x88.Address(1, self.position(other) + 1)

    def addr(self, other):
        return self.docid.globalize(self.vaddr(other))

    def indices(self, vspan):
        if not x88.istype(x88.Span, vspan):
            raise TypeError, "%s is not a span" % vspan
        return self.index(vspan.start), self.index(vspan.end())

    def vspan(self, start, end):
        return x88.Span(self.vaddr(start), self.vaddr(end))

    # setting the selection and cursor position

    def setcur(self, other):
        self.mark_set("insert", self.index(other))

    def setsel(self, spec):
        self.tag_remove("sel", "0.0", "end")
        if x88.istype(x88.VSpec, spec):
            for span in spec.spans: self.addsel(span)
        else: self.addsel(spec)

    def addsel(self, span):
        if span is not None:
            start, end = self.index(span.start), self.index(span.end())
            self.tag_add("sel", start, end)

    # information about positions in the text widget

    def __len__(self):
        # Don't count the extra newline added by Tk.
        return self.position("end") - 1

    def selected(self):
        return len(self.tag_ranges("sel")) > 0

    def selind(self):
        range = self.tag_ranges("sel")
        if not range: raise ValueError, "no text is selected"
        return range

    def selvspan(self):
        start, end = self.selind()
        return x88.VSpan(self.docid, self.vspan(start, end))

    def selvspec(self):
        return x88.VSpec(self.docid, [self.selvspan().span])

    def scroll(self, top):
        self.yview("moveto", top + 0.000001)

    def tagspecset(self, name, specset):
        self.tag_delete(name)
        for spec in specset:
            if x88.istype(x88.Span, spec):
                try: self.tagspan(name, self.docid.localize(spec))
                except: pass
            elif x88.istype(x88.VSpec, spec):
                for vspan in spec: self.tagspan(name, vspan.span)

    def tagspan(self, name, vspan):
        start, end = self.indices(vspan)
        self.tag_add(name, start, end)

class Clipboard(Notifier):
    """Clipboard - a class for marking and moving regions of text.
    A single clipboard is shared among all the browser windows."""

    def __init__(self, xusession):
        Notifier.__init__(self)
        self.markspan = None
        self.marktext = None
        self.movable = 0
        self.xs = xusession

    def mark(self, vspan, text=None, movable=0):
        """Set the marked text region."""
        if self.markspan:
            self.marktext.tag_delete("clip")

        if vspan:
            start, end = text.indices(vspan.span)
            text.tag_add("clip", start, end)
            text.tag_configure("clip", background=MARKBG)
            self.movable = movable
        else:
            self.movable = 0

        self.markspan = vspan
        self.marktext = text
        self.send("mark")

    def unmark(self, text):
        """Unset the marked text region."""
        if text is self.marktext:
            self.mark(None)

    def marked(self):
        """Return true if there is some text marked."""
        return self.markspan is not None

    def vcopy(self, addr, text):
        """Transclude the marked text at the given address."""
        docid, vaddr = addr.split()
        self.xs.vcopy(docid, vaddr, x88.SpecSet(self.markspan))
        data = self.marktext.get("clip.first", "clip.last")
        text.insert(text.index(vaddr), data)
        text.setsel(x88.Span(vaddr, vaddr + x88.Offset(0, len(data))))
        text.see("insert")
        self.mark(None)

    def move(self, addr, text):
        """Move the marked text to the given address."""
        docid, vaddr = addr.split()
        if self.markspan.contains(addr):
            self.mark(None)
        elif self.markspan.docid == docid:
            # Move text within a document by pivoting it around.
            vspan = self.markspan.span
            if vaddr < vspan.start:
                self.xs.pivot(docid, vaddr, vspan.start, vspan.end())
            else:
                self.xs.pivot(docid, vspan.start, vspan.end(), vaddr)
            data = self.marktext.get("clip.first", "clip.last")
            text.insert("insert", data)
        else:
            # Move text to another document by doing vcopy and then remove.
            self.xs.vcopy(docid, vaddr, x88.SpecSet(self.markspan))
            data = self.marktext.get("clip.first", "clip.last")
            text.insert(text.index(vaddr), data)
            self.xs.remove(self.markspan.docid, self.markspan.span)

        # Select the newly-inserted text and unset the mark.
        text.setsel(x88.Span(vaddr, vaddr + x88.Offset(0, len(data))))
        text.see("insert")
        self.marktext.delete("clip.first", "clip.last")
        self.mark(None)

class Browser(Notifier, Frame):
    """Browser - the main widget for navigating and editing documents."""

    def __init__(self, parent, xusession, scrollside=RIGHT):
        Notifier.__init__(self)
        Frame.__init__(self, parent)
        self.xs = xusession

        # Build all the subwidgets.

        self.tool_frame = self.buildtoolbar(self)
        self.tool_frame.pack(side=TOP, fill=X)
        self.doc_menu = self.builddocmenu(self.doc_btn)
        self.edit_menu = self.buildeditmenu(self.edit_btn)
        self.link_menu = self.buildlinkmenu(self.link_btn)
        self.doc_frame = self.buildtextarea(self, scrollside)
        self.doc_frame.pack(fill=BOTH, expand=1)

        # Alt changes the cursor; Alt-Left and Alt-Right navigate the history.

        for widget in self, self.loc_entry, self.doc_text:
            for event in "KeyPress", "KeyRelease":
                for key in "Alt_L", "Alt_R":
                    widget.bind("<%s-%s>" % (event, key), self.eh_alt)
            widget.bind("<Alt-Left>", self.eh_back)
            widget.bind("<Alt-Right>", self.eh_fwd)

        # These keys can change the selection.

        for key in ["Shift_L", "Shift_R", "Up", "Down", "Left", "Right",
                    "Home", "End", "Prior", "Next"]:
            self.doc_text.bind("<KeyRelease-%s>" % key, self.eh_keyrelease)

        self.bind("<Enter>", self.eh_enter)
        self.bind("<Destroy>", self.eh_destroy)
        self.doc_text.focus()

        # Initialize member variables.

        self.sourceends = x88.SpecSet()
        self.targetends = x88.SpecSet()

        self.docid = None
        self.textspec = None
        self.textvspan = None
        self.linkvspan = None

        self.history = []
        self.histindex = 0

        self.busycount = 0
        self.xcursor = "xterm"

        self.editable = 0
        self.editstate = NOTEDITING
        self.editcount = 0

        self.linkactions = [(x88.MARGIN_TYPE, self.marginaction)]

    def buildtoolbar(self, parent):
        """Create the toolbar area."""
        frame = Frame(parent)

        self.loc_var = StringVar()
        self.loc_entry = Entry(frame, bd=1, width=8, background=INPUTBG,
                               textvariable=self.loc_var)
        self.loc_entry.bind("<Return>", self.eh_return)
        self.loc_entry.pack(side=LEFT, fill=X, expand=1)

        self.edit_label = Label(frame, pady=2, bd=1, font=SMALLFONT)
        self.edit_label.bind("<Button>", self.eh_click)

        self.doc_btn = Menubutton(frame, text="Document", padx=4, pady=0)
        self.edit_btn = Menubutton(frame, text="Edit", padx=4, pady=0)
        self.link_btn = Menubutton(frame, text="Link", padx=4, pady=0)

        self.back_btn = Button(frame, text="back", font=SMALLFONT,
                               state=DISABLED, padx=4, pady=1, bd=1,
                               command=self.cb_back)
        self.fwd_btn = Button(frame, text="fwd", font=SMALLFONT,
                              state=DISABLED, padx=4, pady=1, bd=1,
                              command=self.cb_fwd)
        self.reload_btn = Button(frame, text="reload", font=SMALLFONT,
                                 state=DISABLED, padx=4, pady=1, bd=1,
                                 command=self.cb_reload)
        for child in [self.reload_btn, self.fwd_btn, self.back_btn,
                      self.link_btn, self.edit_btn, self.doc_btn,
                      self.edit_label]:
            child.pack(side=RIGHT)
        return frame

    def builddocmenu(self, parent):
        """Create the Document menu."""
        parent["menu"] = menu = Menu(parent)

        menu.add_command(label="Open New Window",
                         command=self.cb_newwindow)
        menu.add_command(label="Create New Document",
                         command=self.cb_createdocument)
        menu.add_command(label="Import New Document",
                         command=self.cb_importdocument)
        menu.add_command(label="Export Current Document",
                         command=self.cb_exportdocument)
        menu.add_command(label="Create New Version",
                         command=self.cb_createversion)
        menu.add_separator()
        self.font_var = StringVar()
        self.font_var.set(PROPFONT)
        menu.add_radiobutton(label="Monospaced Font", value=MONOFONT,
                             command=self.cb_font, variable=self.font_var)
        menu.add_radiobutton(label="Proportional Font", value=PROPFONT,
                             command=self.cb_font, variable=self.font_var)
        self.spacing_var = IntVar()
        self.spacing_var.set(1)
        menu.add_checkbutton(label="Paragraph Spacing",
                             command=self.cb_font, variable=self.spacing_var)
        return menu

    def buildeditmenu(self, parent):
        """Create the Edit menu."""
        parent["menu"] = menu = Menu(parent)

        self.edit_var = IntVar()
        menu.add_checkbutton(label="Enable Editing",
                             command=self.cb_editable, variable=self.edit_var)
        menu.add_separator()
        menu.add_command(label="Mark", state=DISABLED,
                         command=self.cb_mark)
        menu.add_command(label="Transclude", state=DISABLED,
                         command=self.cb_vcopy)
        menu.add_command(label="Move", state=DISABLED,
                         command=self.cb_move)
        clipboard.listen("mark", self.updateeditmenu)
        return menu

    def buildlinkmenu(self, parent):
        """Create the Link menu."""
        parent["menu"] = menu = Menu(parent)

        menu.add_command(label="Add Source End",
                         command=self.cb_addsource, state=DISABLED)
        self.sourceindex = menu.index("end")
        menu.add_separator()
        menu.add_command(label="Add Target End",
                         command=self.cb_addtarget, state=DISABLED)
        self.targetindex = menu.index("end")
        menu.add_separator()
        menu.add_command(label="Create Link",
                         command=self.cb_link, state=DISABLED)
        menu.add_command(label="Clear Ends",
                         command=self.cb_clear, state=DISABLED)
        return menu

    def buildtextarea(self, parent, scrollside=RIGHT):
        """Create the text editing area."""
        frame = Frame(parent)

        self.doc_scroll = Scrollbar(frame, bd=2, width=11)
        self.doc_scroll.pack(side=scrollside, fill=Y)
        self.doc_text = XuText(frame, wrap=WORD, font=PROPFONT, spacing1=10)
        self.doc_text.pack(fill=BOTH, expand=1)
        def yview(cmd, pos, units=None, self=self):
            if units is None:
                self.doc_text.yview(cmd, pos)
            else:
                self.doc_text.yview(cmd, pos, units)
            self.send("scroll")
        self.doc_scroll.configure(command=yview)
        def scrollset(top, bottom, self=self):
            self.doc_scroll.set(top, bottom)
            self.send("scroll")
        self.doc_text.configure(yscrollcommand=scrollset)
        self.doc_text.bind("<KeyPress>", self.eh_key)
        self.doc_text.bind("<ButtonPress>", self.eh_click)
        self.doc_text.bind("<ButtonRelease>", self.eh_release)
        return frame

    # UI control

    def updatecursor(self):
        """Update the mouse pointer cursor."""
        if self.busycount > 0:
            self.configure(cursor="watch")
            self.loc_entry.configure(cursor="watch")
            self.doc_text.configure(cursor="watch")
        else:
            self.configure(cursor="")
            self.loc_entry.configure(cursor="xterm")
            self.doc_text.configure(cursor=self.xcursor)
        self.update()

    def busy(self):
        """Call this before doing a potentially lengthy operation."""
        self.busycount = self.busycount + 1
        self.updatecursor()

    def ready(self):
        """Call this after finishing a potentially lengthy operation."""
        if self.busycount > 0:
            self.busycount = self.busycount - 1
        self.updatecursor()

    def updatefwdback(self):
        """Update the forward and back buttons to reflect the history."""
        self.back_btn.configure(
            state=(self.histindex > 0 and NORMAL or DISABLED))
        self.fwd_btn.configure(
            state=(self.histindex < len(self.history) and NORMAL or DISABLED))
        self.reload_btn.configure(
            state=(self.docid and NORMAL or DISABLED))

    def updateeditmenu(self, *args):
        """Update the Edit menu to reflect the selection and clipboard state."""
        selected = self.doc_text.selected() and NORMAL or DISABLED
        self.edit_menu.entryconfigure(3, state=selected)
        self.edit_menu.entryconfigure(4, state=clipboard.marked() and \
            self.editable and NORMAL or DISABLED)
        self.edit_menu.entryconfigure(5, state=clipboard.marked() and \
            self.editable and clipboard.movable and NORMAL or DISABLED)

    def updatelinkmenu(self):
        """Update the Link menu to reflect the selection state."""
        linkends = self.sourceends or self.targetends

        last = self.link_menu.index("end")
        self.link_menu.entryconfigure(last - 1,
            state=linkends and self.editable and NORMAL or DISABLED)
        self.link_menu.entryconfigure(last,
            state=linkends and NORMAL or DISABLED)

        selected = self.doc_text.selected() and NORMAL or DISABLED
        self.link_menu.entryconfigure(self.sourceindex, state=selected)
        self.link_menu.entryconfigure(self.targetindex, state=selected)

    def setwidth(self, width):
        dummy = Label(font=self.doc_text.cget("font"), text="0", bd=0, padx=0)
        charwidth = dummy.winfo_reqwidth()
        width = width - self.doc_scroll.winfo_width()
        charcount = width / charwidth
        self.doc_text.config(width=charcount)

    # editing

    def deleteselection(self):
        """Delete the selected text and flush immediately to the back-end."""
        selvspan = self.doc_text.selvspan()
        self.finishedit()
        self.xs.remove(self.docid, selvspan.span)
        return selvspan.span

    def insertchar(self, ch):
        """Handle a single insert operation and buffer it."""
        #warn("entering insertchar")
        if self.editstate != INSERTING:
            self.finishedit()
            if self.doc_text.selected():
                self.insaddr = self.deleteselection().start
            else:
                self.insaddr = self.doc_text.vaddr("insert")
            self.inschars = []
            self.editstate = INSERTING

        if ch == "\r": ch = "\n"
        self.inschars.append(ch)
        self.editcount = self.editcount + 1
        self.edit_label.config(text="%3d" % self.editcount,
                               foreground="darkgreen", relief=SUNKEN)
        self.doc_text.insert("insert", ch)
        self.doc_text.tag_remove("source", "insert - 1 c", "insert")
        self.doc_text.tag_remove("target", "insert - 1 c", "insert")
        self.doc_text.tag_remove("type", "insert - 1 c", "insert")
        self.doc_text.see("insert")
        clipboard.unmark(self.doc_text)
        if self.doc_text.selected():
            self.doc_text.delete("sel.first", "sel.last")
        self.send("edit")
        return "break"

    def deletechar(self, ch):
        """Handle a single delete operation and buffer it."""
        if self.doc_text.selected():
            self.deleteselection()
            self.send("edit")
            return

        if self.editstate != DELETING:
            self.finishedit()
            self.delmin = self.delmax = self.doc_text.position("insert")
            self.deletelimit = len(self.doc_text)
            self.editstate = DELETING

        if ch == "\010" and self.delmin > 0:
            self.delmin = self.delmin - 1
        if ch == "\177" and self.delmax < self.deletelimit:
            self.delmax = self.delmax + 1
        self.editcount = self.editcount + 1
        self.edit_label.config(text="%3d" % self.editcount,
                               foreground="darkred", relief=SUNKEN)
        clipboard.unmark(self.doc_text)
        self.send("edit")

    def finishedit(self):
        """Flush the current editing operation to the back-end."""
        #warn("entering finishedit")
        if self.editstate != NOTEDITING:
            #warn("inside finishedit")
            if self.editstate == INSERTING:
                text = string.join(self.inschars, "")
                self.xs.insert(self.docid, self.insaddr, [text])
            if self.editstate == DELETING:
                vspan = self.doc_text.vspan(self.delmin, self.delmax)
                self.xs.remove(self.docid, vspan)
            self.editstate = NOTEDITING
        self.editcount = 0
        try: self.edit_label.config(text="", foreground="black", relief=FLAT)
        except TclError: pass

    # keyboard event handlers

    def eh_key(self, event):
        """Handle a keypress in the text editing area."""

        #warn("entering eh_key char:%s;state:%d;keysym:%s" %
        #       (event.char, event.state, event.keysym))

        if event.keysym[-2:] in ["_L", "_R"]: # Ignore keypress on modifiers.
            #warn("in eh_key ignoring modifier")
            return

        # Filter out some modified keypresses
        if event.state & 1: # Allow Shift
            pass
        elif event.state & 2: # Allow Caps Lock
            pass
        elif event.state & 4: # Ignore Ctrl-*
            #warn("in eh_key ignoring ctrl %d" % event.state)
            return "break"
        elif event.state & 8: # Ignore mod1: Alt-* on my machine
            return
        elif event.state & 16: # Allow mod2: Numlock
            pass
        elif event.state: # Ignore if any other modifier is on.
            #warn("in eh_key ignoring other modifier %d" % event.state)
            return

        if event.char in ["\010", "\177"]:
            #warn("in eh_key delete char %s" % event.char)
            if not self.editable: return "break"
            return self.deletechar(event.char)
        elif event.char >= " " or event.char in ["\t", "\r"]:
            if not self.editable: return "break"
            return self.insertchar(event.char)
        else:
            return self.finishedit()

    def eh_keyrelease(self, event):
        """Update menus when Shift or a cursor-movement key is released,
        since these keys can cause the selection to change."""
        self.updateeditmenu()
        self.updatelinkmenu()

    def eh_alt(self, event):
        """Update the cursor when Alt is depressed or released."""
        if event.type == "2": # KeyPress
            self.xcursor = "hand2"
        elif event.type == "3": # KeyRelease
            self.xcursor = "xterm"
        self.updatecursor()

    def eh_enter(self, event):
        """Do various updates when the mouse pointer enters the window.
        While the pointer has been away, another window may have cleared
        our selection, or the Alt key may have been depressed."""
        self.updateeditmenu()
        self.updatelinkmenu()
        self.xcursor = event.state & 8 and "hand2" or "xterm"
        self.updatecursor()

    def eh_return(self, event):
        """Go to the address that has been entered into the location field."""
        location = string.strip(self.loc_var.get())
        self.loc_var.set(location)
        try:
            addr = x88.Address(location)
        except ValueError:
            tktrans.error(self,
                "\"%s\" is not a well-formed tumbler." % location,
                "Invalid Address")
            self.loc_var.set(self.docid)
            return
        try:
            self.xs.open_document(addr, x88.READ_ONLY, x88.CONFLICT_COPY)
            try:
                self.xs.retrieve_vspanset(addr)
            finally:
                self.xs.close_document(addr)
        except x88.XuError:
            tktrans.error(self,
                "There is no document at the address \"%s\"." % location,
                "Invalid Address")
            self.loc_var.set(self.docid)
            return
        self.browse(addr)

    def eh_fwd(self, event):
        self.cb_fwd()
        return "break"

    def eh_back(self, event):
        self.cb_back()
        return "break"

    def eh_destroy(self, event):
        if not event.widget == str(self): return
        try: self.closedoc()
        except (IOError, x88.XuError): pass

    # toolbar callbacks and event handlers

    def cb_fwd(self):
        """Navigate one step forward in the history stack."""
        if self.histindex >= len(self.history): return
        self.fwd_btn.configure(relief=SUNKEN)
        self.fwd_btn.update()
        origin, dest = self.history[self.histindex]
        self.goto(dest)
        self.histindex = self.histindex + 1
        self.fwd_btn.configure(relief=RAISED)
        self.updatefwdback()

    def cb_back(self, event=None):
        """Navigate one step backward in the history stack."""
        if self.histindex < 1: return
        self.back_btn.configure(relief=SUNKEN)
        self.back_btn.update()
        self.histindex = self.histindex - 1
        origin, dest = self.history[self.histindex]
        spec, top = origin
        self.goto(spec, top)
        self.back_btn.configure(relief=RAISED)
        self.updatefwdback()

    def cb_reload(self):
        self.reload()

    # document menu callbacks

    def cb_newwindow(self):
        """Open a new window on the same document."""
        window = BrowserWindow(self.xs)
        window.goto(self.docid)

    def cb_createdocument(self):
        """Create a new document and open it for editing in a new window."""
        docid = self.xs.create_document()
        docid = self.xs.open_document(
            docid, x88.READ_WRITE, x88.CONFLICT_COPY)
        # workaround: back-end acts weird on empty documents
        self.xs.insert(docid, x88.Address(1, 1), [" "])
        self.xs.close_document(docid)
        window = BrowserWindow(self.xs)
        window.goto(docid, editable=1)

    def importstuff(self,input):
        """import the stuff in the opened input"""
        if self.editable:
            docid = self.docid
            address = self.doc_text.vaddr("insert")
        else:
            docid = self.xs.create_document()
            docid = self.xs.open_document(
                docid, x88.READ_WRITE, x88.CONFLICT_COPY)
            address = x88.Address(1, 1)

        while 1:
            # workaround: insert buffer in the back-end has a limited size
            data = input.read(900)
            if not data: break
            self.xs.insert(docid, address, [data])
            address = address + x88.Offset(0, len(data))
        self.xs.close_document(docid)
        return docid

    def importdir(self,dirpath,dirs): # called by walk
        """ import contents of the directory """
        for file  in dirs:
            file = os.path.join(dirpath,file)
            if(os.path.isfile(file)): # don't do the directories
                try:
                    input = open(os.path.join(dirpath,file))
                    docid = self.importstuff(input)
                    f = file + "\n"
                    self.xs.insert(self.indexdocid,self.address,[f])
                    sourcespec = x88.SpecSet(x88.VSpec(self.indexdocid,[x88.Span(self.address, x88.Offset(0, len(file)))]))
                    targetspec = x88.SpecSet(x88.VSpec(docid,[x88.Span(x88.Address(1, 1), x88.Offset(0, 1))]))
                    self.address = self.address + x88.Offset(0, len(f))
                    self.xs.create_link(self.indexdocid, sourcespec, targetspec,
                                x88.SpecSet(x88.JUMP_TYPE))
                    #print "opened the file \"%s\"." % os.path.join(dirpath,file)
                except IOError:
                     print "Could not open the file \"%s\"." % os.path.join(dirpath,file)

    def cb_importdocument(self):
        """Read a file or the output of a command, and either insert it
        into the current document if it's editable, or put it into a new
        document otherwise.  if it's a directory (or link or mount) make
        a file with the paths in it and link all the files  to that after
        importing  them"""
        file = tktrans.getstring(self,
            "Enter a filename (or a command followed by \"|\"):",
            self.editable and "Insert Document" or "Import Document")
        if file is None: return
        file = string.strip(file)
        if not file: return

        self.busy()
        try:
            if file[-1:] == "|":
                input = os.popen(file[:-1], "r")
                docid = self.importstuff(input)
            elif(os.path.isdir(file)):
                self.indexdocid = self.xs.create_document()
                self.indexdocid = self.xs.open_document(
                    self.indexdocid, x88.READ_WRITE, x88.CONFLICT_COPY)
                self.address = x88.Address(1, 1)
                os.path.walk(file,Browser.importdir,self)
                docid = self.indexdocid
                self.xs.close_document(self.indexdocid)
            else:
                try:
                    input = open(file)
                    docid = self.importstuff(input)
                except IOError:
                    tktrans.error(self,
                        "Could not open the file \"%s\"." % file,
                        "Import Failed")
                    return

            if self.editable:
                self.reload()
            else:
                window = BrowserWindow(self.xs)
                window.goto(docid)

        finally:
            self.ready()

    def cb_exportdocument(self):
        """ export the text  of the  current document, currently as a
        flat text, later perhaps as html or xml or a real standard  when that
        becomes possible"""
        file = tktrans.getstring(self,
            "Enter a filename ")
        if file is None: return
        file = string.strip(file)
        if not file: return
        #print self.doc_text.get("0.0","end")

        output = open(file,"w")
        output.write(self.doc_text.get("0.0","end"))
        output.close();

    def cb_createversion(self):
        """Create a new version of the current document and open it for
        editing in a new window."""
        docid = self.xs.create_version(self.docid)
        window = BrowserWindow(self.xs)
        window.goto(docid, editable=1)

    def cb_font(self):
        """Change the font or spacing settings."""
        self.doc_text.config(font=self.font_var.get(),
                             spacing1=self.spacing_var.get() and 10 or 0)

    # edit menu callbacks

    def cb_editable(self):
        """Reopen the document when the "Enable Editing" box is toggled."""
        docid = self.docid
        self.closedoc()
        self.opendoc(docid, editable=self.edit_var.get())
        self.updateeditmenu()
        self.updatelinkmenu()

    def cb_mark(self):
        """Set the selected span of the text as the marked region."""
        clipboard.mark(self.doc_text.selvspan(), self.doc_text, self.editable)

    def cb_vcopy(self):
        """Transclude the marked text at the text cursor location."""
        clipboard.vcopy(self.doc_text.addr("insert"), self.doc_text)

    def cb_move(self):
        """Move the marked text to the text cursor location."""
        clipboard.move(self.doc_text.addr("insert"), self.doc_text)

    # link menu callbacks

    def cb_link(self):
        """Create a new link with the link ends listed in the Link menu."""
        choices = map(lambda t: (string.capitalize(x88.TYPE_NAMES[t]), t),
                      x88.LINK_TYPES)
        result = tktrans.choose(
            self, choices, "Select a link type:", "Link Type")
        if result:
            self.xs.create_link(self.docid, self.sourceends, self.targetends,
                                x88.SpecSet(result))
            self.cb_clear()
            self.showendsets()

    def cb_clear(self):
        """Clear the link ends from the Link menu."""
        menulength = self.link_menu.index("end")
        if self.targetends:
            self.link_menu.delete(self.targetindex + 1, menulength - 3)
            self.targetends.clear()
        if self.sourceends:
            self.link_menu.delete(self.sourceindex + 1, self.targetindex - 2)
            self.sourceends.clear()
        self.targetindex = self.sourceindex + 2
        self.updatelinkmenu()

    def cb_addsource(self):
        """Add the selected span to the list of source ends in the Link menu."""
        if not self.doc_text.selected(): return
        vspec = self.doc_text.selvspec()
        self.sourceends.append(vspec)

        def jump(browse=self.browse, vspec=vspec): browse(vspec)
        self.link_menu.insert_command(self.sourceindex + len(self.sourceends),
            label=str(vspec)[1:-1], command=jump)

        self.targetindex = self.targetindex + 1
        self.updatelinkmenu()

    def cb_addtarget(self):
        """Add the selected span to the list of target ends in the Link menu."""
        if not self.doc_text.selected(): return
        vspec = self.doc_text.selvspec()
        self.targetends.append(vspec)

        def jump(browse=self.browse, vspec=vspec): browse(vspec)
        self.link_menu.insert_command(self.targetindex + len(self.targetends),
            label=str(vspec)[1:-1], command=jump)

        self.updatelinkmenu()

    # text area event handlers

    def eh_nothing(self, event):
        """This temporary callback prevents mouse activity from affecting
        a newly-loaded document after clicking on a link."""
        self.doc_text.unbind("<Button>")
        return "break"

    def eh_click(self, event):
        """Flush the editing operation when a click moves the cursor."""
        self.finishedit()

    def eh_release(self, event):
        """Update menus when a mouse button is release, since this could
        cause the selection to change."""
        self.updateeditmenu()
        self.updatelinkmenu()

    def findvspan(self, specset, span):
        """Return the unique vspan in a specset containing the given span."""
        result = None
        for vspec in specset:
            for vspan in vspec:
                if vspan.contains(span):
                    if result: return None # not unique
                    else: result = vspan
        return result

    def eh_linkend(self, event):
        """Traverse a link when the user clicks on a link end in the text."""
        self.finishedit()
        self.busy()
        try:
            # Get the address and span of the character at the mouse pointer.
            vaddr = self.doc_text.vaddr("current")
            charspan = x88.Span(vaddr, x88.Offset(0, 1))
            specend = x88.SpecSet(x88.VSpec(self.docid, [charspan]))
            clickspan = self.docid.globalize(charspan)

            # Find the first source or target link end at the clicked spot.
            dest = None
            direction = 0
            links = self.xs.find_links(specend)
            if links:
                dests = self.xs.follow_link(links[0], x88.LINK_TARGET)
                origins = self.xs.follow_link(links[0], x88.LINK_SOURCE)
                if dests: dest = dests[0]
                direction = 1
            else:
                links = self.xs.find_links(x88.NOSPECS, specend)
                if links:
                    dests = self.xs.follow_link(links[0], x88.LINK_SOURCE)
                    origins = self.xs.follow_link(links[0], x88.LINK_TARGET)
                    if dests: dest = dests[0]
                    direction = -1

            if dest:
                # Check the type of the link and do the appropriate action.
                types = self.xs.follow_link(links[0], x88.LINK_TYPE)
                for type, function in self.linkactions:
                    if type in types:
                        if function(links[0], origins, dests, direction):
                            break
                else:
                    origin = self.findvspan(origins, clickspan) or clickspan
                    self.browse(dest, origin)

        finally:
            self.ready()
        self.doc_text.focus()
        self.doc_text.bind("<Button>", self.eh_nothing)
        return "break"

    def marginaction(self, link, origins, dests, direction):
        """To present a "marginal note" type of link, display the text
        of the target end of the link in a pop-up message box."""
        if direction == 1:
            docids = {}
            for target in dests:
                if x88.istype(x88.Span, target):
                    docids[target.start.split()[0]] = 1
                if x88.istype(x88.VSpec, target):
                    docids[target.docid] = 1
            for docid in docids.keys():
                self.xs.open_document(
                    docid, x88.READ_ONLY, x88.CONFLICT_COPY)
            data = string.join(self.xs.retrieve_contents(dests), "")
            for docid in docids.keys():
                self.xs.close_document(docid)

            tktrans.MessageBox(self, "Marginal Note", data)
            return 1

    def eh_linkprop(self, event):
        """Present a popup with information about a link end."""
        self.finishedit()
        self.busy()
        try:
            vaddr = self.doc_text.vaddr("current")
            charspan = x88.Span(vaddr, x88.Offset(0, 1))
            specset = x88.SpecSet(x88.VSpec(self.docid, [charspan]))

            links = self.xs.find_links(specset) + \
                    self.xs.find_links(x88.NOSPECS, specset) + \
                    self.xs.find_links(x88.NOSPECS, x88.NOSPECS, specset)
            if links:
                clickspan = specset[0][0]
                if len(links) == 1:
                    self.link_popup = Menu()
                    link = links[0]
                    self.buildlinkpopup(self.link_popup, link, clickspan)
                else:
                    self.link_popup = Menu(tearoff=0)
                    for link in links:
                        menu = Menu(self.link_popup)
                        self.buildlinkpopup(menu, link, clickspan)
                        self.link_popup.add_cascade(
                            label="Link %s" % str(link), menu=menu)
                rootx = event.x + self.winfo_rootx()
                rooty = event.y + self.winfo_rooty()
                self.link_popup.post(rootx, rooty)
        finally:
            self.ready()

        return "break"

    def buildlinkpopup(self, menu, link, clickspan):
        """Construct the popup menu describing a given link."""
        typenames = []
        try:
            specset = self.xs.follow_link(link, x88.LINK_TYPE)
            for spec in specset:
                if spec in x88.LINK_TYPES:
                    typenames.append(x88.TYPE_NAMES[spec])
        except x88.XuError: pass

        label = "Link %s" % str(link)
        if typenames:
            label = label + " (" + string.join(typenames, ", ") + ")"
        menu.add_command(label=label, state=DISABLED)

        for label, end in (("Source", x88.LINK_SOURCE),
                           ("Target", x88.LINK_TARGET)):
            menu.add_separator()
            menu.add_command(label="%s Ends" % label, state=DISABLED)
            specset = self.xs.follow_link(link, end)
            for spec in specset:
                def jump(self=self, spec=spec): self.browse(spec)
                colour = spec.contains(clickspan) and "red" or "black"
                menu.add_command(label=str(spec)[1:-1], command=jump,
                                 foreground=colour, activeforeground=colour)

    # document navigation

    def reload(self):
        """Reload the document, preserving the view and cursor position."""
        self.finishedit()
        top, bottom = self.doc_text.yview()
        cursor = self.doc_text.index("insert")
        self.busy()
        try:
            self.loaddoc(self.docid, self.editable)
            self.doc_text.scroll(top)
            self.doc_text.setcur(cursor)
        finally:
            self.ready()

    def goto(self, spec, top=None, editable=0):
        """Navigate to a given address or span without recording history."""
        self.finishedit()
        self.busy()
        try:
            if x88.istype(x88.Address, spec):
                if spec != self.docid:
                    self.loaddoc(spec, editable)
                if top: self.doc_text.scroll(top)

            elif x88.istype(x88.Span, spec):
                self.goto(spec.localize(), top, editable)
                if top: self.doc_text.scroll(top)

            elif x88.istype(x88.VSpan, spec):
                if spec.docid != self.docid:
                    self.loaddoc(spec.docid, editable)
                if top: self.doc_text.scroll(top)

                start, end = self.doc_text.indices(spec.span)
                self.doc_text.see(start)
                self.doc_text.see(end)
                self.doc_text.setsel(spec.span)
                self.doc_text.setcur(end)

            elif x88.istype(x88.VSpec, spec):
                if len(spec): self.goto(spec[0], top, editable)
                self.doc_text.setsel(spec)

        finally:
            self.ready()

    def browse(self, spec, origin=None):
        """Navigate to a given address or span, recording a history entry."""
        top, bottom = self.doc_text.yview()
        here = (origin or self.docid), top
        self.goto(spec)
        self.history[self.histindex:] = [(here, spec)]
        self.histindex = self.histindex + 1
        self.updatefwdback()

    def showendsets(self):
        """Highlight all the link ends in the current document."""
        source, target, type = self.xs.retrieve_endsets(self.textspec)
        self.doc_text.tagspecset("source", source)
        self.doc_text.tagspecset("target", target)
        self.doc_text.tag_configure("source", underline=1, foreground=SOURCEFG)
        self.doc_text.tag_bind("source", "<Alt-Button-1>", self.eh_linkend)
        self.doc_text.tag_bind("source", "<Button-3>", self.eh_linkprop)
        self.doc_text.tag_configure("target", background=TARGETBG)
        self.doc_text.tag_bind("target", "<Alt-Button-1>", self.eh_linkend)
        self.doc_text.tag_bind("target", "<Button-3>", self.eh_linkprop)

    def loaddoc(self, docid, editable=0):
        """Load a document into the text area."""
        self.closedoc()
        self.opendoc(docid, editable)
        self.showdoc()
        self.showendsets()

    def opendoc(self, docid, editable=0):
        """Open a document, optionally for editing."""
        mode = editable and x88.READ_WRITE or x88.READ_ONLY
        docid = self.xs.open_document(docid, mode, x88.CONFLICT_COPY)

        self.textvspan = self.linkvspan = None
        for vspan in self.xs.retrieve_vspanset(docid):
            span = vspan.span
            if vspan.span.start[0] == 1:
                # This will break if the back-end returns more than one span.
                self.textvspan = vspan.span
            elif vspan.span.start[0] == 2:
                self.linkvspan = vspan.span
            else:
                warn("ignoring vspan %s" % vspan)

        if self.textvspan is not None:
            textvspec = x88.VSpec(docid, [self.textvspan])
            self.textspec = x88.SpecSet(textvspec)
        else:
            warn("document contains no data")

        self.loc_var.set(str(docid))
        self.doc_text.docid = self.docid = docid
        self.editable = editable
        self.doc_menu.entryconfigure(
            3, label=editable and "Insert Document" or "Import New Document")
        self.doc_text.config(bg=editable and INPUTBG or DEFAULTBG)
        self.doc_scroll.config(bg=editable and INPUTBG or DEFAULTBG)
        self.edit_var.set(editable)
        self.updatefwdback()
        self.send("opendoc")

    def showdoc(self):
        """Display the contents of a document in the text area."""
        if self.textvspan is not None:
            text = self.xs.retrieve_contents(self.textspec)[0]
            self.doc_text.delete("1.0", "end")
            self.doc_text.insert("1.0", text)

    def closedoc(self):
        """Clean up and close the current document."""
        self.finishedit()
        if self.docid:
            self.xs.close_document(self.docid)
        self.doc_text.docid = self.docid = None
        self.textspec = None
        self.textvspan = None
        self.linkvspan = None
        clipboard.unmark(self.doc_text)
        self.send("closedoc")

class BrowserWindow(Toplevel):
    """BrowserWindow - a Window containing a single Browser."""

    def __init__(self, xusession, title=PROGRAM):
        Toplevel.__init__(self)
        windows[self] = 1
        self.title(title)
        self.browser = Browser(self, xusession, scrollside=LEFT)
        self.browser.pack(fill=BOTH, expand=1)
        self.bind("<Destroy>", self.eh_destroy)
        self.bind("<Alt-q>", self.eh_quit)

    def goto(self, spec, top=None, editable=0):
        self.browser.goto(spec, top, editable)

    def browse(self, spec, origin=None):
        self.browser.browse(spec, origin)

    def quit(self):
        try: self.browser.closedoc()
        except (IOError, x88.XuError): pass
        Toplevel.quit(self)

    def eh_quit(self, event):
        self.quit()

    def eh_destroy(self, event):
        """Close the window; quit the application if this is the last one."""
        if not event.widget == str(self): return
        try: self.browser.closedoc()
        except (IOError, x88.XuError): pass

        if windows.has_key(self):
            del windows[self]
            if not windows.keys(): self.quit()
        else:
            return "break"

class TwoBrowserWindow(BrowserWindow):
    """TwoBrowserWindow - a Window that can optionally display two Browsers
    and draw transpointing lines between them connecting common sections."""

    commoncolours = ["#ffc0c0", "#ffe0a0", "#ffffc0", "#c0ffc0",
                     "#c0e0ff", "#c0c0ff", "#e0a0ff"]

    def __init__(self, xusession, title=PROGRAM):
        BrowserWindow.__init__(self, xusession, title)
        self.xs = xusession
        self.browser2 = None
        self.comparing = 0
        self.bind("<Alt-p>", self.eh_parallel)

    def eh_config(self, event):
        if event.widget is self and self.browser2:
            self.fixsize()

    def fixsize(self):
        width = self.winfo_width()
        height = self.winfo_height()
        brwidth = (width-120)/2
        self.browser.setwidth(brwidth)
        self.browser2.setwidth(brwidth)

    def eh_parallel(self, event):
        """Toggle display of the second browser pane."""
        if self.browser2:
            for browser in self.browser, self.browser2:
                browser.unlisten("opendoc", self.updatecompare)
                browser.unlisten("closedoc", self.cb_closedoc)

            self.browser.forget()
            self.trans_frame.forget()
            self.browser2.closedoc()
            self.browser2.forget()

            self.browser.pack(fill=BOTH, expand=1)
            self.browser2 = None
            self.bind("<Configure>", "")

        else:
            self.browser.forget()
            self.trans_frame = Frame(self, width=100)
            self.browser2 = Browser(self, self.browser.xs)

            self.browser.pack(fill=BOTH, side=LEFT)
            self.browser2.pack(fill=BOTH, side=RIGHT)
            self.trans_frame.pack(fill=BOTH, expand=1)

            self.fixsize()
            self.bind("<Configure>", self.eh_config)

            self.compare_btn = Button(self.trans_frame, font=SMALLFONT, bd=1,
                                      pady=1, text="compare", width=100,
                                      command=self.cb_compare)
            self.compare_btn.pack(side=TOP)
            self.updatecompare()
            self.trans_canvas = Canvas(self.trans_frame)
            self.trans_canvas.pack(fill=BOTH, expand=1)

            self.sharedspans = []
            for browser in self.browser, self.browser2:
                browser.listen("opendoc", self.updatecompare)
                browser.listen("closedoc", self.cb_closedoc)

    def quit(self):
        BrowserWindow.quit(self)
        if self.browser2:
            try: self.browser2.closedoc()
            except (IOError, x88.XuError): pass

    def updatelines(self, *args):
        """Update the transpointing lines in the middle canvas."""
        def linenum(text, index, atoi=string.atoi, split=string.split):
            return atoi(split(text.index(index), ".")[0])

        text, text2 = self.browser.doc_text, self.browser2.doc_text
        top, top2 = linenum(text, "@0,0"), linenum(text2, "@0,0")
        lineheight = text.dlineinfo("@0,0")[3]

        self.trans_canvas.config(height=text.winfo_height())
        width = self.trans_canvas.winfo_width()
        height = self.trans_canvas.winfo_height()

        def ymin(text, index):
            result = text.bbox(index)
            return result and result[1]

        def ymax(text, index):
            result = text.bbox(index)
            return result and result[1] + result[3]

        index = 0
        for leftspan, rightspan in self.sharedspans:
            id = self.translines[index]
            index = index + 1

            leftstart, leftend = text.indices(leftspan.span)
            rightstart, rightend = text2.indices(rightspan.span)

            leftymin = ymin(text, leftstart)
            leftymax = ymax(text, leftend)
            rightymin = ymin(text2, rightstart)
            rightymax = ymax(text2, rightend)

            if leftymin or leftymax or rightymin or rightymax:
                # If any boundaries are offscreen, we have to make estimates.
                if not leftymin:
                    if linenum(text, leftstart) <= top: leftymin = -1
                    else: leftymin = height + 1
                if not leftymax:
                    if linenum(text, leftend) <= top: leftymax = -1
                    else: leftymax = height + 1
                if not rightymin:
                    if linenum(text2, rightstart) <= top2: rightymin = -1
                    else: rightymin = height + 1
                if not rightymax:
                    if linenum(text2, rightend) <= top2: rightymax = -1
                    else: rightymax = height + 1

                lefty = (leftymin + leftymax)/2
                righty = (rightymin + rightymax)/2
                self.trans_canvas.coords(id, 0, lefty, width, righty)

            else:
                self.trans_canvas.coords(id, -1, -1, -1, -1)

    def eh_configcanvas(self, event):
        self.updatelines()

    def cb_compare(self):
        if self.comparing:
            self.compare_off()
        else:
            self.compare_on()

    def cb_closedoc(self, *args):
        try: self.compare_off()
        except TclError: pass

    def updatecompare(self, *args):
        """Activate the "compare" button only when both browser panes
        contain documents that are open for reading but not editing."""
        if self.browser and self.browser2:
            if self.browser.docid and self.browser2.docid and \
               not self.browser.editable and not self.browser2.editable:
                self.compare_btn.config(state=NORMAL)
            else:
                self.compare_btn.config(state=DISABLED)

    def compare_on(self):
        """Turn on the display of transpointing lines."""
        self.trans_canvas.delete("all")
        self.trans_canvas.config(background="darkgrey")

        # note: back-end seems to return bogus results if either document
        # contains more than one virtual copy of the same span of text
        self.sharedspans = self.xs.compare_versions(self.browser.textspec,
                                                    self.browser2.textspec)
        index = 0
        self.translines = []
        for leftspan, rightspan in self.sharedspans:
            colour = self.commoncolours[index % len(self.commoncolours)]

            start, end = self.browser.doc_text.indices(leftspan.span)
            tag = "left-%d" % index
            self.browser.doc_text.tag_add(tag, start, end)
            self.browser.doc_text.tag_configure(tag, background=colour)

            start, end = self.browser2.doc_text.indices(rightspan.span)
            tag = "right-%d" % index
            self.browser2.doc_text.tag_add(tag, start, end)
            self.browser2.doc_text.tag_configure(tag, background=colour)
            index = index + 1

            id = self.trans_canvas.create_line(0, 50, 100, 50)
            self.trans_canvas.itemconfigure(id, width=2, fill=colour)
            self.translines.append(id)

        self.updatelines()

        self.trans_canvas.bind("<Configure>", self.eh_configcanvas)
        for browser in self.browser, self.browser2:
            browser.listen("edit", self.updatelines)
            browser.listen("scroll", self.updatelines)

        self.compare_btn.config(relief=SUNKEN)
        self.comparing = 1

    def compare_off(self):
        """Turn off the display of transpointing lines."""
        for index in range(len(self.sharedspans)):
            self.browser.doc_text.tag_delete("left-%d" % index)
            self.browser2.doc_text.tag_delete("right-%d" % index)

        self.trans_canvas.delete("all")
        self.trans_canvas.config(background=DEFAULTBG)
        self.trans_canvas.bind("<Configure>", "")
        for browser in self.browser, self.browser2:
            browser.unlisten("edit", self.updatelines)
            browser.unlisten("scroll", self.updatelines)

        self.compare_btn.config(relief=RAISED)
        self.updatecompare()
        self.comparing = 0

    def eh_destroy(self, event):
        if not event.widget == str(self): return
        if self.browser2 is not None:
            try: self.browser2.closedoc()
            except (IOError, x88.XuError): pass
        BrowserWindow.eh_destroy(self, event)

if __name__ == "__main__":
    print "Pyxi (Python Udanax Interface) v" + str(VERSION)
    print "Copyright 1999 by Ka-Ping Yee.  All rights reserved."
    print "This program and the Udanax Green hypertext server are part of the"
    print "Udanax project.  Please see http://www.udanax.com/ for details."
    print

    cwd = os.getcwd()
    if not os.path.isdir("be"):
        print "There is no directory named \"be\" in which to run the Udanax"
        print "server.  Please create it, and also create the file (or link)"
        print "be/backend (the back-end executable)."
        sys.exit(1)
    if not os.path.isfile("be/backend"):
        print "There is no file at be/backend.  Please put a copy or a link"
        print "to the server executable there."
        sys.exit(1)
    if not os.path.exists("be/enf.enf"):
        print "No enfilade file at be/enf.enf; copying in the default."
        os.system("cp -f ../enfs/sample.enf be/enf.enf")
        
    os.chdir("be")

    import getopt
    opts, extra = getopt.getopt(sys.argv[1:], ":dst")
    if ('-d', '') in opts:
        ps = x88.DebugWrapper(x88.PipeStream("./backend"), sys.stderr)
        xc = x88.DebugWrapper(x88.XuConn(ps), sys.stderr)
        xs = x88.DebugWrapper(x88.XuSession(xc), sys.stderr)
    elif ('-s', '') in opts:
        
        port = 55146
        host = "localhost"
        ps = x88.DebugWrapper(x88.TcpStream(host,port), sys.stderr)
        xc = x88.DebugWrapper(x88.XuConn(ps), sys.stderr)
        xs = x88.DebugWrapper(x88.XuSession(xc), sys.stderr)
#        ps.write("34~0.1.0.1.1~")
    elif ('-t', '') in opts:
        port = 55146
        host = "localhost"
        xs = x88.tcpconnect(host,port)
    else:
        xs = x88.pipeconnect("./backend")
    os.chdir(cwd)

    Tk().withdraw()
    clipboard = Clipboard(xs)
    windows = {}
    window = TwoBrowserWindow(xs)
    addr = (extra + ["1.1.0.1.0.1"])[0]
    window.browser.goto(x88.Address(addr))
    mainloop()
    for window in windows.keys():
        window.quit()
    xs.quit()
    time.sleep(10.0)
