"""Pack src/UltQ into UltQ.rbxmx — a single model you drag into ServerScriptService in Roblox Studio.
Mirrors Rojo's file conventions: init.server.lua -> Script, *.client.lua -> LocalScript,
*.lua -> ModuleScript, folders -> Folder.
    python tools/build_rbxmx.py
"""
import os, sys, itertools
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "UltQ")
OUT = os.path.join(ROOT, "UltQ.rbxmx")
_ref = itertools.count(1)

def cdata(src):
    return "<![CDATA[" + src.replace("]]>", "]]]]><![CDATA[>") + "]]>"

def item(cls, name, source=None, children=()):
    ref = f"RBX{next(_ref):08X}"
    props = [f'<string name="Name">{escape(name)}</string>']
    if source is not None:
        props.append(f'<ProtectedString name="Source">{cdata(source)}</ProtectedString>')
    if cls == "Script":
        props.append('<token name="RunContext">0</token>')
    body = "".join(children)
    return f'<Item class="{cls}" referent="{ref}"><Properties>{"".join(props)}</Properties>{body}</Item>'

def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()

def build_dir(path, name):
    """A directory: Script if it has init.server.lua, else Folder."""
    entries = sorted(os.listdir(path))
    init = None
    kids = []
    for e in entries:
        full = os.path.join(path, e)
        if os.path.isdir(full):
            kids.append(build_dir(full, e))
        elif e == "init.server.lua":
            init = ("Script", read(full))
        elif e.endswith(".client.lua"):
            kids.append(item("LocalScript", e[:-len(".client.lua")], read(full)))
        elif e.endswith(".server.lua"):
            kids.append(item("Script", e[:-len(".server.lua")], read(full)))
        elif e.endswith(".lua") or e.endswith(".luau"):
            kids.append(item("ModuleScript", os.path.splitext(e)[0], read(full)))
    if init:
        return item(init[0], name, init[1], kids)
    return item("Folder", name, None, kids)

xml = ('<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
       'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
       'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">'
       '<External>null</External><External>nil</External>'
       + build_dir(SRC, "UltQ") + '</roblox>')
with open(OUT, "w", encoding="utf-8") as f:
    f.write(xml)
print("wrote", OUT, len(xml), "bytes")
