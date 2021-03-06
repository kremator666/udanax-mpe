Udanax Green + Pyxi + .mpe hacks
Berend van Berkum <berend@dotmpe.com>

Xu88.1 is found at http://udanax.com/green/. There are two interactive parts to
this project, ``backend``, and ``xumain``. The former is a executable binary
to run a server for one Xanadu Green Enfilade, loaded from ``*.enf``. The
structure is interacted with by the Xu88.1 FeBe (Frontend-Backend) protocol over
port 55146.

The ``xumain`` executable serves to interact with a BeBe (Backend-Backend)
protocol but seems mostly usefull for creating new enfilades.
A FeBe client is implemented by ``pyxi``, a Python/Tk script which provides an
editable text-view and text highlighting and linking.

My hacks include:

- x-be-pipestream-tcpwrapper.py, circumvent bug? and have single user network
  access.
- udxdot, create dot network diagrams for nodes/links
- htdoc with some tools to generate and backup enfilades
- XuDiff - handle simple remove/insertions.. muse on rearrangements. Plain text
  editor FeBe adapter based on standard file diffs.

Look at var/htdocs/1.olddemo for a good example how to create enfilades.
The Makefile has further directions on building.
Text can be inserted as is, but links will need to be writtin in Xu88.1 FeBe
syntax.

Another addition is (a part) of the Sunless Sea wiki's Xanadu Archaeology pages,
which I feared might succumb to information entropy. It does not have links,
but there are 68 pages and a bunch of images.
(See `var/htdocs/Xanadu-archaeology/ <var/htdocs/Xanadu-archaeology/README.rst>`__)

As for `Udanax Gold`__ (xu92), the two files are in ``./gold``.

The Makefile does rely on a personal GNU/Make toolkit I'm afraid but it is
simple enough to hack that out.

For more Xanadu[tm] and Transliterature related projects, see Scrow.


.. __: http://udanax.xanadu.com/gold/
